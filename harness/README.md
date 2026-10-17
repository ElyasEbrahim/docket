# Phase 0 benchmark harness

Measures how calibrated, order-sensitive and label-set-sensitive a decision backend is **when called through pg-jev on real Postgres data**. Everything runs in Docker.

## Stack

| Service | What |
| --- | --- |
| `db` | PostgreSQL 16 + `plpython3u` + pg-jev **v0.2.1**, built from the upstream git tag (port `127.0.0.1:54329`, user `postgres`, password `bench`, db `bench`) |
| `mock` | pg-jev's own deterministic mock API (`test/mock_api.py` at v0.2.1), keyless under `/local/` |
| `sim` | Simulated Jev-compatible backend with **planted** flaws: over-confidence (temperature), first-option bias, row difficulty. It derives answers from the labels, so it is only for checking that the harness measures what it claims. |
| `bench` | The `jevbench` CLI (`harness/jevbench`) |

## Data

CFPB stopped publishing complaint narratives on **14 Aug 2026**: the live API and the bulk CSV no longer carry them. Narratives published before that were CC0. The harness samples them from the CC0 Hugging Face mirror [`BEE-spoke-data/consumer-finance-complaints`](https://huggingface.co/datasets/BEE-spoke-data/consumer-finance-complaints) (config `has-text`, 1.69M complaints, 2015-03 → 2024-02) through the datasets-server API, and records the dataset revision in `data/raw/*.manifest.json`.

Ground truth is the consumer-selected Product and Issue, mapped to 9 stable product labels (`harness/jevbench/tasks.py`). Consumers sometimes pick the wrong product, so agreement is a **lower bound** on fidelity to the narrative.

## Experiments

| Name | Kind | What it measures |
| --- | --- | --- |
| `choice_base` | choice (9 options) | Accuracy, top-label ECE, Brier/NLL; cross-fitted temperature and isotonic recalibration |
| `choice_shift3`, `choice_shift6` | choice | The same options cyclically shifted: flip rate, first-position probability lift, accuracy when averaging orderings |
| `choice_other` | choice (10 options) | **Label-set drift**: a catch-all option is appended. Measures flip rate, change in the auto-accepted set at τ = 0.5/0.7/0.9, and the τ needed to keep the same volume |
| `noul_debt_collection` | noul | Calibration of `jev_prob` (truth: product = debt collection) |
| `noul_incorrect_report` | noul | Calibration of `jev_prob` (truth: issue = incorrect information on report) |

Each experiment runs in a fresh database session with `jev_cache_clear()`, because pg-jev's per-session cache key does not include `jev.model` or `jev.api_url` (see `make cachecheck`).

## Usage

```bash
make up                 # build + start db, mock, sim
make upstream-test      # pg-jev's own regression suite at v0.2.1
make smoke              # README queries against the upstream mock
make test               # harness unit tests (metrics, sim contract)
make fetch              # 3,000-row sample → data/raw/cfpb_sample.jsonl (+ manifest)
make load N=2000        # → bench.complaints / bench.items
make bench              # BACKEND=sim by default; writes results/<run_id>/report.md + metrics.json
make cachecheck         # demonstrates the cross-backend cache reuse in one session
```

### Real Jev

```bash
export TYPESAFE_API_KEY=...        # never committed; passed to the bench container only
make bench BACKEND=jev             # prints the estimated spend and refuses without --yes
make bench BACKEND=jev ARGS=--yes  # 2,000 rows × 6 experiments ≈ $0.2–0.3 at list price; hard cap --max-usd 1.0
```

Other Jev-compatible servers (stuntd, laya-server):

```bash
docker compose run --rm bench run --backend stuntd --api-url http://host.docker.internal:8787/v1/systemone --analyze
```

## Reading the report

- **ECE** = count-weighted |accuracy − confidence| over 15 equal-width bins (equal-mass is also reported). Brackets are 95 % bootstrap intervals.
- **"after temperature / isotonic"** numbers are out-of-fold (5-fold cross-fit). They estimate what a calibration layer fitted on your own labels would achieve.
- **First-position probability lift** = how much probability an option gains when it is listed first, compared with the same option on the same row in other positions.
- On `sim`, the right answers are known in direction: it is over-confident (T = 0.5) and favours the first option (+0.6 logit). The harness should report ECE that drops after recalibration and a positive first-position lift. If it doesn't, the harness is wrong.
