# Benchmark run `jev-20261017-122314`

- Backend: `jev` · model `jev-1.13.0` · endpoint `https://api.typesafe.ai/v1/systemone`
- Rows: 2000 CFPB complaint narratives · started 2026-10-17 12:23:14.720515+00:00 · finished 2026-10-17 12:23:35.562027+00:00
- Ground truth: consumer-selected Product / Issue (noisy; agreement is a lower bound on fidelity)

## Headline numbers

- **Product choice (9 options):** accuracy 77.0 % [75.4 %, 79.0 %], top-label ECE 0.089 [0.075, 0.106] → 0.029 after temperature scaling (T = 1.13, zeros floored at 0.005) and 0.027 after isotonic (both cross-fitted).
- **Probability resolution:** smallest non-zero probability 0.01; 12,104 exact zeros; the labeled class gets exactly 0 on 54 rows. Unfloored temperature scaling fits T = 3.99 and moves ECE to 0.167.
- **Option order:** 7.4 % [6.4 %, 8.6 %] of rows change their answer across 3 cyclic orderings. Listing an option first lifts its probability by 1.0 pp [0.9, 1.2]; within-class recall changes by 2.3 pp [1.4, 3.1] when the true class is listed first. Averaging orderings: accuracy 77.0 % → 76.6 % at 3× cost.
- **Label-set drift (adding "other financial product or service"):** 5.8 % of top-1 answers change (2.5 % move to the new option); at τ = 0.7 the auto-accepted set goes 1593 → 1568 rows (Jaccard 0.92). Keeping the same volume needs τ ≈ 0.68.
- **noul_debt_collection:** AUROC 0.884 [0.855, 0.909], ECE 0.240 [0.228, 0.252] → 0.016 isotonic / 0.015 Platt (cross-fitted).
- **noul_incorrect_report:** AUROC 0.748 [0.725, 0.767], ECE 0.380 [0.363, 0.398] → 0.024 isotonic / 0.034 Platt (cross-fitted).

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
| choice_base | 3.5 | 100 | 628,231 | 0.0264 |
| choice_other | 3.3 | 100 | 648,231 | 0.0272 |
| choice_shift3 | 3.2 | 100 | 628,231 | 0.0264 |
| choice_shift6 | 3.7 | 100 | 628,231 | 0.0264 |
| noul_debt_collection | 3.1 | 100 | 466,131 | 0.0196 |
| noul_incorrect_report | 3.5 | 100 | 465,831 | 0.0196 |

## `choice_base`

Question: *Which financial product is this consumer complaint about?*

Options (in order): credit reporting, debt collection, mortgage, credit card, checking or savings account, student loan, money transfer or virtual currency, vehicle loan or lease, payday, title, or personal loan

| metric | value |
| --- | ---: |
| n | 2000 |
| accuracy | 77.0 % [75.4 %, 79.0 %] |
| macro-F1 | 0.658 |
| mean confidence | 0.854 |
| ECE (15 equal-width bins) | 0.089 [0.075, 0.106] |
| ECE (15 equal-mass bins) | 0.084 |
| Brier / NLL | 0.344 / 1.291 |
| smallest non-zero probability / exact zeros | 0.01 / 12,104 |
| rows where the labeled class has probability 0 | 54 |
| ECE after temperature (T=1.13, floor 0.005) | 0.029 |
| ECE after temperature, unfloored (T=3.99) | 0.167 |
| ECE after isotonic | 0.027 |
| corr(reported confidence, max prob) | 1.000 |

| option | support | predicted | recall | precision |
| --- | ---: | ---: | ---: | ---: |
| credit reporting | 1248 | 1136 | 82.3 % | 90.4 % |
| debt collection | 239 | 181 | 52.3 % | 69.1 % |
| mortgage | 110 | 120 | 84.5 % | 77.5 % |
| credit card | 142 | 259 | 77.5 % | 42.5 % |
| checking or savings account | 124 | 121 | 74.2 % | 76.0 % |
| student loan | 36 | 58 | 69.4 % | 43.1 % |
| money transfer or virtual currency | 39 | 34 | 64.1 % | 73.5 % |
| vehicle loan or lease | 38 | 46 | 71.1 % | 58.7 % |
| payday, title, or personal loan | 24 | 45 | 70.8 % | 37.8 % |

Reliability (raw):

| bin | n | mean confidence | observed accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.2–0.3 | 4 | 0.268 | 0.250 | -0.018 |
| 0.3–0.4 | 26 | 0.370 | 0.423 | +0.053 |
| 0.4–0.5 | 63 | 0.452 | 0.492 | +0.040 |
| 0.5–0.6 | 165 | 0.547 | 0.503 | -0.044 |
| 0.6–0.7 | 162 | 0.656 | 0.525 | -0.131 |
| 0.7–0.8 | 165 | 0.754 | 0.612 | -0.142 |
| 0.8–0.9 | 279 | 0.848 | 0.713 | -0.135 |
| 0.9–1.0 | 1136 | 0.977 | 0.907 | -0.071 |

## `choice_other`

Question: *Which financial product is this consumer complaint about?*

Options (in order): credit reporting, debt collection, mortgage, credit card, checking or savings account, student loan, money transfer or virtual currency, vehicle loan or lease, payday, title, or personal loan, other financial product or service

| metric | value |
| --- | ---: |
| n | 2000 |
| accuracy | 76.2 % [74.5 %, 78.1 %] |
| macro-F1 | 0.657 |
| mean confidence | 0.843 |
| ECE (15 equal-width bins) | 0.088 [0.074, 0.105] |
| ECE (15 equal-mass bins) | 0.086 |
| Brier / NLL | 0.355 / 1.459 |
| smallest non-zero probability / exact zeros | 0.01 / 13,471 |
| rows where the labeled class has probability 0 | 65 |
| ECE after temperature (T=1.11, floor 0.005) | 0.033 |
| ECE after temperature, unfloored (T=4.13) | 0.189 |
| ECE after isotonic | 0.023 |
| corr(reported confidence, max prob) | 1.000 |

| option | support | predicted | recall | precision |
| --- | ---: | ---: | ---: | ---: |
| credit reporting | 1248 | 1132 | 82.1 % | 90.5 % |
| debt collection | 239 | 177 | 52.3 % | 70.6 % |
| mortgage | 110 | 115 | 82.7 % | 79.1 % |
| credit card | 142 | 251 | 75.4 % | 42.6 % |
| checking or savings account | 124 | 108 | 69.4 % | 79.6 % |
| student loan | 36 | 60 | 77.8 % | 46.7 % |
| money transfer or virtual currency | 39 | 25 | 48.7 % | 76.0 % |
| vehicle loan or lease | 38 | 42 | 71.1 % | 64.3 % |
| payday, title, or personal loan | 24 | 40 | 66.7 % | 40.0 % |
| other financial product or service | 0 | 50 | – | 0.0 % |

Reliability (raw):

| bin | n | mean confidence | observed accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.2–0.3 | 5 | 0.263 | 0.000 | -0.263 |
| 0.3–0.4 | 31 | 0.365 | 0.323 | -0.042 |
| 0.4–0.5 | 91 | 0.452 | 0.527 | +0.075 |
| 0.5–0.6 | 166 | 0.553 | 0.494 | -0.059 |
| 0.6–0.7 | 156 | 0.657 | 0.494 | -0.163 |
| 0.7–0.8 | 183 | 0.749 | 0.628 | -0.121 |
| 0.8–0.9 | 254 | 0.849 | 0.724 | -0.125 |
| 0.9–1.0 | 1114 | 0.975 | 0.905 | -0.070 |

## `choice_shift3`

Question: *Which financial product is this consumer complaint about?*

Options (in order): credit card, checking or savings account, student loan, money transfer or virtual currency, vehicle loan or lease, payday, title, or personal loan, credit reporting, debt collection, mortgage

| metric | value |
| --- | ---: |
| n | 2000 |
| accuracy | 75.9 % [74.2 %, 77.6 %] |
| macro-F1 | 0.653 |
| mean confidence | 0.854 |
| ECE (15 equal-width bins) | 0.094 [0.081, 0.113] |
| ECE (15 equal-mass bins) | 0.094 |
| Brier / NLL | 0.356 / 1.316 |
| smallest non-zero probability / exact zeros | 0.01 / 12,173 |
| rows where the labeled class has probability 0 | 54 |
| ECE after temperature (T=1.14, floor 0.005) | 0.029 |
| ECE after temperature, unfloored (T=3.99) | 0.167 |
| ECE after isotonic | 0.043 |
| corr(reported confidence, max prob) | 1.000 |

| option | support | predicted | recall | precision |
| --- | ---: | ---: | ---: | ---: |
| credit card | 142 | 279 | 78.9 % | 40.1 % |
| checking or savings account | 124 | 121 | 73.4 % | 75.2 % |
| student loan | 36 | 55 | 66.7 % | 43.6 % |
| money transfer or virtual currency | 39 | 33 | 61.5 % | 72.7 % |
| vehicle loan or lease | 38 | 50 | 73.7 % | 56.0 % |
| payday, title, or personal loan | 24 | 45 | 70.8 % | 37.8 % |
| credit reporting | 1248 | 1089 | 79.6 % | 91.2 % |
| debt collection | 239 | 208 | 56.5 % | 64.9 % |
| mortgage | 110 | 120 | 86.4 % | 79.2 % |

Reliability (raw):

| bin | n | mean confidence | observed accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.2–0.3 | 3 | 0.284 | 0.333 | +0.049 |
| 0.3–0.4 | 27 | 0.361 | 0.333 | -0.027 |
| 0.4–0.5 | 73 | 0.452 | 0.425 | -0.027 |
| 0.5–0.6 | 155 | 0.550 | 0.465 | -0.086 |
| 0.6–0.7 | 147 | 0.654 | 0.524 | -0.130 |
| 0.7–0.8 | 172 | 0.754 | 0.622 | -0.132 |
| 0.8–0.9 | 274 | 0.850 | 0.708 | -0.142 |
| 0.9–1.0 | 1149 | 0.974 | 0.895 | -0.080 |

## `choice_shift6`

Question: *Which financial product is this consumer complaint about?*

Options (in order): money transfer or virtual currency, vehicle loan or lease, payday, title, or personal loan, credit reporting, debt collection, mortgage, credit card, checking or savings account, student loan

| metric | value |
| --- | ---: |
| n | 2000 |
| accuracy | 76.3 % [74.6 %, 78.2 %] |
| macro-F1 | 0.655 |
| mean confidence | 0.852 |
| ECE (15 equal-width bins) | 0.093 [0.082, 0.112] |
| ECE (15 equal-mass bins) | 0.089 |
| Brier / NLL | 0.359 / 1.360 |
| smallest non-zero probability / exact zeros | 0.01 / 12,009 |
| rows where the labeled class has probability 0 | 57 |
| ECE after temperature (T=1.15, floor 0.005) | 0.035 |
| ECE after temperature, unfloored (T=4.13) | 0.172 |
| ECE after isotonic | 0.027 |
| corr(reported confidence, max prob) | 1.000 |

| option | support | predicted | recall | precision |
| --- | ---: | ---: | ---: | ---: |
| money transfer or virtual currency | 39 | 39 | 66.7 % | 66.7 % |
| vehicle loan or lease | 38 | 49 | 71.1 % | 55.1 % |
| payday, title, or personal loan | 24 | 43 | 70.8 % | 39.5 % |
| credit reporting | 1248 | 1088 | 79.9 % | 91.6 % |
| debt collection | 239 | 202 | 55.6 % | 65.8 % |
| mortgage | 110 | 126 | 84.5 % | 73.8 % |
| credit card | 142 | 267 | 79.6 % | 42.3 % |
| checking or savings account | 124 | 128 | 76.6 % | 74.2 % |
| student loan | 36 | 58 | 72.2 % | 44.8 % |

Reliability (raw):

| bin | n | mean confidence | observed accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.2–0.3 | 4 | 0.285 | 0.000 | -0.285 |
| 0.3–0.4 | 25 | 0.366 | 0.320 | -0.046 |
| 0.4–0.5 | 78 | 0.452 | 0.462 | +0.009 |
| 0.5–0.6 | 154 | 0.549 | 0.558 | +0.010 |
| 0.6–0.7 | 158 | 0.657 | 0.475 | -0.182 |
| 0.7–0.8 | 177 | 0.755 | 0.655 | -0.100 |
| 0.8–0.9 | 261 | 0.852 | 0.701 | -0.151 |
| 0.9–1.0 | 1143 | 0.976 | 0.895 | -0.080 |

## `noul_debt_collection`

Question: *the complaint is about a debt collector or about collecting a debt*

| metric | value |
| --- | ---: |
| n / prevalence | 2000 / 11.9 % |
| AUROC | 0.884 [0.855, 0.909] |
| ECE (15 equal-width bins) | 0.240 [0.228, 0.252] |
| ECE (15 equal-mass bins) | 0.240 |
| Brier / NLL | 0.132 / 0.432 |
| precision / recall / F1 at 0.5 | 0.430 / 0.782 / 0.555 |
| best F1 (threshold) | 0.633 (0.65) |
| ECE / Brier after isotonic | 0.016 / 0.065 |
| ECE / Brier after Platt | 0.015 / 0.065 |

Reliability (raw):

| bin | n | mean confidence | observed accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.0–0.1 | 121 | 0.069 | 0.000 | -0.069 |
| 0.1–0.2 | 384 | 0.148 | 0.023 | -0.125 |
| 0.2–0.3 | 512 | 0.249 | 0.025 | -0.224 |
| 0.3–0.4 | 340 | 0.348 | 0.041 | -0.307 |
| 0.4–0.5 | 208 | 0.440 | 0.077 | -0.364 |
| 0.5–0.6 | 132 | 0.548 | 0.121 | -0.427 |
| 0.6–0.7 | 66 | 0.655 | 0.318 | -0.337 |
| 0.7–0.8 | 69 | 0.750 | 0.435 | -0.315 |
| 0.8–0.9 | 90 | 0.850 | 0.656 | -0.195 |
| 0.9–1.0 | 78 | 0.930 | 0.782 | -0.148 |

## `noul_incorrect_report`

Question: *the consumer says their credit report contains incorrect information*

| metric | value |
| --- | ---: |
| n / prevalence | 2000 / 28.1 % |
| AUROC | 0.748 [0.725, 0.767] |
| ECE (15 equal-width bins) | 0.380 [0.363, 0.398] |
| ECE (15 equal-mass bins) | 0.380 |
| Brier / NLL | 0.332 / 0.982 |
| precision / recall / F1 at 0.5 | 0.376 / 0.959 / 0.541 |
| best F1 (threshold) | 0.567 (0.71) |
| ECE / Brier after isotonic | 0.024 / 0.172 |
| ECE / Brier after Platt | 0.034 / 0.172 |

Reliability (raw):

| bin | n | mean confidence | observed accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.0–0.1 | 93 | 0.062 | 0.000 | -0.062 |
| 0.1–0.2 | 169 | 0.144 | 0.024 | -0.121 |
| 0.2–0.3 | 132 | 0.245 | 0.045 | -0.200 |
| 0.3–0.4 | 77 | 0.353 | 0.052 | -0.301 |
| 0.4–0.5 | 97 | 0.450 | 0.093 | -0.358 |
| 0.5–0.6 | 114 | 0.550 | 0.158 | -0.392 |
| 0.6–0.7 | 147 | 0.658 | 0.204 | -0.453 |
| 0.7–0.8 | 159 | 0.753 | 0.296 | -0.458 |
| 0.8–0.9 | 423 | 0.853 | 0.390 | -0.463 |
| 0.9–1.0 | 589 | 0.931 | 0.474 | -0.457 |

## Option-order sensitivity

Orderings: choice_base, choice_shift3, choice_shift6 (cyclic shifts of the same options), 2000 rows.

| metric | value |
| --- | ---: |
| rows whose answer changes with order | 7.4 % [6.4 %, 8.6 %] |
| answers that are the first-listed option | 24.2 % |
| truths that are the first-listed option | 23.8 % |
| excess first-position answers | 0.4 % [-0.1 %, 1.0 %] |
| probability lift when listed first | 1.05 pp |
| within-class recall gain when the true class is listed first | 2.34 pp [1.43, 3.15] |
| accuracy: canonical order → averaged over orderings | 77.0 % → 76.6 % (Δ CI [-1.2 %, 0.2 %]) |
| ECE: canonical order → averaged | 0.089 → 0.085 |

| class listed first | rows | recall when first | recall in other orderings |
| --- | ---: | ---: | ---: |
| credit reporting | 1248 | 82.3 % | 79.8 % |
| credit card | 142 | 78.9 % | 78.5 % |
| money transfer or virtual currency | 39 | 66.7 % | 62.8 % |

## Label-set drift

Same question and order, with "other financial product or service" appended. 2000 rows.

| metric | value |
| --- | ---: |
| top-1 answers that change | 5.8 % [4.9 %, 6.9 %] |
| answers moving to the new option | 2.5 % |
| mean Δ p(true label) | -0.0128 |
| mean Δ max probability | -0.0103 |
| accuracy before → after | 77.0 % → 76.2 % |

| τ | auto-accepted before | after | Jaccard | precision before | after |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.5 | 1907 | 1873 | 0.95 | 78.6 % | 78.3 % |
| 0.7 | 1593 | 1568 | 0.92 | 84.1 % | 83.8 % |
| 0.9 | 1136 | 1114 | 0.89 | 90.7 % | 90.5 % |

## Method notes

- ECE is the count-weighted |accuracy − confidence| over bins (top-label confidence for choice). Brackets are 95 % percentile-bootstrap intervals over rows (1,000 resamples).
- Recalibrated numbers are **out-of-fold** (5-fold cross-fitting), so they are not scored on the rows they were fitted on.
- If a backend reports exact zeros, temperature scaling is fitted after flooring probabilities at half the smallest non-zero value; otherwise a handful of zero-probability labels dominate NLL and the fitted temperature.
- Yes/no truth is a coded field (product or issue). A confident "yes" on a row coded otherwise can be a model error **or** a narrative that satisfies the question while the consumer filed it under another issue; raw ECE mixes both. Recalibrated ECE measures how well the scores map onto *this* label definition.
- Sampling: CC0 mirror of CFPB narratives; the source, revision, seed and truncation are recorded in `data/raw/*.manifest.json` (default: uniform sample of parquet shard 0, de-duplicated by narrative, ≤ 1,500 chars).
- Each experiment runs in a fresh session with `jev_cache_clear()`: pg-jev's answer cache key omits `jev.model` and `jev.api_url`.
