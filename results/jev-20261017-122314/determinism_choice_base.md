# Run-to-run determinism: `choice_base`

Runs: `jev-20261017-122314`, `jev-20261018-110601`, `jev-20261018-110607` · 2000 rows · identical requests (same rows, order, batches, options and model).

| metric | value |
| --- | ---: |
| rows with identical probabilities in every run | 27.5 % |
| rows with the same top answer in every run | 95.2 % |
| rows where some option moves by ≥ 0.05 | 33.9 % |
| largest probability change seen | 0.87 |
| mean confidence (first run): rows whose answer flips / stable rows | 0.493 / 0.872 |

| run pair | top-1 agreement | identical probabilities | rows with max change ≥ 0.05 | mean max change |
| --- | ---: | ---: | ---: | ---: |
| `jev-20261017-122314` vs `jev-20261018-110601` | 96.2 % | 34.3 % | 23.9 % | 0.0317 |
| `jev-20261017-122314` vs `jev-20261018-110607` | 97.2 % | 33.7 % | 22.8 % | 0.0313 |
| `jev-20261018-110601` vs `jev-20261018-110607` | 96.9 % | 33.6 % | 21.9 % | 0.0304 |

| run | accuracy | ECE |
| --- | ---: | ---: |
| `jev-20261017-122314` | 77.0 % | 0.089 |
| `jev-20261018-110601` | 77.0 % | 0.093 |
| `jev-20261018-110607` | 76.9 % | 0.090 |

Largest change of any option probability per row, across runs:

| change | rows |
| --- | ---: |
| 0.00-0.01 | 550 |
| 0.01-0.02 | 313 |
| 0.02-0.05 | 460 |
| 0.05-0.10 | 399 |
| 0.10-0.20 | 211 |
| 0.20-1.01 | 67 |
