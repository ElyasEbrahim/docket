# Benchmark run `jev-20261019-073856`

- Backend: `jev` · model `jev-1.13.0` · endpoint `https://api.typesafe.ai/v1/systemone` · 1 row(s) per request
- Rows: 2000 CFPB complaint narratives · started 2026-10-19 07:38:56.071567+00:00 · finished 2026-10-19 07:39:57.041416+00:00
- Ground truth: consumer-selected Product / Issue (noisy; agreement is a lower bound on fidelity)

## Headline numbers

- **Product choice (9 options):** accuracy 79.3 % [77.5 %, 80.9 %], top-label ECE 0.126 [0.114, 0.144] → 0.032 after temperature scaling (T = 1.26, zeros floored at 0.005) and 0.056 after isotonic (both cross-fitted).
- **Probability resolution:** smallest non-zero probability 0.01; 14,228 exact zeros; the labeled class gets exactly 0 on 115 rows. Unfloored temperature scaling fits T = 5.76 and moves ECE to 0.087.

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
| choice_base | 60.9 | 2000 | 1,128,831 | 0.0474 |

## `choice_base`

Question: *Which financial product is this consumer complaint about?*

Options (in order): credit reporting, debt collection, mortgage, credit card, checking or savings account, student loan, money transfer or virtual currency, vehicle loan or lease, payday, title, or personal loan

| metric | value |
| --- | ---: |
| n | 2000 |
| accuracy | 79.3 % [77.5 %, 80.9 %] |
| macro-F1 | 0.707 |
| mean confidence | 0.918 |
| ECE (15 equal-width bins) | 0.126 [0.114, 0.144] |
| ECE (15 equal-mass bins) | 0.125 |
| Brier / NLL | 0.340 / 2.012 |
| smallest non-zero probability / exact zeros | 0.01 / 14,228 |
| rows where the labeled class has probability 0 | 115 |
| ECE after temperature (T=1.26, floor 0.005) | 0.032 |
| ECE after temperature, unfloored (T=5.76) | 0.087 |
| ECE after isotonic | 0.056 |
| corr(reported confidence, max prob) | 1.000 |

| option | support | predicted | recall | precision |
| --- | ---: | ---: | ---: | ---: |
| credit reporting | 1248 | 1074 | 81.0 % | 94.1 % |
| debt collection | 239 | 213 | 60.7 % | 68.1 % |
| mortgage | 110 | 120 | 92.7 % | 85.0 % |
| credit card | 142 | 274 | 84.5 % | 43.8 % |
| checking or savings account | 124 | 135 | 83.1 % | 76.3 % |
| student loan | 36 | 56 | 86.1 % | 55.4 % |
| money transfer or virtual currency | 39 | 36 | 69.2 % | 75.0 % |
| vehicle loan or lease | 38 | 52 | 78.9 % | 57.7 % |
| payday, title, or personal loan | 24 | 40 | 70.8 % | 42.5 % |

Reliability (raw):

| bin | n | mean confidence | observed accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.3–0.4 | 12 | 0.370 | 0.250 | -0.120 |
| 0.4–0.5 | 31 | 0.447 | 0.387 | -0.060 |
| 0.5–0.6 | 102 | 0.554 | 0.520 | -0.035 |
| 0.6–0.7 | 84 | 0.655 | 0.536 | -0.119 |
| 0.7–0.8 | 108 | 0.756 | 0.602 | -0.154 |
| 0.8–0.9 | 142 | 0.852 | 0.599 | -0.254 |
| 0.9–1.0 | 1521 | 0.988 | 0.870 | -0.118 |

## Method notes

- ECE is the count-weighted |accuracy − confidence| over bins (top-label confidence for choice). Brackets are 95 % percentile-bootstrap intervals over rows (1,000 resamples).
- Recalibrated numbers are **out-of-fold** (5-fold cross-fitting), so they are not scored on the rows they were fitted on.
- If a backend reports exact zeros, temperature scaling is fitted after flooring probabilities at half the smallest non-zero value; otherwise a handful of zero-probability labels dominate NLL and the fitted temperature.
- Yes/no truth is a coded field (product or issue). A confident "yes" on a row coded otherwise can be a model error **or** a narrative that satisfies the question while the consumer filed it under another issue; raw ECE mixes both. Recalibrated ECE measures how well the scores map onto *this* label definition.
- Sampling: CC0 mirror of CFPB narratives; the source, revision, seed and truncation are recorded in `data/raw/*.manifest.json` (default: uniform sample of parquet shard 0, de-duplicated by narrative, ≤ 1,500 chars).
- Each experiment runs in a fresh session with `jev_cache_clear()`: pg-jev's answer cache key omits `jev.model` and `jev.api_url`.
