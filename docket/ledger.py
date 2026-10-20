"""Install the ledger schema and manage decisions, labels and calibration (ADR 0004)."""
import csv
import json
import os
from importlib import resources

from psycopg import sql
from psycopg.types.json import Jsonb

from . import calibration
from .spec import option_names, validate

MIGRATION_TABLE = "CREATE SCHEMA IF NOT EXISTS docket; " \
                  "CREATE TABLE IF NOT EXISTS docket.migration (version text PRIMARY KEY, " \
                  "applied_at timestamptz NOT NULL DEFAULT now())"


def connect(dsn, **kw):
    import psycopg
    return psycopg.connect(dsn, **kw)


def _migrations():
    files = sorted(f for f in resources.files("docket").joinpath("sql").iterdir() if f.name.endswith(".sql"))
    return [(f.name.split("_", 1)[0], f.read_text()) for f in files]


def install(dsn):
    """Apply pending migrations in order; each in its own transaction. Returns the versions applied."""
    applied = []
    with connect(dsn) as conn:
        conn.execute(MIGRATION_TABLE)
        conn.commit()
        done = {r[0] for r in conn.execute("SELECT version FROM docket.migration")}
        for version, text in _migrations():
            if version in done:
                continue
            with conn.transaction():
                conn.execute(text)
                conn.execute("INSERT INTO docket.migration (version) VALUES (%s)", (version,))
            applied.append(version)
    return applied


def create(dsn, name, table, key, text, spec, backfill=True):
    validate(spec)
    with connect(dsn) as conn:
        did = conn.execute("SELECT docket.create_decision(%s, %s::regclass, %s, %s, %s, %s)",
                           (name, table, key, text, Jsonb(spec), backfill)).fetchone()[0]
        queued = conn.execute("SELECT count(*) FROM docket.queue WHERE decision_id = %s", (did,)).fetchone()[0]
    return did, queued


def _decision(conn, name):
    r = conn.execute("SELECT d.id, d.source, d.key_column, d.active_version, v.spec FROM docket.decision d "
                     "JOIN docket.version v ON v.decision_id = d.id AND v.version = d.active_version "
                     "WHERE d.name = %s", (name,)).fetchone()
    if not r:
        raise SystemExit(f"no decision named {name!r}")
    return {"id": r[0], "source": r[1], "key": r[2], "version": r[3], "spec": r[4]}


def import_labels(dsn, name, column=None, csv_path=None, sample=None, seed="1"):
    """Copy human labels into docket.label, from a column of the source table or from a key,label CSV."""
    with connect(dsn) as conn:
        d = _decision(conn, name)
        names = option_names(d["spec"]) if d["spec"]["kind"] == "choice" else None
        if column:
            col = sql.Identifier(column)
            cond = sql.SQL(" AND {}::text = ANY(%(names)s)").format(col) if names else sql.SQL("")
            q = sql.SQL("""
                INSERT INTO docket.label (decision_id, row_key, label, source)
                SELECT %(did)s, s.{key}::text, s.{col}::text, %(src)s FROM {table} s
                WHERE s.{col} IS NOT NULL{cond}
                ORDER BY md5(s.{key}::text || %(seed)s) {limit}
                ON CONFLICT (decision_id, row_key) DO UPDATE SET label = EXCLUDED.label, source = EXCLUDED.source,
                    labeled_at = now()""").format(
                key=sql.Identifier(d["key"]), col=col, table=sql.SQL(d["source"]), cond=cond,
                limit=sql.SQL("LIMIT {}").format(sql.Literal(int(sample))) if sample else sql.SQL(""))
            cur = conn.execute(q, {"did": d["id"], "src": f"column:{column}", "seed": ":" + str(seed), "names": names})
            return cur.rowcount
        rows = []
        with open(csv_path, newline="") as f:
            for r in csv.DictReader(f):
                label = (r.get("label") or "").strip()
                if label and (names is None or label in names):
                    rows.append((d["id"], r["key"], label, "csv:" + os.path.basename(csv_path)))
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO docket.label (decision_id, row_key, label, source) VALUES (%s, %s, %s, %s) "
                            "ON CONFLICT (decision_id, row_key) DO UPDATE SET label = EXCLUDED.label, "
                            "source = EXCLUDED.source, labeled_at = now()", rows)
        return len(rows)


def calibrate(dsn, name, precision_target=0.9, alpha=0.05, positive="true"):
    """Fit a calibrator on labeled rows that have a current answer, and store it on the active version."""
    with connect(dsn) as conn:
        d = _decision(conn, name)
        rows = conn.execute(
            "SELECT l.label, j.answer FROM docket.label l "
            "JOIN docket.current c ON c.decision_id = l.decision_id AND c.version = %s AND c.row_key = l.row_key "
            "JOIN docket.judgment j ON j.id = c.judgment_id WHERE l.decision_id = %s ORDER BY l.row_key",
            (d["version"], d["id"])).fetchall()
        spec = d["spec"]
        if spec["kind"] == "choice":
            names = set(option_names(spec))
            rows = [r for r in rows if r[0] in names]
            labels = [r[0] for r in rows]
        else:
            labels = [str(r[0]).strip().lower() == str(positive).lower() for r in rows]
        cal = calibration.fit(spec, [r[1] for r in rows], labels, precision_target, alpha)
        conn.execute("UPDATE docket.version SET calibration = %s WHERE decision_id = %s AND version = %s",
                     (Jsonb(cal), d["id"], d["version"]))
    return cal


def status(dsn):
    with connect(dsn) as conn:
        cur = conn.execute("SELECT * FROM docket.status ORDER BY name")
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def load_spec(kind, question, options=None, options_file=None, backend="jev", model="jev-1.13.0", batch_size=1):
    opts = []
    if options_file:
        with open(options_file) as f:
            opts = [o if isinstance(o, dict) else {"name": o} for o in json.load(f)]
    elif options:
        opts = [{"name": o.strip()} for o in options.split(",") if o.strip()]
    spec = {"kind": kind, "question": question, "backend": backend, "model": model, "batch_size": batch_size}
    if kind == "choice":
        spec["options"] = opts
    return validate(spec)
