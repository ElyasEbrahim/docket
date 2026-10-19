# Contributing

Docket is a single-maintainer project. **Issues, questions and ideas are welcome. Pull requests are not accepted for now**, so please open an issue instead.

## How work is tracked

- Every change starts from an [issue](https://github.com/ElyasEbrahim/docket/issues), grouped into [milestones](https://github.com/ElyasEbrahim/docket/milestones) that match the phases in [ROADMAP.md](ROADMAP.md).
- Commits reference their issue: `Refs #12` while in progress, `Closes #12` in the commit that finishes it (GitHub then closes the issue and links it to the exact change).
- Notable changes go into [CHANGELOG.md](CHANGELOG.md) under the date.
- Labels: `phase-0`, `phase-1`, `research` (measurements), `upstream` (contributions to pg-jev and others), `outreach` (users and community), `bug`.

## Keeping docs in sync

- [README.md](README.md) and [README.zh-CN.md](README.zh-CN.md) must say the same thing. Change both in the same commit.
- A new measurement updates [docs/phase0/FINDINGS-jev-1.13.md](docs/phase0/FINDINGS-jev-1.13.md) and [docs/phase0/STATUS.md](docs/phase0/STATUS.md), and keeps its report under `results/<run_id>/`.
- A design change gets a new or updated record in [docs/adr/](docs/adr/).

## Running things

```bash
make test        # harness unit tests (no database or API needed)
make up          # the full Docker stack
make bench       # experiments on the simulated backend (free)
```

Paid runs against the real Jev API need a key in `.env` (see `.env.example`). They print an estimate, require `--yes`, and refuse anything above `--max-usd` (default $1). Record the cost in the issue or commit message.

## Secrets and data

- API keys live only in `.env`, which is gitignored. Never put a key in code, docs, issues or commit messages.
- Downloaded datasets stay in `data/raw/` (gitignored). Commit reports and metrics, not raw narratives.
- The harness is self-contained Python (numpy, psycopg, pyarrow); there is no linter. Use 4-space indentation.

## Reporting a problem

Use the issue templates: **Bug** for something broken in the harness, **Research** for a new measurement, **Task** for anything else. For anything security-related, such as a leaked key, open an issue without the sensitive details and ask for a private contact.
