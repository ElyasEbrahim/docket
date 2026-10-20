"""Replay real issues into an empty "live" table in their original order, as if they were arriving now.

demo.k8s_live mirrors a team's ticket table: pgdocket judges `title` and `body`; `sig` is the team the issue was
eventually routed to (the label a triager would record), and `inserted_at` lets us measure decision latency.
"""
import time

from .db import connect

DDL = """
CREATE SCHEMA IF NOT EXISTS demo;
DROP TABLE IF EXISTS demo.k8s_live;
CREATE TABLE demo.k8s_live (
    number      int PRIMARY KEY,
    created_at  timestamptz NOT NULL,
    title       text NOT NULL,
    body        text NOT NULL,
    sig         text,
    inserted_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
"""


def create_live_table():
    with connect() as conn:
        conn.execute(DDL)
        conn.commit()


def replay(n=300, rate=10.0, sigs=None, log=print):
    """Insert the `n` most recent in-scope issues, oldest first, one per transaction, at `rate` per second."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT number, created_at, title, body, sig FROM ("
            "  SELECT * FROM demo.k8s_issues WHERE sig = ANY(%s) ORDER BY created_at DESC LIMIT %s"
            ") recent ORDER BY created_at", (sigs, n)).fetchall()
    gap = 1.0 / rate
    with connect(autocommit=True) as conn:
        t0 = time.time()
        for i, r in enumerate(rows, 1):
            conn.execute("INSERT INTO demo.k8s_live (number, created_at, title, body, sig) VALUES (%s, %s, %s, %s, %s)", r)
            if i % 50 == 0:
                log(f"  inserted {i}/{len(rows)}")
            time.sleep(max(0.0, t0 + i * gap - time.time()))
    return {"inserted": len(rows), "seconds": round(time.time() - t0, 1)}
