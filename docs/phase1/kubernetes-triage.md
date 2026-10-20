# `pgdocket check` on a real triage workload: Kubernetes issues

*2026-10-19 · issues #11 and #12*

No real users have been reached yet (see [ROADMAP](../../ROADMAP.md)). As the closest stand-in, this uses a real team's real triage data: two years of issues from kubernetes/kubernetes, with the routing (`sig/*`) and type (`kind/*`) labels that maintainers and authors applied. It's public text with human labels, and it's the scenario pgdocket targets ("which team should handle this?"). It is still *not* a user: nobody chose the question, the threshold or the trade-offs for their own needs.

## Data

| | |
| --- | --- |
| Source | kubernetes/kubernetes issues created 2024-07 → 2026-06, via the GitHub API (`python -m jevbench.ghissues`) |
| Issues | 3,884; 2,816 with exactly one SIG label; 3,014 with exactly one kind label |
| Text sent | title + body (body truncated to 2,000 characters) |
| Table | `demo.k8s_issues` (`jevbench load-github`), read by `pgdocket check` like any user table |
| Raw text | kept in `data/raw/` (gitignored). Issue text belongs to its authors, and only aggregates and keyed answers are committed |

Tasks:
- **Routing (choice):** "Which Kubernetes SIG should handle this issue?" over the 10 largest SIGs (2,550 issues), each option with a one-line description ([examples/k8s_sig_options.json](../../examples/k8s_sig_options.json)).
- **Type (yes/no):** "the issue asks for a new feature or enhancement, rather than reporting a problem". Truth: `kind/feature` (23.2 % of the 3,014 issues with one kind label; 21.6 % of the sample).

Each check: 500 labeled issues, one row per request, plus 100 re-asked and 100 sent 20 per request. jev-1.13.0.

## Results

| | SIG routing | Feature request? | CFPB product (validation) |
| --- | ---: | ---: | ---: |
| Agreement / ranking | **88.8 %** accuracy [86.0, 91.4], macro-F1 0.83 | **AUROC 0.966** [0.945, 0.984] | 79.8 % (Phase 0: 79.3 %) |
| Calibration error, raw → calibrated | 0.073 → **0.029** | 0.037 → **0.013** | 0.133 → 0.037 |
| Guaranteed auto-accept (95 % confidence) | **90 % precision on 90 % of issues** | 80 % precision catching 82 % of feature requests; 85 % precision catching 65 % | 80 % precision on 85 % of complaints |
| Answers changed when asked again | **1 %** (of 100) | 1 % (of 100) | – |
| Answers changed at 20 rows per request | **15 %** (of 100); accuracy 88 → 80 % | 8 % (of 100) | – |
| Tokens per row · per million rows | 1,019 · $43 | 839 · $35 | 569 · $24 |
| Cost of the check | $0.029 | $0.024 | $0.012 |

Reports: [SIG routing](../../results/check-k8s-sig/report.md) · [feature request](../../results/check-k8s-feature/report.md) · [CFPB validation](../../results/check-cfpb-product/report.md).

## What this adds to Phase 0

1. **The tool measures what the benchmark measured.** On the same CFPB rows, `pgdocket check` gives 79.8 % accuracy against 79.3 % in Phase 0, with the same calibration error before and after (within noise) and the same cost per row.
2. **Routing works well on technical text.** Ten SIGs with one-line descriptions: 88.8 % agreement with the labels people applied. The largest groups (node, api-machinery, scheduling, network, storage) are 86–92 % recall. Small or fuzzy groups are weaker: auth 59 %, apps 70 %, and "testing" is over-assigned with 40 % precision.
3. **A guarantee people can use:** a team could auto-route 90 % of incoming issues with precision ≥ 90 % at 95 % confidence, and send 10 % to a person. That's the kind of statement pgdocket is meant to produce.
4. **Batching hurts again, on a second dataset.** 20 rows per request changed 15 % of routing answers and cost 8 points of accuracy on the 100 tested issues. That supports ADR 0002's one-row-per-request default.
5. **One row per request looks much more stable.** Only 1 % of answers changed when asked again, against 2.9–3.8 % between batched runs on CFPB. This is from 100 rows on a different dataset, so it's an indication, not yet a measurement.
6. **Calibration needs differ by task.** Routing was over-confident mostly because of exact-zero probabilities: clamping them did most of the work, and the fitted temperature was 1.00. The yes/no question was already fairly well calibrated (0.037).
7. **Cost depends on text length and option descriptions:** $24–43 per million rows here. That's still small next to the cost of a person reading the same rows.

## Limits

- Labels are what authors and maintainers applied, sometimes via bot commands; some issues are mislabelled or genuinely span several SIGs (only single-SIG issues are used).
- 500 labels per task; per-option numbers for small SIGs rest on 9–23 issues.
- One model version; stability and batching tests use 100 rows each.
- A public, technical, English-language project is not a customer's ticket queue.

## Reproduce

```bash
PYTHONPATH=harness python3 -m jevbench.ghissues            # needs the GitHub CLI, signed in (~2 min)
docker compose run --rm bench load-github
docker compose run --rm --entrypoint python bench -m pgdocket check \
  --table demo.k8s_issues --key number --text title,body --kind choice \
  --question "Which Kubernetes SIG (special interest group) should handle this issue?" \
  --options-file examples/k8s_sig_options.json --label-column sig \
  --sample 500 --repeat 100 --batch-test 100 --yes --out results/check-k8s-sig
```

Re-analyse the committed answers without API calls: `pgdocket report results/check-k8s-sig`.
