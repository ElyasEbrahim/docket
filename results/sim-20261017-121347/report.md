# Benchmark run `sim-20261017-121347`

> **Synthetic backend.** These numbers describe the harness, not a real model. The `sim` backend derives its answers from the labels with planted flaws (see `harness/jevbench/sim.py`); `mock` is pg-jev's deterministic test double.

- Backend: `sim` · model `jev-sim` · endpoint `http://sim:8787/v1/systemone`
- Rows: 2000 CFPB complaint narratives · started 2026-10-17 12:13:47.251507+00:00 · finished 2026-10-17 12:13:52.515043+00:00
- Ground truth: consumer-selected Product / Issue (noisy; agreement is a lower bound on fidelity)

## Headline numbers

- **Product choice (9 options):** accuracy 89.9 % [88.6 %, 91.2 %], top-label ECE 0.059 [0.049, 0.072] → 0.012 after temperature scaling (T = 1.99, zeros floored at 4.99999e-07) and 0.019 after isotonic (both cross-fitted).
- **Probability resolution:** smallest non-zero probability 9.99998e-07; 10,353 exact zeros; the labeled class gets exactly 0 on 1 rows. Unfloored temperature scaling fits T = 2.13 and moves ECE to 0.013.
- **Option order:** 4.1 % [3.3 %, 4.9 %] of rows change their answer across 3 cyclic orderings. Listing an option first lifts its probability by 1.5 pp [1.3, 1.6]; within-class recall changes by 2.4 pp [1.6, 3.1] when the true class is listed first. Averaging orderings: accuracy 89.9 % → 91.0 % at 3× cost.
- **Label-set drift (adding "other financial product or service"):** 0.1 % of top-1 answers change (0.1 % move to the new option); at τ = 0.7 the auto-accepted set goes 1890 → 1888 rows (Jaccard 1.00). Keeping the same volume needs τ ≈ 0.70.
- **noul_debt_collection:** AUROC 0.967 [0.957, 0.977], ECE 0.034 [0.028, 0.045] → 0.013 isotonic / 0.016 Platt (cross-fitted).
- **noul_incorrect_report:** AUROC 0.966 [0.957, 0.974], ECE 0.042 [0.035, 0.055] → 0.019 isotonic / 0.017 Platt (cross-fitted).

## Sample

| product | rows |
| --- | ---: |
| credit reporting | 1248 |
| debt collection | 239 |
| credit card | 142 |
| checking or savings account | 124 |
| mortgage | 110 |
| money transfer or virtual currency | 39 |
| vehicle loan or lease | 38 |
| student loan | 36 |
| payday, title, or personal loan | 24 |

## Cost and latency

| experiment | seconds | requests | input tokens | est. cost (USD) |
| --- | ---: | ---: | ---: | ---: |
| choice_base | 0.4 | 100 | 619,488 | 0.0260 |
| choice_other | 1.3 | 100 | 641,488 | 0.0269 |
| choice_shift3 | 1.2 | 100 | 619,488 | 0.0260 |
| choice_shift6 | 1.2 | 100 | 619,488 | 0.0260 |
| noul_debt_collection | 0.4 | 100 | 474,556 | 0.0199 |
| noul_incorrect_report | 0.4 | 100 | 474,613 | 0.0199 |

## `choice_base`

Question: *Which financial product is this consumer complaint about?*

Options (in order): credit reporting, debt collection, mortgage, credit card, checking or savings account, student loan, money transfer or virtual currency, vehicle loan or lease, payday, title, or personal loan

| metric | value |
| --- | ---: |
| n | 2000 |
| accuracy | 89.9 % [88.6 %, 91.2 %] |
| macro-F1 | 0.777 |
| mean confidence | 0.958 |
| ECE (15 equal-width bins) | 0.059 [0.049, 0.072] |
| ECE (15 equal-mass bins) | 0.059 |
| Brier / NLL | 0.159 / 0.423 |
| smallest non-zero probability / exact zeros | 9.99998e-07 / 10,353 |
| rows where the labeled class has probability 0 | 1 |
| ECE after temperature (T=1.99, floor 4.99999e-07) | 0.012 |
| ECE after temperature, unfloored (T=2.13) | 0.013 |
| ECE after isotonic | 0.019 |
| corr(reported confidence, max prob) | 1.000 |

| option | support | predicted | recall | precision |
| --- | ---: | ---: | ---: | ---: |
| credit reporting | 1248 | 1334 | 98.1 % | 91.8 % |
| debt collection | 239 | 221 | 83.3 % | 90.0 % |
| mortgage | 110 | 98 | 80.0 % | 89.8 % |
| credit card | 142 | 126 | 78.9 % | 88.9 % |
| checking or savings account | 124 | 114 | 75.0 % | 81.6 % |
| student loan | 36 | 27 | 58.3 % | 77.8 % |
| money transfer or virtual currency | 39 | 31 | 59.0 % | 74.2 % |
| vehicle loan or lease | 38 | 32 | 60.5 % | 71.9 % |
| payday, title, or personal loan | 24 | 17 | 62.5 % | 88.2 % |

Reliability (raw):

| bin | n | mean confidence | observed accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.3–0.4 | 6 | 0.382 | 0.500 | +0.118 |
| 0.4–0.5 | 20 | 0.462 | 0.300 | -0.162 |
| 0.5–0.6 | 39 | 0.550 | 0.410 | -0.140 |
| 0.6–0.7 | 45 | 0.648 | 0.444 | -0.203 |
| 0.7–0.8 | 53 | 0.752 | 0.623 | -0.129 |
| 0.8–0.9 | 87 | 0.856 | 0.644 | -0.213 |
| 0.9–1.0 | 1750 | 0.994 | 0.951 | -0.043 |

## `choice_other`

Question: *Which financial product is this consumer complaint about?*

Options (in order): credit reporting, debt collection, mortgage, credit card, checking or savings account, student loan, money transfer or virtual currency, vehicle loan or lease, payday, title, or personal loan, other financial product or service

| metric | value |
| --- | ---: |
| n | 2000 |
| accuracy | 89.8 % [88.5 %, 91.1 %] |
| macro-F1 | 0.777 |
| mean confidence | 0.957 |
| ECE (15 equal-width bins) | 0.059 [0.049, 0.071] |
| ECE (15 equal-mass bins) | 0.059 |
| Brier / NLL | 0.159 / 0.424 |
| smallest non-zero probability / exact zeros | 9.99998e-07 / 12,005 |
| rows where the labeled class has probability 0 | 1 |
| ECE after temperature (T=1.96, floor 4.99999e-07) | 0.010 |
| ECE after temperature, unfloored (T=2.10) | 0.013 |
| ECE after isotonic | 0.018 |
| corr(reported confidence, max prob) | 1.000 |

| option | support | predicted | recall | precision |
| --- | ---: | ---: | ---: | ---: |
| credit reporting | 1248 | 1333 | 98.0 % | 91.7 % |
| debt collection | 239 | 221 | 83.3 % | 90.0 % |
| mortgage | 110 | 98 | 80.0 % | 89.8 % |
| credit card | 142 | 126 | 78.9 % | 88.9 % |
| checking or savings account | 124 | 114 | 75.0 % | 81.6 % |
| student loan | 36 | 27 | 58.3 % | 77.8 % |
| money transfer or virtual currency | 39 | 31 | 59.0 % | 74.2 % |
| vehicle loan or lease | 38 | 32 | 60.5 % | 71.9 % |
| payday, title, or personal loan | 24 | 17 | 62.5 % | 88.2 % |
| other financial product or service | 0 | 1 | – | 0.0 % |

Reliability (raw):

| bin | n | mean confidence | observed accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.3–0.4 | 6 | 0.379 | 0.500 | +0.121 |
| 0.4–0.5 | 21 | 0.462 | 0.286 | -0.177 |
| 0.5–0.6 | 39 | 0.552 | 0.410 | -0.141 |
| 0.6–0.7 | 46 | 0.648 | 0.457 | -0.192 |
| 0.7–0.8 | 54 | 0.750 | 0.611 | -0.139 |
| 0.8–0.9 | 86 | 0.857 | 0.651 | -0.206 |
| 0.9–1.0 | 1748 | 0.994 | 0.951 | -0.043 |

## `choice_shift3`

Question: *Which financial product is this consumer complaint about?*

Options (in order): credit card, checking or savings account, student loan, money transfer or virtual currency, vehicle loan or lease, payday, title, or personal loan, credit reporting, debt collection, mortgage

| metric | value |
| --- | ---: |
| n | 2000 |
| accuracy | 90.5 % [89.2 %, 91.7 %] |
| macro-F1 | 0.784 |
| mean confidence | 0.954 |
| ECE (15 equal-width bins) | 0.050 [0.042, 0.063] |
| ECE (15 equal-mass bins) | 0.050 |
| Brier / NLL | 0.151 / 0.391 |
| smallest non-zero probability / exact zeros | 9.99998e-07 / 9,768 |
| rows where the labeled class has probability 0 | 1 |
| ECE after temperature (T=1.86, floor 4.99999e-07) | 0.010 |
| ECE after temperature, unfloored (T=1.95) | 0.010 |
| ECE after isotonic | 0.015 |
| corr(reported confidence, max prob) | 1.000 |

| option | support | predicted | recall | precision |
| --- | ---: | ---: | ---: | ---: |
| credit card | 142 | 155 | 86.6 % | 79.4 % |
| checking or savings account | 124 | 119 | 77.4 % | 80.7 % |
| student loan | 36 | 30 | 63.9 % | 76.7 % |
| money transfer or virtual currency | 39 | 33 | 64.1 % | 75.8 % |
| vehicle loan or lease | 38 | 36 | 65.8 % | 69.4 % |
| payday, title, or personal loan | 24 | 17 | 58.3 % | 82.4 % |
| credit reporting | 1248 | 1277 | 96.6 % | 94.4 % |
| debt collection | 239 | 233 | 86.6 % | 88.8 % |
| mortgage | 110 | 100 | 81.8 % | 90.0 % |

Reliability (raw):

| bin | n | mean confidence | observed accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.3–0.4 | 5 | 0.380 | 0.400 | +0.020 |
| 0.4–0.5 | 22 | 0.466 | 0.318 | -0.148 |
| 0.5–0.6 | 45 | 0.550 | 0.422 | -0.128 |
| 0.6–0.7 | 50 | 0.650 | 0.600 | -0.050 |
| 0.7–0.8 | 53 | 0.745 | 0.642 | -0.104 |
| 0.8–0.9 | 93 | 0.853 | 0.645 | -0.208 |
| 0.9–1.0 | 1732 | 0.993 | 0.957 | -0.037 |

## `choice_shift6`

Question: *Which financial product is this consumer complaint about?*

Options (in order): money transfer or virtual currency, vehicle loan or lease, payday, title, or personal loan, credit reporting, debt collection, mortgage, credit card, checking or savings account, student loan

| metric | value |
| --- | ---: |
| n | 2000 |
| accuracy | 90.8 % [89.5 %, 92.0 %] |
| macro-F1 | 0.798 |
| mean confidence | 0.955 |
| ECE (15 equal-width bins) | 0.048 [0.041, 0.062] |
| ECE (15 equal-mass bins) | 0.047 |
| Brier / NLL | 0.150 / 0.391 |
| smallest non-zero probability / exact zeros | 9.99998e-07 / 9,715 |
| rows where the labeled class has probability 0 | 1 |
| ECE after temperature (T=1.87, floor 4.99999e-07) | 0.011 |
| ECE after temperature, unfloored (T=1.96) | 0.016 |
| ECE after isotonic | 0.014 |
| corr(reported confidence, max prob) | 1.000 |

| option | support | predicted | recall | precision |
| --- | ---: | ---: | ---: | ---: |
| money transfer or virtual currency | 39 | 48 | 82.1 % | 66.7 % |
| vehicle loan or lease | 38 | 38 | 68.4 % | 68.4 % |
| payday, title, or personal loan | 24 | 18 | 62.5 % | 83.3 % |
| credit reporting | 1248 | 1279 | 96.7 % | 94.4 % |
| debt collection | 239 | 234 | 87.4 % | 89.3 % |
| mortgage | 110 | 103 | 82.7 % | 88.3 % |
| credit card | 142 | 132 | 82.4 % | 88.6 % |
| checking or savings account | 124 | 119 | 77.4 % | 80.7 % |
| student loan | 36 | 29 | 63.9 % | 79.3 % |

Reliability (raw):

| bin | n | mean confidence | observed accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.2–0.3 | 1 | 0.285 | 0.000 | -0.285 |
| 0.3–0.4 | 5 | 0.369 | 0.600 | +0.231 |
| 0.4–0.5 | 20 | 0.466 | 0.500 | +0.034 |
| 0.5–0.6 | 48 | 0.551 | 0.479 | -0.071 |
| 0.6–0.7 | 46 | 0.643 | 0.630 | -0.012 |
| 0.7–0.8 | 56 | 0.744 | 0.625 | -0.119 |
| 0.8–0.9 | 86 | 0.855 | 0.593 | -0.262 |
| 0.9–1.0 | 1738 | 0.994 | 0.958 | -0.036 |

## `noul_debt_collection`

Question: *the complaint is about a debt collector or about collecting a debt*

| metric | value |
| --- | ---: |
| n / prevalence | 2000 / 11.9 % |
| AUROC | 0.967 [0.957, 0.977] |
| ECE (15 equal-width bins) | 0.034 [0.028, 0.045] |
| ECE (15 equal-mass bins) | 0.033 |
| Brier / NLL | 0.043 / 0.181 |
| precision / recall / F1 at 0.5 | 0.870 / 0.644 / 0.740 |
| best F1 (threshold) | 0.773 (0.24) |
| ECE / Brier after isotonic | 0.013 / 0.041 |
| ECE / Brier after Platt | 0.016 / 0.040 |

Reliability (raw):

| bin | n | mean confidence | observed accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.0–0.1 | 1733 | 0.004 | 0.027 | +0.023 |
| 0.1–0.2 | 29 | 0.151 | 0.310 | +0.160 |
| 0.2–0.3 | 30 | 0.253 | 0.400 | +0.147 |
| 0.3–0.4 | 17 | 0.351 | 0.471 | +0.120 |
| 0.4–0.5 | 14 | 0.455 | 0.643 | +0.188 |
| 0.5–0.6 | 9 | 0.558 | 0.556 | -0.002 |
| 0.6–0.7 | 13 | 0.654 | 0.769 | +0.116 |
| 0.7–0.8 | 11 | 0.760 | 0.636 | -0.124 |
| 0.8–0.9 | 12 | 0.856 | 0.917 | +0.061 |
| 0.9–1.0 | 132 | 0.983 | 0.917 | -0.066 |

## `noul_incorrect_report`

Question: *the consumer says their credit report contains incorrect information*

| metric | value |
| --- | ---: |
| n / prevalence | 2000 / 28.1 % |
| AUROC | 0.966 [0.957, 0.974] |
| ECE (15 equal-width bins) | 0.042 [0.035, 0.055] |
| ECE (15 equal-mass bins) | 0.036 |
| Brier / NLL | 0.061 / 0.259 |
| precision / recall / F1 at 0.5 | 0.886 / 0.843 / 0.864 |
| best F1 (threshold) | 0.866 (0.46) |
| ECE / Brier after isotonic | 0.019 / 0.060 |
| ECE / Brier after Platt | 0.017 / 0.060 |

Reliability (raw):

| bin | n | mean confidence | observed accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.0–0.1 | 1328 | 0.006 | 0.036 | +0.030 |
| 0.1–0.2 | 61 | 0.152 | 0.230 | +0.078 |
| 0.2–0.3 | 29 | 0.251 | 0.345 | +0.094 |
| 0.3–0.4 | 17 | 0.356 | 0.294 | -0.062 |
| 0.4–0.5 | 30 | 0.449 | 0.367 | -0.082 |
| 0.5–0.6 | 14 | 0.549 | 0.571 | +0.022 |
| 0.6–0.7 | 21 | 0.653 | 0.524 | -0.129 |
| 0.7–0.8 | 30 | 0.745 | 0.667 | -0.078 |
| 0.8–0.9 | 30 | 0.848 | 0.833 | -0.015 |
| 0.9–1.0 | 440 | 0.986 | 0.932 | -0.054 |

## Option-order sensitivity

Orderings: choice_base, choice_shift3, choice_shift6 (cyclic shifts of the same options), 2000 rows.

| metric | value |
| --- | ---: |
| rows whose answer changes with order | 4.1 % [3.3 %, 4.9 %] |
| answers that are the first-listed option | 25.6 % |
| truths that are the first-listed option | 23.8 % |
| excess first-position answers | 1.8 % [1.4 %, 2.3 %] |
| probability lift when listed first | 1.46 pp |
| within-class recall gain when the true class is listed first | 2.38 pp [1.61, 3.15] |
| accuracy: canonical order → averaged over orderings | 89.9 % → 91.0 % (Δ CI [0.4 %, 1.7 %]) |
| ECE: canonical order → averaged | 0.059 → 0.051 |

| class listed first | rows | recall when first | recall in other orderings |
| --- | ---: | ---: | ---: |
| credit reporting | 1248 | 98.1 % | 96.7 % |
| credit card | 142 | 86.6 % | 80.6 % |
| money transfer or virtual currency | 39 | 82.1 % | 61.5 % |

## Label-set drift

Same question and order, with "other financial product or service" appended. 2000 rows.

| metric | value |
| --- | ---: |
| top-1 answers that change | 0.1 % [0.0 %, 0.1 %] |
| answers moving to the new option | 0.1 % |
| mean Δ p(true label) | -0.0007 |
| mean Δ max probability | -0.0005 |
| accuracy before → after | 89.9 % → 89.8 % |

| τ | auto-accepted before | after | Jaccard | precision before | after |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.5 | 1974 | 1973 | 1.00 | 90.6 % | 90.6 % |
| 0.7 | 1890 | 1888 | 1.00 | 92.8 % | 92.7 % |
| 0.9 | 1750 | 1748 | 1.00 | 95.1 % | 95.1 % |

## Method notes

- ECE is the count-weighted |accuracy − confidence| over bins (top-label confidence for choice). Brackets are 95 % percentile-bootstrap intervals over rows (1,000 resamples).
- Recalibrated numbers are **out-of-fold** (5-fold cross-fitting), so they are not scored on the rows they were fitted on.
- If a backend reports exact zeros, temperature scaling is fitted after flooring probabilities at half the smallest non-zero value; otherwise a handful of zero-probability labels dominate NLL and the fitted temperature.
- Yes/no truth is a coded field (product or issue). A confident "yes" on a row coded otherwise can be a model error **or** a narrative that satisfies the question while the consumer filed it under another issue; raw ECE mixes both. Recalibrated ECE measures how well the scores map onto *this* label definition.
- Sampling: CC0 mirror of CFPB narratives; the source, revision, seed and truncation are recorded in `data/raw/*.manifest.json` (default: uniform sample of parquet shard 0, de-duplicated by narrative, ≤ 1,500 chars).
- Each experiment runs in a fresh session with `jev_cache_clear()`: pg-jev's answer cache key omits `jev.model` and `jev.api_url`.
