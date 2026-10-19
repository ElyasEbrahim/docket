# Roadmap

Assumes ~20 h/week. Each phase ends with an exit criterion. If a phase misses its criterion, stop and rethink before starting the next one.

## Phase 0: Validate (weeks 1–2)

Status as of 2026-10-17: harness built and validated; real Jev run done; the technical half of the go/no-go is met. See [docs/phase0/STATUS.md](docs/phase0/STATUS.md).

- [x] pg-jev v0.2.1 in Docker; upstream regression suite passes (PG 16, and PG 18: 4/4); README queries against the upstream mock (`make up smoke upstream-test`)
- [x] CFPB narrative sample: CFPB stopped publishing narratives on 2026-08-14, so sample from the CC0 mirror (`make fetch load`; 3,000 rows, 2015–2024, revision pinned in the manifest)
- [x] Harness: `choice_base`, two cyclic shifts, `choice_other` (label-set drift), two noul tasks; raw answers stored in `bench.results`
- [x] Metrics: ECE (equal-width and equal-mass) with bootstrap CIs, Brier/NLL, AUROC, cross-fitted temperature, isotonic and Platt recalibration, order-flip rate, first-position lift, drift and auto-accept set changes
- [x] Harness validated against a simulated backend with planted flaws (16 tests, plus a 2,000-row Docker run that recovers T ≈ 1/0.5)
- [x] Found: pg-jev's session cache ignores `jev.model` / `jev.api_url` (2,000/2,000 stale answers after switching backend); draft issue in [docs/phase0/upstream-issue-cache-key.md](docs/phase0/upstream-issue-cache-key.md)
- [x] Real run on jev-1.13.0 (`jev-20261017-122314`, ≈ $0.146): see [docs/phase0/FINDINGS-jev-1.13.md](docs/phase0/FINDINGS-jev-1.13.md)
- [ ] Optional second backend: stuntd / laya-server via `--api-url`; OpenAI Decisions needs an adapter (different contract)
- [x] Run-to-run determinism check and label learning curve (FINDINGS §7–§8; corrected the order and drift claims)
- [x] Batch-context check (#3): ~16.5 % of answers change with batch neighbours (FINDINGS §9)
- [ ] Measure batch size 1 (accuracy, calibration, stability) to decide how Docket batches
- [ ] Turn the draft findings into the public technical note (#2)
- [ ] File the cache-key issue upstream (after review); PR adding PostgreSQL 18 to pg-jev's CI matrix
- [ ] Open a pg-jev GitHub Discussion about persisting and calibrating judgments; talk to 5–10 potential users
- [ ] Check the name "Docket" on PyPI, GitHub and npm; pick a final name

**Exit (go/no-go):** measurable miscalibration or drift on real data **and** ≥3 people say they would use durable decisions.

## Phase 1: Ledger core (weeks 3–6)

- [ ] Migration tooling for the `docket` schema (plain SQL; PG 14–18)
- [ ] Tables: `decision`, `decision_version` (spec + `spec_hash`), `judgment` (append-only), `queue`
- [ ] Triggers on source tables → `queue` (insert/update; input-hash dedup)
- [ ] Worker: `SKIP LOCKED` claiming, LISTEN/NOTIFY + polling, batches of 20, retries, spend guards
- [ ] Backend adapters: `jev` (direct), `mock`
- [ ] `create_decision`, `backfill`, `v_<decision>` views with `pending` state
- [ ] CI: PG 14–18 containers + Supabase local + Neon branch smoke test

**Exit:** a 100k-row table judged once and read in milliseconds; works unchanged on Supabase.

## Phase 2: Trust layer (weeks 7–10)

- [ ] `gold` table with inclusion probabilities; stratified random `review_queue`; `label()`
- [ ] Calibrators (Platt, isotonic, temperature) fitted by the worker and stored as knots; applied in SQL
- [ ] `set_policy`: precision/recall targets with δ via fixed-sequence testing (Learn-then-Test) and Clopper–Pearson / betting bounds
- [ ] `estimate_count` / `estimate_share`: PPI in SQL, with refusal when gold coverage in scope is too thin
- [ ] Review-budget planner: labels needed for a target CI width or guarantee
- [ ] **Coverage-test suite** (simulation) in CI for every interval and guarantee

**Exit:** all coverage tests pass at their stated rates.

## Phase 3: Multi-backend + drift (weeks 11–12)

- [ ] Adapters: OpenAI Decisions API, `/v1/systemone`-compatible (stuntd, laya-server), Jev via OpenRouter
- [ ] Shadow versions, `revise`, `diff` (flip rate, calibration shift, gold accuracy), `promote`
- [ ] Backend comparison report (accuracy, ECE, cost, latency) on the same gold set
- [ ] Option-order debiasing for `choice` (on only if Phase 0 showed it helps)
- [ ] Instruction-injection flag decision and consistency re-checks → review queue

**Exit:** backend comparison report on two public datasets.

## Phase 4: Ship v0.1 (weeks 13–14)

- [ ] Docs site / README, quick start for self-hosted, Supabase, Neon and RDS
- [ ] Docker image + PyPI package; SQL part listed on PGXN or database.dev
- [ ] Case study (CFPB or OSHA narratives) with reproducible notebook
- [ ] Launch post; link from the pg-jev discussion

**Exit:** v0.1.0 tagged; ≥3 external users trying it.

## Later (driven by user demand)

- Gateway mode: `/v1/systemone`-compatible proxy so pg-jev's `jev.api_url` gets a persistent cross-session cache and ledger
- Cascades through stuntd/Laya (local-first, escalate uncertain rows)
- dbt package; minimal review web UI
