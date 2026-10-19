# Docket (working name)

**Migrations for AI decisions.** Declare a semantic decision once. Docket keeps it materialized, versioned, calibrated against your own labels, and statistically defensible, in any Postgres, with any decision backend.

> Status: **proposal / Phase 0 (validation)**. No code yet. Read [REPORT.md](REPORT.md) for the reasoning and research behind it.

## Why

[pg-jev](https://github.com/realZachi/pg-jev) lets you write `WHERE jev(tickets, 'the customer threatens to cancel')`. That works well for exploration, but the answers:

- disappear when the session ends (each pooled backend re-judges the whole table),
- become invalid when someone adds a label (*label-set drift*),
- can't be compared across backends (Jev, OpenAI Decisions, Laya),
- carry no guarantee: what does `0.7` mean, and how wrong is `count(*)`?
- don't run on Supabase, Neon or RDS (`plpython3u` + superuser).

Model calls now cost about **$6–7 per million rows**, so the bottleneck is **human trust**, not API spend. Docket applies per-task calibration, finite-sample threshold guarantees and prediction-powered inference to that problem, inside ordinary Postgres.

## Shape

- **Core:** plain SQL + PL/pgSQL schema (`docket.*`), installed like a migration, so no superuser is needed.
- **Worker:** external Python process (Docker / pip). It batches rows to decision backends, fits calibrators, selects guaranteed thresholds and runs shadow versions.
- **Backends:** TypeSafe Jev (direct or via OpenRouter), OpenAI Decisions API, any `/v1/systemone`-compatible server (stuntd, laya-server), mock.

See [REPORT.md §4](REPORT.md#4-the-recommended-project-docket) for the SQL API sketch and architecture.

## Repository map

| Path | What |
| --- | --- |
| [REPORT.md](REPORT.md) | Full project report: pg-jev teardown, current research, candidates evaluated, design, evaluation, risks |
| [ROADMAP.md](ROADMAP.md) | Phased checklist with exit criteria |
| [docs/adr/](docs/adr/) | Architecture decision records |
| [harness/](harness/) | Phase 0 benchmark harness: pg-jev v0.2.1 in Docker, upstream mock, simulated backend, `jevbench` CLI |
| `docker-compose.yml`, `Makefile` | The Phase 0 stack and its commands |
| `results/<run_id>/` | Benchmark reports (`report.md`, `metrics.json`) |
| `pg&jev.pdf` | Source article (winkrun, 4 Oct 2026) |

## Phase 0 quick start

```bash
make up            # Postgres 16 + pg-jev v0.2.1, upstream mock API, simulated backend
make smoke         # pg-jev README queries against the mock
make fetch load    # CFPB complaint narratives (CC0 mirror) → Postgres
make bench         # all experiments on the simulated backend → results/<run_id>/report.md
```

With a TypeSafe key: `TYPESAFE_API_KEY=... make bench BACKEND=jev ARGS=--yes`. It prints the estimated spend first and refuses anything over $1. Details are in [harness/README.md](harness/README.md).

## License

[Apache-2.0](LICENSE). Copyright 2026 ElyasEbrahim.
