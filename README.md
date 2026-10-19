**English** | [简体中文](README.zh-CN.md)

# Docket (working name)

[![CI](https://github.com/ElyasEbrahim/docket/actions/workflows/ci.yml/badge.svg)](https://github.com/ElyasEbrahim/docket/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**Durable, versioned, calibrated AI decisions for Postgres.** Declare a semantic decision once (*"is this complaint about debt collection?"*). Docket keeps the answer stored as data, versioned, calibrated against your own labels, and honest about its uncertainty, in any Postgres and with any decision model.

> **Status: Phase 1 has started.** The first piece of Docket works: [`docket check`](docket/README.md) measures how trustworthy an AI decision is on *your* table. The rest of the product (stored, versioned decisions) is not built yet. The repository also contains the design ([REPORT.md](REPORT.md), [ADRs](docs/adr/)) and the Phase 0 benchmark ([findings](docs/phase0/FINDINGS-jev-1.13.md)). Progress is tracked in [issues](https://github.com/ElyasEbrahim/docket/issues) and [milestones](https://github.com/ElyasEbrahim/docket/milestones).

## The problem

[pg-jev](https://github.com/realZachi/pg-jev) lets you filter rows in plain language, such as `WHERE jev(tickets, 'the customer threatens to cancel')`, using TypeSafe's Jev decision model. That's good for exploring. To rely on the answers in production, they need to be stable, comparable and trustworthy, and today they aren't:

- they disappear when the database session ends, so every session judges the whole table again;
- they change when someone adds a label option, or switches model or backend;
- they change when you simply ask again, or send the row alongside different rows;
- a score of `0.7` doesn't mean 70 %, and `count(*)` over AI labels has no error bar;
- they don't run on managed hosts like Supabase, Neon or RDS.

Model calls now cost roughly **$6–25 per million rows** (depending on text length and rows per request), so the bottleneck is no longer cost. It's whether people can trust and audit the answers.

## What Phase 0 measured

2,000 real consumer-complaint narratives, judged by jev-1.13.0 through pg-jev, for about $0.30 in API calls in total.

| Finding | Result |
| --- | --- |
| Scores are over-confident | 9-way choice ECE **0.089**; yes/no ECE **0.24–0.38** |
| ~100 labels fix most of it | Calibration on 100 labels removes **45–85 %** of the error |
| Asking again changes answers | **4.8 %** of rows change top answer across 3 identical runs |
| Neighbours change answers | Re-batching the same rows changes **~16.5 %** of answers (≈ 5× noise) |
| One row per request is better | Judging rows singly: **+2.4 pp** accuracy, +0.05 macro-F1, at 1.8× tokens |
| Adding an option moves answers | **2.5 %** of answers move to a new catch-all option |
| Scores are coarse | Probabilities come on a 0.01 grid with exact zeros |

Write-up for a general audience: [*Same row, different answer*](docs/notes/2026-10-same-row-different-answer.md). Details, methods and limits: [docs/phase0/FINDINGS-jev-1.13.md](docs/phase0/FINDINGS-jev-1.13.md).

## Try it on your own data: `docket check`

Point it at a table, the text to send, a question and some labels (an existing column, or a CSV you label by hand). It reports agreement, calibration, a threshold with a stated precision guarantee, consistency and cost. It's read-only, and no row text goes in the report.

```bash
python -m docket check --table public.tickets --key id --text subject,body \
  --kind choice --question "Which team should handle this ticket?" \
  --options billing,technical,security,sales --label-column team --yes
```

On two years of Kubernetes issues, routing to 10 teams (SIGs) agreed with the human labels **88.8 %** of the time. **90 % of issues could be auto-routed with precision ≥ 90 % guaranteed** at 95 % confidence ([write-up](docs/phase1/kubernetes-triage.md), [report](results/check-k8s-sig/report.md)). Full usage: [docket/README.md](docket/README.md).

## What Docket will be

1. **Stored decisions.** Answers live in an append-only ledger and a view you can join and index. New and changed rows are judged automatically, one row per request.
2. **Versions.** Changing the question, labels, model or batching creates a new version, which is compared with the old one before it replaces it.
3. **Calibration on your labels.** About 100–200 human labels per decision turn raw scores into probabilities that mean what they say.
4. **Honest numbers.** Thresholds with stated guarantees ("precision ≥ 95 %"), and counts with confidence intervals (prediction-powered inference).
5. **Runs anywhere.** Plain SQL plus an external worker, so no superuser or untrusted extension is needed. Works on Supabase, Neon and RDS.

Architecture and SQL sketch: [REPORT.md §4](REPORT.md#4-the-recommended-project-docket). Decisions so far: [docs/adr/](docs/adr/).

## Quick start: the Phase 0 harness

Requires Docker. Everything runs in containers.

```bash
make up            # Postgres 16 + pg-jev v0.2.1, pg-jev's mock API, a simulated backend
make test          # harness unit tests
make smoke         # pg-jev's README queries against the mock
make fetch load    # 2,000 CFPB complaint narratives (CC0 mirror) → Postgres
make bench         # all experiments on the simulated backend → results/<run_id>/report.md
```

To run against the real Jev API, copy `.env.example` to `.env`, add your TypeSafe key, then:

```bash
make bench BACKEND=jev ARGS=--yes   # prints the estimated spend; refuses anything over $1
```

More commands (determinism, learning curve, batch context): [harness/README.md](harness/README.md).

## Repository map

| Path | What |
| --- | --- |
| [REPORT.md](REPORT.md) | Project report: pg-jev teardown, research survey, candidates, design, evaluation plan, risks |
| [ROADMAP.md](ROADMAP.md) | Phased plan with exit criteria |
| [CHANGELOG.md](CHANGELOG.md) | What changed, by date |
| [docs/adr/](docs/adr/) | Architecture decision records |
| [docs/phase0/](docs/phase0/) | Phase 0 findings, status, draft upstream issue |
| [docs/notes/](docs/notes/) | Public write-ups |
| [docs/phase1/](docs/phase1/) | Phase 1 results (Kubernetes triage) |
| [docket/](docket/) | The product: `docket check` (and later the ledger) |
| [examples/](examples/) | Option files with descriptions for the example checks |
| [harness/](harness/) | Benchmark harness: `jevbench` CLI, simulated backend, tests |
| [results/](results/) | Benchmark reports from the runs cited in the findings |
| `docker-compose.yml`, `Makefile` | The benchmark stack and its commands |

## Sources

- [realZachi/pg-jev](https://github.com/realZachi/pg-jev), the Postgres extension this builds on (PostgreSQL License).
- winkrun, *不用向量索引，Postgres 也能做语义过滤：pg-jev 上手* (4 Oct 2026). Its list of pg-jev caveats shaped the design; the article isn't redistributed here.
- Full reference list: [REPORT.md § Sources](REPORT.md#sources).

## Contributing

This is a single-maintainer project. Issues and questions are welcome; pull requests are not accepted for now. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache-2.0](LICENSE). Copyright 2026 ElyasEbrahim.
