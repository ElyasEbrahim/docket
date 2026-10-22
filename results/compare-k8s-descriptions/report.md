# Comparing `k8s_route` v1 (active) with v2 (shadow)

*2026-10-22T11:07:13+00:00* · 300 rows compared

## Verdict: **no clear difference**

- The new version changes 4.3 % of answers, against 1.0 % when the current one is simply asked again: 3.3 % more [1.0 %, 6.0 %] are due to the change.
- The versions disagree on 13 of 300 rows, all labelled: the current one was right on 8, the new one on 2, neither on 3 (exact sign test p = 0.11). Accuracy difference: -2.0 pp [-4.0 pp, +0.0 pp]. No difference is detectable: the new version is between 4.0 pp less and 0.0 pp more accurate.
- Auto-accept at ≥ 90 % precision (95 % confidence), each version calibrated on the same random labels: current 78.3 % of compared rows, new 74.7 %.
- Tokens per row: 1024 → 884 (-14 %). Promote for the saving only if losing up to 4.0 pp of accuracy is acceptable.

## What changed in the spec

| | v1 (active) | v2 (shadow) |
| --- | --- | --- |
| options | 10 options, 10 with descriptions | 10 options, 0 with descriptions |
| descriptions changed | 10 options | api-machinery, apps, auth, cli, instrumentation, network, node, scheduling, storage, testing |

## Answers that change

| | share of rows |
| --- | ---: |
| new version vs current | 4.3 % |
| current asked again (noise) | 1.0 % |
| due to the change | 3.3 % [1.0 %, 6.0 %] |

| current answer | new answer | rows |
| --- | --- | ---: |
| node | storage | 2 |
| api-machinery | scheduling | 2 |
| node | api-machinery | 2 |
| testing | storage | 1 |
| auth | node | 1 |
| api-machinery | storage | 1 |
| api-machinery | node | 1 |
| apps | api-machinery | 1 |

## Accuracy

| | current | new | difference |
| --- | ---: | ---: | ---: |
| on 80 random-sample labels | 91.2 % | 91.2 % | +0.0 pp |
| right where they disagree (13 of 13 labelled) | 8 | 2 | neither: 3 · sign test p = 0.11 |
| **difference, 95 % interval** (disagreements) | | | -2.0 pp [-4.0 pp, +0.0 pp] |

## Calibration on the same 80 random labels

| | current | new |
| --- | ---: | ---: |
| calibration error, raw → calibrated | 0.095 → 0.030 | 0.074 → 0.052 |
| threshold for ≥ 90 % precision (95 % confidence) | 0.968 | 0.948 |
| compared rows it would auto-accept | 78.3 % | 74.7 % |

## Answer counts in the sample

| answer | current | new |
| --- | ---: | ---: |
| node | 102 | 101 |
| api-machinery | 74 | 73 |
| scheduling | 58 | 60 |
| network | 14 | 14 |
| storage | 11 | 15 |
| apps | 11 | 10 |
| auth | 10 | 9 |
| testing | 10 | 7 |
| cli | 7 | 8 |
| instrumentation | 3 | 3 |

Intervals are 95 % paired bootstrap intervals over rows. "Noise" is the current version re-asked on the same rows (probe judgments), so only the excess over it is attributable to the change. Where both versions give the same answer they are equally right, so the accuracy difference depends only on the rows where they disagree.
