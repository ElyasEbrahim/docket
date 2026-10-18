# Label learning curve: run `jev-20261017-122314`

For each label budget n, fit the calibrator on n random labeled rows and measure ECE on 1000 other rows. 50 random splits per n; values are mean [10th–90th percentile]. "Floor" is the ECE a perfectly calibrated predictor would still show on this many test rows (finite-sample noise).

## `choice_base`

| labels | raw | isotonic | temperature |
| ---: | ---: | ---: | ---: |
| 100 | 0.090 | 0.071 [0.048–0.094] | 0.050 [0.033–0.068] |
| 200 | 0.090 | 0.062 [0.042–0.084] | 0.044 [0.028–0.058] |
| 500 | 0.090 | 0.049 [0.039–0.068] | 0.039 [0.025–0.054] |
| 1000 | 0.090 | 0.043 [0.032–0.055] | 0.037 [0.022–0.052] |

Finite-sample floor on 1000 rows: 0.030

## `noul_debt_collection` (prevalence 11.9 %)

| labels | raw | isotonic | platt | positives among labels |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 0.239 | 0.048 [0.035–0.070] | 0.037 [0.026–0.053] | 12 |
| 200 | 0.239 | 0.041 [0.029–0.053] | 0.031 [0.022–0.043] | 23 |
| 500 | 0.239 | 0.031 [0.024–0.039] | 0.027 [0.021–0.033] | 58 |
| 1000 | 0.239 | 0.026 [0.018–0.033] | 0.024 [0.017–0.030] | 118 |

Finite-sample floor on 1000 rows: 0.022

## `noul_incorrect_report` (prevalence 28.1 %)

| labels | raw | isotonic | platt | positives among labels |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 0.384 | 0.077 [0.041–0.119] | 0.065 [0.040–0.089] | 28 |
| 200 | 0.384 | 0.060 [0.035–0.089] | 0.055 [0.035–0.074] | 57 |
| 500 | 0.384 | 0.049 [0.028–0.069] | 0.045 [0.033–0.060] | 142 |
| 1000 | 0.384 | 0.043 [0.025–0.058] | 0.046 [0.033–0.062] | 286 |

Finite-sample floor on 1000 rows: 0.029
