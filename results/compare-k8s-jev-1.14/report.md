# Comparing `k8s_route` v1 (active) with v3 (shadow)

*2026-10-22T11:52:44+00:00* · 300 rows compared

## Verdict: **no clear difference**

- The new version changes 1.0 % of answers, against 1.0 % when the current one is asked again: the difference [-1.0 %, 1.0 %] is within run-to-run noise.
- The versions disagree on 3 of 300 rows, all labelled: the current one was right on 1, the new one on 2, neither on 0 (exact sign test p = 1.00). Accuracy difference: +0.3 pp [-0.7 pp, +1.7 pp]. No difference is detectable: the new version is between 0.7 pp less and 1.7 pp more accurate.
- Auto-accept at ≥ 90 % precision (95 % confidence), each version calibrated on the same 80 labels as `calibrate` would use: current 78.3 % of compared rows, new none (no threshold reaches it).
- With 80 labels, whether a guarantee can be certified at all is partly chance: on Kubernetes routing, 80 random labels certified 90 % in only 54–66 % of draws. Label more rows (150–200) before reading this as a difference between the versions.
- Tokens per row: 1024 → 1024 (+0 %).

## What changed in the spec

| | v1 (active) | v3 (shadow) |
| --- | --- | --- |
| model | jev-1.13.0 | jev-1.14.0 |

## Answers that change

| | share of rows |
| --- | ---: |
| new version vs current | 1.0 % |
| current asked again (noise) | 1.0 % |
| due to the change | 0.0 % [-1.0 %, 1.0 %] |

| current answer | new answer | rows |
| --- | --- | ---: |
| testing | scheduling | 1 |
| apps | api-machinery | 1 |
| testing | node | 1 |

## Accuracy

| | current | new | difference |
| --- | ---: | ---: | ---: |
| on 80 random-sample labels | 91.2 % | 92.5 % | +1.3 pp |
| right where they disagree (3 of 3 labelled) | 1 | 2 | neither: 0 · sign test p = 1.00 |
| **difference, 95 % interval** (disagreements) | | | +0.3 pp [-0.7 pp, +1.7 pp] |

## Calibration on the same 80 labels (as `calibrate` and `promote` would use them)

| | current | new |
| --- | ---: | ---: |
| calibration error, raw → calibrated | 0.095 → 0.030 | 0.067 → 0.050 |
| threshold for ≥ 90 % precision (95 % confidence) | 0.968 | none |
| compared rows it would auto-accept | 78.3 % | – |

## Answer counts in the sample

| answer | current | new |
| --- | ---: | ---: |
| node | 102 | 103 |
| api-machinery | 74 | 75 |
| scheduling | 58 | 59 |
| network | 14 | 14 |
| apps | 11 | 10 |
| storage | 11 | 11 |
| auth | 10 | 10 |
| testing | 10 | 8 |
| cli | 7 | 7 |
| instrumentation | 3 | 3 |

Intervals are 95 % paired bootstrap intervals over rows. "Noise" is the current version re-asked on the same rows (probe judgments), so only the excess over it is attributable to the change. Where both versions give the same answer they are equally right, so the accuracy difference depends only on the rows where they disagree.
