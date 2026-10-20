# ADR 0004: Ledger, queue and worker

- Status: Accepted
- Date: 2026-10-20

## Context

ADR 0001 puts pgdocket's core in plain SQL with an external worker. ADR 0002 makes the versioned spec the unit of deployment and, after Phase 0, defaults to one row per request. Phase 0 also showed that answers aren't reproducible by asking again (4.8 % of rows flip across identical runs), so the stored answer is the record. This ADR fixes the concrete data model and the worker contract for Phase 1.

## Decision

**Tables** (schema `docket`):

| Table | Role |
| --- | --- |
| `decision` | name, source table, key column (and its type), judged text columns, active version |
| `version` | spec (kind, question, options, backend, model, batch size), `spec_hash`, status `shadow` / `active` / `retired`, calibration |
| `judgment` | **append-only ledger**: raw answer, option or score, input hash, tokens, time. Never updated. |
| `current` | latest judgment per (decision, version, row): a cache of the ledger, so reads are one primary-key join |
| `queue` | rows to judge, with attempts, lease (`locked_until`), claim token and last error |
| `label` | human labels used for calibration |

**Triggers.** `create_decision` adds an `AFTER INSERT` trigger and an `AFTER UPDATE` trigger whose `WHEN` clause fires only if a judged column changed. The trigger function is `SECURITY DEFINER` with a fixed `search_path`. Application roles that write to the source table can then enqueue without any grant on the `docket` schema.

**Worker.** The worker:
1. Claims a batch with `UPDATE … FROM (SELECT … FOR UPDATE SKIP LOCKED)`, setting a lease and a fresh claim token, and commits.
2. Reads the rows and computes the input hash of the exact JSON it will send. Unchanged input is dequeued without a call.
3. Judges the rows outside any transaction.
4. In one transaction, appends to `judgment`, upserts `current`, and deletes the queue rows *that still carry its claim token*. If a row changed while it was being judged, the trigger has reset the token, so the row stays queued and is judged again.

Failures back off exponentially. After 5 attempts a row is left with its error and shows as `error` in the view. The worker wakes on `NOTIFY docket` and polls as a fallback.

**Reads.** Each decision gets a view `docket.v_<name>` over the source table. It has: key, status (`pending` / `judged` / `missing` / `error`), answer, raw score, calibrated confidence, `auto` (confidence ≥ the guaranteed threshold), judged time and version. Calibration is applied by an `IMMUTABLE` SQL function from parameters stored on the version, so a new calibration takes effect without re-judging.

## Consequences

- Reads are eventually consistent: a new row is `pending` for as long as the worker takes.
- Deleting a source row removes it from the view. Its judgments stay in the ledger for audit.
- The ledger grows with every re-judgment. Partitioning or archiving old versions is a later concern.
- `SECURITY DEFINER` means the trigger runs with the schema owner's rights. It only inserts into `docket.queue`, and `search_path` is pinned to prevent hijacking.
- No superuser and no extension: everything needs ordinary `CREATE` on a database and ownership of the source table (for the triggers).
