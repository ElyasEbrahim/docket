# Changelog

Notable changes, newest first. Dates are UTC; `#n` refers to issues in this repository.

## 2026-10-19

### Added
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
