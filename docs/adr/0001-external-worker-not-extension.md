# ADR 0001: Core is plain SQL plus an external worker, not a server-side extension

- Status: Proposed
- Date: 2026-10-17

## Context

pg-jev runs inside the database as a `plpython3u` function. That requires superuser and an untrusted language, which rules out Supabase, Neon, RDS/Aurora and most other managed hosts. The pg-jev docs list these hosts as unsupported. pgai Vectorizer hit the same wall and, in April 2025, moved its embedding worker out of the database. Since then it runs against any Postgres with triggers + a queue table + an external process.

## Decision

- The `docket` schema is plain SQL and trusted PL/pgSQL, applied like a migration by a role that owns its schema.
- All network calls, model I/O and statistical fitting happen in an external worker (Python, shipped as a Docker image and a pip package).
- The worker claims jobs with `FOR UPDATE SKIP LOCKED`, wakes on `LISTEN/NOTIFY`, and falls back to polling.
- Anything that must be computed at read time (applying a calibrator, PPI estimates) is closed-form SQL over stored parameters.

## Consequences

- Runs on any Postgres 14+ that allows triggers, including managed hosts.
- Judgments are eventually consistent: a new row is `pending` for seconds, not judged inside the inserting transaction.
- Operators run one more process. This is mitigated by a single container and a health view (`docket.worker_status`).
- No planner integration. pgdocket does not try to replace pg-jev's ad-hoc predicates; it handles the production side.
