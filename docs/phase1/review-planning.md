# Planning human review

*2026-10-22 · issue #20 · design: [ADR 0003](../adr/0003-human-labels-are-the-oracle.md) · method: probably approximately correct labels (Candès, Ilyas & Zrnic, 2025)*

A team that acts on an AI decision usually wants a promise about the whole column: *at most 5 % of these rows are wrong*. The cheapest way to get there is to let people check the rows the model is least sure of, and keep the model's answer for the rest. `pgdocket plan` tells you how many rows that is, with a guarantee.

```bash
pgdocket plan triage --max-error 0.05 --export review.csv
```

```
k8s_route: 300 judged rows · 80 random labels · the AI alone: 8.8 % wrong (at most 15.8 % with 95 % confidence)
 at most wrong    people review  the AI keeps
        10.0 %       29 ( 9.7 %)           271
         5.0 %      300 (100.0 %)             0  ←
         3.0 %     not provable  needs ≥ 99 random labels
         2.0 %     not provable  needs ≥ 149 random labels
         1.0 %     not provable  needs ≥ 299 random labels
to keep ≤ 5.0 % wrong, people must review every row: the labels can't yet vouch for any of the model's answers at this level
```

`--export` writes the review queue: the rows below the cut, least confident first, with their text and the model's answer.

## How it works

- **Confidence.** For each judged row, how sure the model is of the answer the view shows: its top probability, or for yes/no the probability of the answer given.
- **The cut.** People review rows below a cut. Once reviewed, a row is right (reviewers are assumed correct). The share of all rows that stay wrong is the share that is *kept and wrong*.
- **The bound.** With a uniform random sample of labels, that share is a proportion the labels estimate without bias. A one-sided Clopper–Pearson bound at 95 % applies to each cut.
- **The scan.** Lowering the cut keeps more rows, so the share kept and wrong can only grow. Cuts are tested from the safest down, and the scan stops at the first one whose bound exceeds ε. Because the share only grows, this needs no multiple-testing correction.
- **Too few labels.** Even with every labelled row right, n labels can only prove ε when n ≥ log α / log(1 − ε). That's 59 labels for 5 %, 99 for 3 % and 299 for 1 %. Below that, `plan` says how many to add.
- **Only random labels count.** Labels must be drawn at random from the judged rows (`label --sample`, or a CSV imported with `--random`). Hand-picked labels would bias the bound.

## Evidence

**Simulation (in CI).** On synthetic populations where less confident rows are more often wrong, the column's error exceeded ε in only 0.7–2.5 % of 400 trials per setting, against the 5 % allowed:

| ε | labels | failures |
| ---: | ---: | ---: |
| 3 % | 300 | 0.7 % |
| 5 % | 200 | 1.3 % |
| 10 % | 100 | 2.5 % |

The CI test fails above 7 %, which allows for simulation noise.

**Real model errors, no API calls** ([results/frontier-2026-10](../../results/frontier-2026-10/report.md) §4). The 500 Kubernetes and 500 CFPB issues judged by `pgdocket check` were treated as populations, with 1,000 random label draws each:

| | AI alone | target | review, if every label were known | review with 100 labels | with 200 labels | failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Kubernetes routing | 11.2 % wrong | 5 % | 19 % | 45 % | 36 % | 2.9 % / 2.2 % |
| CFPB product | 20.2 % wrong | 10 % | 24 % | 67 % | 46 % | 1.3 % / 1.9 % |

The guarantee costs about twice the review an omniscient planner would need at 200 labels, and less as labels grow.

**The live decision.** `k8s_route` is the 300 issues of the live replay, with 80 random labels. Every issue also has a human label, so the plan can be checked:
- **≤ 10 % target:** the plan reviews 29 issues (9.7 %), and the column is left **5.0 %** wrong. That's within the target. Knowing every label, no review would have been needed, since the AI alone is 8.7 % wrong.
- **≤ 5 % target:** the plan must review everything. Those same 29 reviews would in fact have reached exactly 5.0 %, but 80 labels can't prove it: two of the 56 labelled answers the model gave a score of 1.0 were wrong.

## Limits

- **Reviewers are assumed right.** In practice they make mistakes too.
- **The guarantee is for the rows judged now.** Rows judged later are covered only if they come from the same distribution. Re-plan as the table grows.
- **Random sampling only, for now.** The paper's importance-weighted version samples more labels where the model is unsure, which would need fewer labels. pgdocket would need to record each label's inclusion probability first, as ADR 0003 plans.
- **A column-level guarantee.** It says nothing about any single answer; for that, see precision per answer (#19).
