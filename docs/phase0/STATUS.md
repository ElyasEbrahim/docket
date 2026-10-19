# Phase 0 status, 2026-10-17

## Done

| Item | Result |
| --- | --- |
| pg-jev in Docker | PostgreSQL 16 + plpython3u + pg-jev **v0.2.1**, built from the upstream tag (`make up`) |
| Upstream regression suite | **4/4 pass** on PG 16 (`make upstream-test`) and **4/4 on PG 18**, which pg-jev's CI doesn't cover yet |
| Upstream mock | pg-jev's own `test/mock_api.py` served to the stack; README queries work (`make smoke`) |
| Data | CFPB stopped publishing narratives on **14 Aug 2026**, so the live API and bulk CSV no longer carry them. 3,000-row uniform sample (2015-03 → 2024-02) from the CC0 mirror, revision `088cc730…` pinned in `data/raw/cfpb_sample.jsonl.manifest.json`. 2,000 rows loaded. |
| Harness | `jevbench` CLI: 6 experiments (product choice, 2 option orderings, label-set drift, 2 yes/no tasks), raw answers in `bench.results`, Markdown + JSON report |
| Validation | Simulated backend that is calibrated by construction, with planted over-confidence and first-option bias. 16 unit tests. Docker run on 2,000 rows: [`results/sim-20261017-121347/report.md`](../../results/sim-20261017-121347/report.md). It recovers the planted temperature (fitted T = 1.99 vs. planted 1/0.5), ECE drops 0.059 → 0.012 after recalibration, and the first-option lift is positive with a CI that excludes 0. |

## Findings from building the harness

1. **pg-jev's session cache ignores `jev.model` and `jev.api_url`.** After switching backend in one session, 2,000 of 2,000 answers were stale copies from the previous backend (`make cachecheck`). The draft issue is in [upstream-issue-cache-key.md](upstream-issue-cache-key.md). This is direct evidence for ADR 0002: the cache and the deployable unit both have to include model and endpoint.
2. **pg-jev works unchanged on PostgreSQL 18.** Adding it to CI is an easy, credible first upstream PR.
3. **The best-known public benchmark for this task lost its source.** CFPB narratives are only available from mirrors now. This is worth one sentence in the technical note, and a reason to add a second dataset (e.g. OSHA severe-injury narratives) in Phase 1.
4. **ECE alone under-reports over-confidence when a backend is usually sure of itself.** On a strong-signal yes/no task, a sharpened backend barely moves ECE. The report therefore also shows NLL, Brier, the fitted temperature and equal-mass ECE.

## Real-model run: done (2026-10-17)

`jev-20261017-122314`: jev-1.13.0, 2,000 rows × 6 experiments, ≈ $0.146. Write-up: [FINDINGS-jev-1.13.md](FINDINGS-jev-1.13.md). Report: [`results/jev-20261017-122314/report.md`](../../results/jev-20261017-122314/report.md).

The technical half of the go/no-go is met: miscalibration 3.3× (choice) to 15× (yes/no) above recalibrated; option order changes 7.4 % of answers; adding one option flips 5.8 %. Still open: user interviews, and filing the upstream issue and PR.

## Follow-ups: done (2026-10-18)

- **Determinism** (two repeats of `choice_base`, ≈ $0.053): identical requests change the top answer for 4.8 % of rows across three runs; only 27.5 % of rows get identical probabilities. Batching was verified identical via the simulator's request log, so the variation is the API's. This corrected the order and drift findings, because part of those flips was run-to-run noise.
- **Label learning curve** (no API cost): about 100 labels remove 45–85 % of the raw ECE; one-parameter calibrators beat isotonic up to 500 labels. ADR 0003 is updated accordingly.

- **Batch context** (issue #3, ≈ $0.053 including a same-day control): re-batching the same rows changed the top answer for ~16.5 % of rows, against ~3 % run-to-run noise (+13.6 pp [13.2, 14.1]). Flipped answers tend to match a new neighbour's answer. Docket must judge rows singly or record batch composition; batch size 1 is the next measurement.

See FINDINGS §4, §5, §7, §8 and §9.
