# `docket check`

**How trustworthy is an AI decision on your table?** Point `docket check` at a Postgres table, the text column(s) to send, a question, and some labels. It samples rows, asks the model one row per request, and writes a report:

- **agreement** with your labels, per option, and the most common disagreements;
- **calibration**: how far the model's confidence is from reality, before and after a one-parameter calibrator fitted on your labels;
- **a threshold with a guarantee**: which answers you can accept automatically with precision ≥ your target at 95 % confidence, and a table of what each target allows;
- **consistency** (optional): how many answers change if you ask again, or send 20 rows per request;
- **cost** for this check and projected for the whole table.

It is **read-only** on your database. It talks to any `/v1/systemone`-compatible backend (TypeSafe Jev, stuntd, laya-server) directly, so pg-jev doesn't need to be installed; managed Postgres works. **No row text appears in the report.** Per-row answers are saved next to it, keyed by your primary key.

## Usage

```bash
pip install "psycopg[binary]" numpy          # or use the repo's Docker image
export DATABASE_URL=postgresql://...          # your database (read-only access is enough)
export TYPESAFE_API_KEY=...                   # for the Jev backend

# A choice question, with labels already in a column
python -m docket check \
  --table public.tickets --key id --text subject,body \
  --kind choice --question "Which team should handle this ticket?" \
  --options billing,technical,security,sales --label-column team \
  --sample 300 --repeat 100 --batch-test 100 --yes

# A yes/no question
python -m docket check \
  --table public.tickets --key id --text subject,body \
  --kind noul --question "the customer threatens to cancel" \
  --label-column churned --positive true --yes
```

**No labels yet?** Export a sample, label it in a spreadsheet, and read it back:

```bash
python -m docket check ... --export-sample sample.csv     # writes key, text columns, empty label
python -m docket check ... --label-file sample.csv --yes  # after filling in the label column
```

**Re-analyse without paying again**, for example with another precision target:

```bash
python -m docket report results/check-<timestamp> --precision-target 0.85
```

## Options worth knowing

| Option | Default | Meaning |
| --- | --- | --- |
| `--options-file` | – | JSON list of `{"name", "description"}`. The model sees `name: description`; labels must match `name`. Descriptions help (see `examples/`). |
| `--sample` | 300 | Labeled rows to check. 100–200 already show most of the calibration picture; more labels give tighter guarantees. |
| `--precision-target` | 0.9 | Target for the guaranteed threshold. The report also shows 95 / 90 / 85 / 80 / 75 / 70 %. |
| `--repeat N` | 0 | Ask again for N rows: how stable are the answers? |
| `--batch-test N` | 0 | Send N rows 20 per request: does batching change answers? |
| `--batch-size` | 1 | Rows per request for the main run. 1 is more accurate; see the findings. |
| `--backend` | `jev` | `jev`, `sim` (the harness simulator) or any `/v1/systemone` URL. |
| `--max-usd` | 1.0 | Refuses checks estimated above this. Paid checks also need `--yes`. |
| `--where` | – | Extra SQL filter, e.g. `"created_at > '2026-01-01'"`. |

## How the guarantee works

Thresholds are tested from strictest to loosest. Each candidate accepts a fixed share of rows (5 %, 10 %, …), chosen from the scores, not the labels. The chosen threshold is the loosest one whose precision passes a one-sided Clopper–Pearson test at 95 %, stopping at the first failure. This fixed-sequence procedure keeps the chance of *any* false claim at 5 % without a multiple-testing correction.

It assumes the labeled sample is representative of the rows the threshold will be applied to. If the data drifts, run the check again.

## Example reports

Real data, real model (jev-1.13.0), October 2026:

- [Kubernetes issues → which SIG should handle it](../results/check-k8s-sig/report.md): 88.8 % agreement; 90 % of issues can be auto-routed with precision ≥ 90 % guaranteed.
- [Kubernetes issues → is it a feature request?](../results/check-k8s-feature/report.md): AUROC 0.97; 80 % precision catches 82 % of feature requests.
- [CFPB complaints → which financial product?](../results/check-cfpb-product/report.md): reproduces the Phase 0 benchmark (79.8 % vs 79.3 %).

Write-up: [docs/phase1/kubernetes-triage.md](../docs/phase1/kubernetes-triage.md).
