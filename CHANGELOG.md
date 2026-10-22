# Changelog

Notable changes, newest first. Dates are UTC; `#n` refers to issues in this repository.

## 2026-10-22

### Added (version comparison, #15)
- **`pgdocket revise` / `compare` / `backfill` / `promote` / `retire` / `versions`.** `revise` adds a shadow version (new question, options, model or backend) without changing any answer. `compare` judges a sample under the shadow version and re-asks the active one on the same rows, then reports:
  - the answers changed beyond that run-to-run noise, with a paired bootstrap interval, and the most common moves;
  - the accuracy difference;
  - tokens per row;
  - a verdict.
- **Only disagreements need labels.** Where both versions agree they are equally right, so `compare --export-disagreements` lists the unlabelled rows where they disagree. Once those are labelled, the accuracy difference is known on the whole sample. The report adds an exact sign test.
- **`promote` is gated.** It refuses while the shadow version hasn't answered every row (`--force`). `retire` stops a shadow version from judging new rows.
- Migration `003`:
  - *probe* judgments: `judgment.purpose` and `queue.purpose`; probes never become current and views ignore them;
  - `docket.compare_enqueue()`, `docket.retire()`, `docket.create_view()`;
  - `version.comparison` and `version.promoted_at`;
  - `docket.status` gains `probes_queued` and `shadow_versions`.
- **Experiment on Kubernetes routing ($0.024).**
  - Dropping the SIG descriptions saved 14 % of tokens and moved 3.3 % [1.0, 6.0] of answers beyond noise.
  - 80 random labels showed no difference. Labelling the 10 remaining disagreements (90 labels) gave the same answer as all 300 human labels: v1 right 8 times, v2 twice, −2.0 pp [−4.0, 0.0], sign test p = 0.11. The descriptions stay; v2 was retired.
  - `jevbench comparevalidate` checks the verdict against every label; write-up in `docs/phase1/versions.md`.

### Changed
- Re-labelling a row that was drawn at random keeps it in the random sample (`label.sampling` records how the row was chosen).
- Labels may name an option of any version still in use, such as one only a shadow version has.

## 2026-10-20

### Added (counts with error bars, #14)
- **`pgdocket estimate` / `docket.estimate()`:** how many judged rows truly have each answer, with a confidence interval. It uses prediction-powered inference (PPI++, power-tuned) on the model's answers plus a random sample of labels, and reports the labels-only interval for comparison, a `reliable` flag (≥ 10 labels with and without the answer) and notes. No interval when the labels contain no example on one side.
- Migration `002`: `docket.label.sampling` (`random` / `all` / `manual`); `docket.norm_ppf()`. `pgdocket label --sample` records random samples, `--random` marks a CSV as random, and `--positive` normalises yes/no labels to `yes` / `no` at import.
- Python estimator (`pgdocket/estimate.py`), with coverage tests in CI, plus integration tests checking that SQL and Python agree to 1e-9.
- `jevbench ppivalidate`: on 500 real Jev judgments with known labels, intervals held 98–100 % when reliable and were 30–50 % narrower than labels alone (`results/ppi-validation/`, `docs/phase1/counts.md`).

### Changed
- **The project is now called pgdocket (#8).** "docket" clashes with the `pydocket` package, which installs a `docket` module. Python package, command (`pgdocket …`) and GitHub repository (`ElyasEbrahim/pgdocket`; the old URL redirects) are renamed. The database schema keeps the short name `docket`, as `pg_cron` uses `cron`.

### Added
- **Packaging (v0.1.0a1):** `pyproject.toml` with the `pgdocket` command and the SQL migration bundled; `pip install "git+https://github.com/ElyasEbrahim/pgdocket"` works now. A `Dockerfile` for the worker image (non-root). `pgdocket --version`.
- **5-minute quickstart** (`examples/quickstart/`): Postgres + worker + 60 synthetic tickets; install → create → live judging → labels → calibration → `auto`. Tested end to end on Jev (~$0.001).
- **Release workflow** (`.github/workflows/release.yml`, on `v*` tags only): PyPI via trusted publishing, image to `ghcr.io/elyasebrahim/pgdocket`, GitHub pre-release. Setup in `docs/RELEASING.md`.
- **The ledger (#13).** Migration `001`: decisions, versions, an append-only judgment ledger, `current`, `queue`, `label`. Insert and update triggers (only when judged columns change; `SECURITY DEFINER`, so app roles need no grants). A per-decision view `docket.v_<name>` with status, answer, calibrated confidence and `auto`. Also `create_decision`, `backfill`, `revise`, `promote`, `drop_decision` and a `docket.status` view.
- **Worker:** claim with lease and token (`FOR UPDATE SKIP LOCKED`), skip unchanged input, one row per request, ledger + current + dequeue in one transaction, back-off and dead-letter, LISTEN/NOTIFY, spend cap.
- **Calibration in the database:** `docket label` (column or CSV), `docket calibrate` (floored temperature or Platt, guaranteed threshold), applied at read time by `docket.calibrated()`, which a test checks against the Python version exactly.
- CLI: `install`, `create`, `worker`, `label`, `calibrate`, `status`, `drop`.
- Integration tests (10) on PostgreSQL 14–18 in CI, as a non-superuser with an unprivileged app role; `make itest`.
- Demos: 100,000-row scale test (simulator) and a live Kubernetes replay on Jev (`jevbench replay`). Write-up: `docs/phase1/ledger.md`. ADR 0004.

### Fixed
- `pgdocket check` recommended calibration even when, with few labels, it didn't improve the error; it now says to label more.
- The backend client created a thread pool per call, so connections were never reused; live decision latency fell from 3.9 s to 0.7 s at the median once fixed.
- The simulator gave every non-CFPB row the same answer (it keyed on a `narrative` field only).

## 2026-10-19

### Added
- **`docket check` (#12)**, the first piece of the product: samples a Postgres table (read-only), judges rows one per request against any `/v1/systemone` backend, and reports agreement, calibration (one-parameter calibrators, zeros clamped), a precision threshold with a 95 % guarantee (Clopper–Pearson, fixed-sequence testing), a table of what each precision target allows, consistency (re-ask and batching) and cost. Labels come from a column or a hand-labelled CSV (`--export-sample` / `--label-file`). `docket report` re-analyses saved answers without API calls.
- **Kubernetes triage scenario (#11)**: 3,884 issues (2024-07 → 2026-06) with human SIG and kind labels, fetched with `jevbench.ghissues` and loaded into `demo.k8s_issues`. Results: 88.8 % routing agreement; 90 % of issues auto-routable at ≥ 90 % precision (guaranteed); 20 rows per request changed 15 % of answers. Write-up: `docs/phase1/kubernetes-triage.md`.
- `docket/` package; `docket.metrics` (moved from the harness, which keeps an alias) with Clopper–Pearson bounds and threshold selection.
- Technical note *Same row, different answer* (`docs/notes/`), the general-audience write-up of Phase 0 (#2).
- **Batch size 1 (#10).** Judging one row per request: +2.4 pp accuracy [0.9, 3.8], +0.05 macro-F1, at 1.8× tokens. ADR 0002 now defaults to one row per request. Findings §10.
- `jevbench run --batch-size` and `jevbench batchsize`.
- **Batch-context check (#3).** Re-batching the same 2,000 rows changed the top answer for ~16.5 % of rows, against ~3 % run-to-run noise (+13.6 pp [13.2, 14.1]), with a same-day control. Findings §9.
- `jevbench reorder [--seed | --restore]` and `jevbench batchcontext`, with a unit test.
- Apache-2.0 license.
- Chinese README (`README.zh-CN.md`), `CONTRIBUTING.md`, this changelog, `.env.example`, GitHub Actions CI (harness tests + compose validation) and issue templates.
- Issues #1–#9 and milestones for Phase 0 and Phase 1.

### Changed
- README rewritten: current status, Phase 0 results, quick start, repository map, language switch.
- ADR 0002 notes that judgments depend on batch composition (open question for Phase 1).

### Fixed
- Stale statements in the harness README (data source), status and roadmap (test counts, simulator numbers).
- The README pointed to a source PDF that is not in the repository; it now cites the article instead.

## 2026-10-18

### Added
- **Determinism check.** Identical requests change the top answer for 4.8 % of rows across three runs. Findings §7.
- **Label learning curve.** ~100 labels remove 45–85 % of calibration error; one-parameter calibrators beat isotonic up to 500 labels. Findings §8.
- `jevbench determinism`, `jevbench curve`, `make curve`; `SIM_LOG` request logging in the simulated backend.

### Changed
- Corrected the option-order and label-drift findings: part of those flips is run-to-run noise.
- ADR 0003: default to parametric calibration (floored temperature / Platt); isotonic once ≥ 1,000 labels exist.

### Fixed
- The `sim` service ran the copy of the code baked into its image instead of the mounted code.

## 2026-10-17

### Added
- Project proposal ([REPORT.md](REPORT.md)), [ROADMAP.md](ROADMAP.md) and ADRs 0001–0003.
- Phase 0 benchmark harness: pg-jev v0.2.1 in Docker, pg-jev's mock API, a simulated backend that is calibrated by construction, and the `jevbench` CLI with six experiments and a report generator.
- First real run on jev-1.13.0 (2,000 CFPB narratives, ≈ $0.146). Findings §1–§6.
- Draft upstream issue for pg-jev's cache key, which ignores `jev.model` and `jev.api_url`.
