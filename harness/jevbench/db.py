"""Database helpers and the benchmark schema."""
import os

import psycopg

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS jev CASCADE;
CREATE SCHEMA IF NOT EXISTS bench;

-- One row per unique (truncated) narrative, with consumer-selected ground truth.
CREATE TABLE IF NOT EXISTS bench.complaints (
    complaint_id  text PRIMARY KEY,
    date_received date,
    product_raw   text NOT NULL,
    product       text NOT NULL,
    issue         text,
    sub_issue     text,
    narrative     text NOT NULL,
    text_hash     text NOT NULL UNIQUE      -- md5(narrative), joins results back
);

-- Exactly what the model sees: the narrative and nothing else (no ids, no labels).
-- A real table (not a view or subquery) so pg-jev streams and batches it.
CREATE TABLE IF NOT EXISTS bench.items (
    narrative text NOT NULL
);

CREATE TABLE IF NOT EXISTS bench.runs (
    run_id      text PRIMARY KEY,
    backend     text NOT NULL,
    api_url     text NOT NULL,
    model       text NOT NULL,
    n_items     int  NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    settings    jsonb NOT NULL DEFAULT '{}',
    notes       text
);

CREATE TABLE IF NOT EXISTS bench.experiment_runs (
    run_id      text NOT NULL REFERENCES bench.runs ON DELETE CASCADE,
    experiment  text NOT NULL,
    kind        text NOT NULL,
    question    text NOT NULL,
    options     text[],
    family      text,
    seconds     float8,
    stats       jsonb,                      -- jev_stats() delta for this experiment
    PRIMARY KEY (run_id, experiment)
);

CREATE TABLE IF NOT EXISTS bench.results (
    run_id     text NOT NULL,
    experiment text NOT NULL,
    text_hash  text NOT NULL,
    answer     jsonb NOT NULL,              -- raw jev_eval() answer
    PRIMARY KEY (run_id, experiment, text_hash),
    FOREIGN KEY (run_id, experiment) REFERENCES bench.experiment_runs ON DELETE CASCADE
);
"""


def dsn():
    return os.environ.get("DATABASE_URL", "postgresql://postgres:bench@localhost:54329/bench")


def connect(**kw):
    return psycopg.connect(dsn(), **kw)


def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()
