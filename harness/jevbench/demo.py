"""Load the Kubernetes issues (jevbench.ghissues output) into a table that looks like a user's own data.

demo.k8s_issues: one row per issue, with the human-applied routing label (`sig`, when exactly one sig/* label)
and type label (`kind`, when exactly one kind/* label). `docket check` points at it like any other table.
"""
import json

from .db import connect

DDL = """
CREATE SCHEMA IF NOT EXISTS demo;
DROP TABLE IF EXISTS demo.k8s_issues;
CREATE TABLE demo.k8s_issues (
    number      int PRIMARY KEY,
    created_at  timestamptz NOT NULL,
    closed_at   timestamptz,
    state       text,
    title       text NOT NULL,
    body        text NOT NULL,
    labels      text[] NOT NULL,
    sig         text,          -- the single sig/* label, if exactly one
    kind        text           -- the single kind/* label, if exactly one
);
"""


def _single(labels, prefix):
    vals = [l[len(prefix):] for l in labels if l.startswith(prefix)]
    return vals[0] if len(vals) == 1 else None


def load_github(path):
    rows = [json.loads(line) for line in open(path)]
    with connect() as conn, conn.cursor() as cur:
        cur.execute(DDL)
        with cur.copy("COPY demo.k8s_issues (number, created_at, closed_at, state, title, body, labels, sig, kind) "
                      "FROM STDIN") as cp:
            for r in rows:
                cp.write_row((r["number"], r["created_at"], r["closed_at"], r["state"], r["title"], r["body"],
                              r["labels"], _single(r["labels"], "sig/"), _single(r["labels"], "kind/")))
        cur.execute("ANALYZE demo.k8s_issues")
        cur.execute("SELECT count(*), count(sig), count(kind) FROM demo.k8s_issues")
        total, with_sig, with_kind = cur.fetchone()
        conn.commit()
    return {"issues": total, "with_single_sig": with_sig, "with_single_kind": with_kind}
