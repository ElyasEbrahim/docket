# The ledger: stored decisions kept current in Postgres

*2026-10-20 · issue #13 · design: [ADR 0004](../adr/0004-ledger-queue-and-worker.md)*

The core of pgdocket: declare a decision on a table once, and every row gets a stored, versioned answer that stays current as rows are inserted or edited. It's plain SQL plus an external worker, with no superuser and no extension.

## How it fits together

```
your table ──insert/update of judged columns──▶ trigger ──▶ docket.queue ──NOTIFY──▶ worker
                                                                                 │ one row per request
docket.v_<name>  ◀── docket.current ◀── docket.judgment (append-only ledger) ◀──┘
   key · status · answer · confidence (calibrated) · auto · judged_at · version
```

```bash
pgdocket install                                     # schema docket (migration 001)
pgdocket create triage --table shop.tickets --key id --text subject,body \
  --kind choice --question "Which team should handle this ticket?" \
  --options-file teams.json                                  # triggers + view; existing rows queued
pgdocket worker                                      # keeps judging as rows arrive
pgdocket label triage --from-column team --sample 200   # or --csv labels.csv
pgdocket calibrate triage --precision-target 0.9
psql -c "SELECT key, answer, confidence, auto FROM docket.v_triage WHERE status = 'judged'"
```

## Tests

10 integration tests run on a real Postgres in CI, on **versions 14, 15, 16, 17 and 18**. pgdocket runs as an ordinary role, and the application writes as a second role **with no grant on the `docket` schema**. They cover:

- install without superuser, and re-running install (idempotent);
- backfill on create, and enqueueing from the app role through the `SECURITY DEFINER` trigger;
- judging, and reading through the view;
- re-queuing only when a judged column actually changes (another column, or the same value, doesn't count);
- skipping unchanged input on a backfill;
- deleted rows leaving the view while staying in the ledger;
- back-off and dead-letter after 5 failures (`status = 'error'`);
- labels and calibration, with the SQL calibration function matching the Python one exactly on every row;
- `drop_decision`.

## Scale: 100,000 rows (simulated backend, free)

| Step | Result |
| --- | --- |
| `pgdocket create` on a 100,000-row table (backfill queued) | **1.6 s** including container start |
| Worker judges all 100,000 rows (one per request, 32 concurrent) | **161 s** (~620 rows/s), 0 failures |
| Read one row from `docket.v_scale` | **0.14 ms** execution (index lookups only); 0.5–3 ms from the client |
| Aggregate over all 100,000 rows (`GROUP BY answer`) | **90–160 ms** |
| Change `team` on 5,000 rows (not judged) | **0 rows** queued |
| Edit the text of 1,000 rows | exactly **1,000** queued, shown as `pending`, re-judged in ~3 s; ledger holds 101,000 judgments for 100,000 rows |

The simulator answers in about a millisecond, so 620 rows/s measures pgdocket's own overhead. With Jev (≈ 0.2–0.3 s per call at 32 in parallel), expect roughly 100–150 rows/s. That's about 11–17 minutes and ~$4 for 100,000 Kubernetes-length rows.

**Phase 1 exit criterion** ("a 100k-row table judged once and read in milliseconds; no superuser"): met.

## Live: Kubernetes issues arriving one by one (real Jev)

The 300 most recent issues that belong to one of the 10 SIGs were inserted into an empty `demo.k8s_live` table in their original order, at 10 per second. The worker ran in the background with a $0.05 spending cap. Cost: 307,114 tokens, about **$0.013**.

| | Before the fix | After the fix |
| --- | ---: | ---: |
| Time from `INSERT` to stored answer, median | 3.9 s | **0.71 s** |
| 95th percentile / max | 5.4 s / 5.9 s | **3.0 s** / 4.1 s |
| Routing agreement with the SIG label | 91.7 % | 91.3 % |

**The fix.** The first run exposed a bug: the backend client built a new thread pool for every call. Its per-thread HTTPS connections were thrown away, so every batch paid a fresh TLS handshake and server-side setup (pg-jev measured up to 1.9 s for that). With one pool for the client's lifetime, connections are reused. A unit test now checks that three calls share at most one connection per thread. The remaining tail is mostly the 16 connections each paying their first handshake once.

### Calibrating like a team would, and checking it on unseen issues

200 of the 300 issues' real SIG labels were imported (`pgdocket label --from-column sig --sample 200`), then `pgdocket calibrate --precision-target 0.9`:

- calibration error **0.059 → 0.026**;
- threshold **0.732**, guaranteeing precision ≥ 90 % (95 % confidence) on the labeled sample, with **95 %** of rows above it.

The view picked up the new calibration immediately, without re-judging anything. On the **100 issues whose labels weren't used**:

| | Held-out issues |
| --- | ---: |
| Accuracy | 87.0 % |
| Auto-routed (`auto = true`) | **92 of 100** |
| Precision of the auto-routed | **89.1 %** (82 of 92); exact 95 % interval 80.9–94.7 % |
| Accuracy of the 8 sent to review | 62.5 % |

How to read this: 89.1 % is just under the 90 % target, but well inside the noise for 92 rows. If the true precision were exactly 90 %, a result this low or lower would occur 44 % of the time. So the held-out check is **consistent with the guarantee but too small to confirm it**. A confirmation needs a few hundred held-out rows. The threshold clearly does its job of routing the hard cases to a person: the model is right on only 62.5 % of the issues it held back.

## Known limits

- Reads are eventually consistent: a new row is `pending` until the worker has judged it.
- The ledger grows with every re-judgment. Archiving or partitioning old versions is future work.
- Shadow versions (`docket.revise` / `docket.promote`) exist in SQL but have no CLI or diff report yet (Phase 3).
- The threshold is chosen on out-of-fold scores, but the view applies it to the final calibrator's scores. These are close, not identical.
- Not yet tested on Supabase, Neon or RDS themselves. The non-superuser CI setup mirrors their permission model, but not their exact configuration.
