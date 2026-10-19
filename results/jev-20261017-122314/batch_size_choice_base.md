# Batch size 1 vs 20: `choice_base`

Batched (20 rows per request): `jev-20261017-122314`, `jev-20261018-110601`, `jev-20261018-110607`, `jev-20261019-072124`. Single-row: `jev-20261019-073856`. 2000 rows, same options and model.

| measure | 20 rows per request | 1 row per request |
| --- | ---: | ---: |
| accuracy | 77.0 %, 77.0 %, 76.9 %, 76.8 % | 79.3 % |
| macro-F1 | 0.658, 0.664, 0.661, 0.657 | 0.707 |
| top-label ECE (raw) | 0.089 | 0.126 |
| ECE after floored temperature (T) | 0.029 (1.13) | 0.032 (1.26) |
| ECE after isotonic | 0.027 | 0.056 |
| exact zeros / rows where the label gets 0 | 12,104 / 54 | 14,228 / 115 |
| requests / input tokens | 100 / 628,231 | 2000 / 1,128,831 |
| tokens per row / cost per 1,000 rows | 314 / $0.0132 | 564 / $0.0237 |
| wall-clock for 2000 rows | 3.5 s | 60.9 s |

**Accuracy change from judging rows singly:** +2.38 pp [+0.90, +3.81] (paired per row against the mean of the batched runs; 95 % bootstrap CI).

| disagreement | value |
| --- | ---: |
| between batched runs (noise) | 3.8 %, 2.9 %, 3.3 %, 3.1 %, 2.6 %, 3.0 % |
| single-row vs each batched run | 14.1 %, 14.1 %, 14.4 %, 14.4 % |
| excess over noise | +11.38 pp [+10.96, +11.79] |

On the 267 rows whose answer flipped when re-batched (#3), single-row judging agrees with the original batches 50.2 % and with the shuffled batches 43.1 % of the time. Correct: original batches 49.8 %, shuffled 39.0 %, single-row 62.5 %.

| class | rows | recall, 20 per request | recall, 1 per request |
| --- | ---: | ---: | ---: |
| credit reporting | 1248 | 82.0 % | 81.0 % |
| debt collection | 239 | 53.0 % | 60.7 % |
| mortgage | 110 | 84.3 % | 92.7 % |
| credit card | 142 | 76.8 % | 84.5 % |
| checking or savings account | 124 | 74.0 % | 83.1 % |
| student loan | 36 | 72.2 % | 86.1 % |
| money transfer or virtual currency | 39 | 64.1 % | 69.2 % |
| vehicle loan or lease | 38 | 71.1 % | 78.9 % |
| payday, title, or personal loan | 24 | 70.8 % | 70.8 % |
