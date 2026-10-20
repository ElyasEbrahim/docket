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
    files = sorted(f for f in resources.files("pgdocket").joinpath("sql").iterdir() if f.name.endswith(".sql"))
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


def import_labels(dsn, name, column=None, csv_path=None, sample=None, seed="1", positive=None, random=False):
    """Copy human labels into docket.label, from a column of the source table or from a key,label CSV.

    Labels record how they were chosen: `--sample N` from a column is a uniform random sample ('random');
    a whole column is 'all'; a CSV is 'manual' unless the caller says it was drawn at random (`random=True`,
    e.g. a file from `pgdocket check --export-sample`). Only 'random' labels feed `estimate` by default.
    For yes/no decisions, labels are stored as 'yes' / 'no' (`positive` is the value that means yes).
    """
    with connect(dsn) as conn:
        d = _decision(conn, name)
        noul = d["spec"]["kind"] == "noul"
        if noul and positive is None:
            raise SystemExit("a yes/no decision needs --positive: the label value that means yes")
        names = option_names(d["spec"]) if not noul else None
        if column:
            col = sql.Identifier(column)
            cond = sql.SQL(" AND {}::text = ANY(%(names)s)").format(col) if names else sql.SQL("")
            value = (sql.SQL("CASE WHEN s.{}::text = %(pos)s THEN 'yes' ELSE 'no' END").format(col) if noul
                     else sql.SQL("s.{}::text").format(col))
            q = sql.SQL("""
                INSERT INTO docket.label (decision_id, row_key, label, source, sampling)
                SELECT %(did)s, s.{key}::text, {value}, %(src)s, %(sampling)s FROM {table} s
                WHERE s.{col} IS NOT NULL{cond}
                ORDER BY md5(s.{key}::text || %(seed)s) {limit}
                ON CONFLICT (decision_id, row_key) DO UPDATE SET label = EXCLUDED.label, source = EXCLUDED.source,
                    sampling = EXCLUDED.sampling, labeled_at = now()""").format(
                key=sql.Identifier(d["key"]), col=col, value=value, table=sql.SQL(d["source"]), cond=cond,
                limit=sql.SQL("LIMIT {}").format(sql.Literal(int(sample))) if sample else sql.SQL(""))
            cur = conn.execute(q, {"did": d["id"], "src": f"column:{column}", "seed": ":" + str(seed), "names": names,
                                   "pos": None if positive is None else str(positive),
                                   "sampling": "random" if sample else "all"})
            return cur.rowcount
        rows = []
        with open(csv_path, newline="") as f:
            for r in csv.DictReader(f):
                label = (r.get("label") or "").strip()
                if not label:
                    continue
                if noul:
                    label = "yes" if label == str(positive) else "no"
                elif label not in names:
                    continue
                rows.append((d["id"], r["key"], label, "csv:" + os.path.basename(csv_path), "random" if random else "manual"))
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO docket.label (decision_id, row_key, label, source, sampling) VALUES (%s, %s, %s, %s, %s) "
                            "ON CONFLICT (decision_id, row_key) DO UPDATE SET label = EXCLUDED.label, "
                            "source = EXCLUDED.source, sampling = EXCLUDED.sampling, labeled_at = now()", rows)
        return len(rows)


def calibrate(dsn, name, precision_target=0.9, alpha=0.05):
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
            labels = [r[0] == "yes" for r in rows]                    # normalised at import
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


def estimate(dsn, name, answer=None, where=None, level=0.95, include_manual=False):
    """Counts with error bars from docket.estimate() (prediction-powered inference)."""
    sampling = ["random", "all", "manual"] if include_manual else ["random"]
    with connect(dsn) as conn:
        cur = conn.execute("SELECT * FROM docket.estimate(%s, %s, %s, %s, %s)", (name, answer, where, level, sampling))
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
