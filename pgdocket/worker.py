"""The worker: judges queued rows and writes them to the ledger (ADR 0004).

Claim with a lease and claim token (FOR UPDATE SKIP LOCKED) → read rows → skip unchanged input →
judge outside any transaction → append judgments, upsert `current` and dequeue (only rows still carrying our
claim token) in one transaction. Failures back off; after 5 attempts a row shows as `error`.
"""
import hashlib
import json
import time
import uuid
from collections import defaultdict

from psycopg import sql

from .backend import Backend, BackendError
from .spec import option_display, read_answer

MAX_ATTEMPTS = 5

CLAIM = """
UPDATE docket.queue q
SET locked_until = now() + make_interval(mins => %(lease)s), attempts = q.attempts + 1, claim = %(token)s
FROM (SELECT decision_id, version, row_key FROM docket.queue
      WHERE (locked_until IS NULL OR locked_until < now()) AND attempts < %(max)s
      ORDER BY enqueued_at
      LIMIT %(n)s
      FOR UPDATE SKIP LOCKED) c
WHERE q.decision_id = c.decision_id AND q.version = c.version AND q.row_key = c.row_key
RETURNING q.decision_id, q.version, q.row_key, q.attempts
"""


class Worker:
    def __init__(self, dsn, api_key=None, claim_size=100, concurrency=16, max_usd=None, poll=5.0, lease_minutes=10,
                 log=print):
        self.dsn, self.api_key = dsn, api_key
        self.claim_size, self.concurrency, self.max_usd = claim_size, concurrency, max_usd
        self.poll, self.lease, self.log = poll, lease_minutes, log
        self.backends, self.decisions = {}, {}
        self.totals = {"judged": 0, "skipped_unchanged": 0, "deleted_rows": 0, "failed": 0, "tokens": 0, "usd": 0.0}

    def _conn(self):
        import psycopg
        # Autocommit: every read is its own statement, and only the explicit `transaction()` blocks group writes,
        # so no transaction stays open while the backend is being called.
        return psycopg.connect(self.dsn, autocommit=True)

    def _backend(self, spec):
        k = (spec.get("backend", "jev"), spec.get("model", "jev-1.13.0"))
        if k not in self.backends:
            self.backends[k] = Backend(k[0], api_key=self.api_key, model=k[1], concurrency=self.concurrency)
        return self.backends[k]

    def _decision(self, conn, did, ver):
        if (did, ver) not in self.decisions:          # a version's spec never changes, so caching is safe
            r = conn.execute("SELECT d.source, d.key_column, d.key_type, d.text_columns, v.spec FROM docket.decision d "
                             "JOIN docket.version v ON v.decision_id = d.id WHERE d.id = %s AND v.version = %s",
                             (did, ver)).fetchone()
            self.decisions[(did, ver)] = dict(zip(("source", "key", "key_type", "text", "spec"), r))
        return self.decisions[(did, ver)]

    def _rows(self, conn, d, keys):
        pairs = sql.SQL(", ").join(sql.SQL("{}, s.{}").format(sql.Literal(c), sql.Identifier(c)) for c in d["text"])
        q = sql.SQL("SELECT s.{k}::text, json_build_object({pairs})::text FROM {src} s WHERE s.{k} = ANY(%s::{kt}[])").format(
            k=sql.Identifier(d["key"]), pairs=pairs, src=sql.SQL(d["source"]), kt=sql.SQL(d["key_type"]))
        return dict(conn.execute(q, (keys,)).fetchall())

    def _hashes(self, conn, did, ver, keys):
        return dict(conn.execute(
            "SELECT c.row_key, j.input_hash FROM docket.current c JOIN docket.judgment j ON j.id = c.judgment_id "
            "WHERE c.decision_id = %s AND c.version = %s AND c.row_key = ANY(%s)", (did, ver, keys)).fetchall())

    def _dequeue(self, conn, did, ver, keys, token):
        conn.execute("DELETE FROM docket.queue WHERE decision_id = %s AND version = %s AND row_key = ANY(%s) AND claim = %s",
                     (did, ver, keys, token))

    def _fail(self, conn, did, ver, keys, token, err):
        conn.execute(
            "UPDATE docket.queue SET last_error = %s, claim = NULL, "
            "locked_until = CASE WHEN attempts >= %s THEN NULL "
            "ELSE now() + make_interval(secs => least(3600, 30 * power(2, attempts - 1))) END "
            "WHERE decision_id = %s AND version = %s AND row_key = ANY(%s) AND claim = %s",
            (str(err)[:500], MAX_ATTEMPTS, did, ver, keys, token))

    def process_once(self):
        """Claim and handle one batch. Returns the number of queue rows handled (0 = nothing to do)."""
        token = uuid.uuid4()
        with self._conn() as conn:
            claimed = conn.execute(CLAIM, {"lease": self.lease, "token": token, "max": MAX_ATTEMPTS,
                                           "n": self.claim_size}).fetchall()
            groups = defaultdict(list)
            for did, ver, key, _ in claimed:
                groups[(did, ver)].append(key)
            for (did, ver), keys in groups.items():
                self._handle(conn, did, ver, keys, token)
        return len(claimed)

    def _handle(self, conn, did, ver, keys, token):
        d = self._decision(conn, did, ver)
        spec = d["spec"]
        rows = self._rows(conn, d, keys)
        hashes = self._hashes(conn, did, ver, keys)
        gone = [k for k in keys if k not in rows]
        todo, same = [], []
        for k in keys:
            if k in rows:
                h = hashlib.md5(rows[k].encode()).hexdigest()
                (same if hashes.get(k) == h else todo).append((k, h))
        with conn.transaction():
            self._dequeue(conn, did, ver, gone + [k for k, _ in same], token)
        self.totals["deleted_rows"] += len(gone)
        self.totals["skipped_unchanged"] += len(same)
        if not todo:
            return
        backend = self._backend(spec)
        before = backend.stats["input_tokens"]
        try:
            answers = backend.judge([json.loads(rows[k]) for k, _ in todo], spec["kind"], spec["question"],
                                    option_display(spec) if spec["kind"] == "choice" else None,
                                    spec.get("batch_size", 1))
        except BackendError as e:
            with conn.transaction():
                self._fail(conn, did, ver, [k for k, _ in todo], token, e)
            self.totals["failed"] += len(todo)
            self.log(f"backend error on {len(todo)} rows of decision {did} v{ver}: {e}")
            return
        tokens = backend.stats["input_tokens"] - before
        per_row = round(tokens / len(todo))
        values = [read_answer(spec, a) for a in answers]
        with conn.transaction():
            ids = conn.execute(
                "INSERT INTO docket.judgment (decision_id, version, row_key, input_hash, answer, value, score, tokens) "
                "SELECT %s, %s, k, h, a::jsonb, v, s, %s FROM unnest(%s::text[], %s::text[], %s::text[], %s::text[], %s::float8[]) "
                "AS t(k, h, a, v, s) RETURNING id, row_key",
                (did, ver, per_row, [k for k, _ in todo], [h for _, h in todo], [json.dumps(a) for a in answers],
                 [v for v, _ in values], [s for _, s in values])).fetchall()
            conn.execute(
                "INSERT INTO docket.current (decision_id, version, row_key, judgment_id) "
                "SELECT %s, %s, k, j FROM unnest(%s::bigint[], %s::text[]) AS t(j, k) "
                "ON CONFLICT (decision_id, version, row_key) DO UPDATE SET judgment_id = EXCLUDED.judgment_id",
                (did, ver, [i for i, _ in ids], [k for _, k in ids]))
            self._dequeue(conn, did, ver, [k for k, _ in todo], token)
        self.totals["judged"] += len(todo)
        self.totals["tokens"] += tokens
        self.totals["usd"] = sum(b.cost_usd() for b in self.backends.values() if b.paid)

    def run(self, once=False):
        """Process until the queue is empty (once=True), or forever, waking on NOTIFY docket."""
        import psycopg
        listen = psycopg.connect(self.dsn, autocommit=True)
        listen.execute("LISTEN docket")
        try:
            while True:
                if self.max_usd is not None and self.totals["usd"] >= self.max_usd:
                    self.log(f"spend cap reached (${self.totals['usd']:.4f} ≥ ${self.max_usd}); stopping")
                    return self.totals
                n = self.process_once()
                if n:
                    self.log(f"handled {n} rows · judged {self.totals['judged']} · unchanged {self.totals['skipped_unchanged']}"
                             f" · failed {self.totals['failed']} · ${self.totals['usd']:.4f}")
                    continue
                if once:
                    return self.totals
                for _ in listen.notifies(timeout=self.poll, stop_after=1):
                    pass
        finally:
            listen.close()
