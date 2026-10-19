# Batch context: `choice_base`

Same-batch runs: `jev-20261017-122314`, `jev-20261018-110601`, `jev-20261018-110607`, `jev-20261019-072124`. Shuffled-batch run: `jev-20261019-072045`. 2000 rows, same options, same model; only each row's 19 batch neighbours differ.

After reordering, 83.2 % of rows share no neighbour with their original batch (mean shared neighbours 0.18 of 19).

| measure | same batches (noise) | shuffled batches |
| --- | ---: | ---: |
| disagreement with a pair of same-batch runs that agree | 1.6 % | 15.2 % |
| pairwise top-1 flips | 3.8 %, 2.9 %, 3.3 %, 3.1 %, 2.6 %, 3.0 % | 16.4 %, 16.6 %, 16.7 %, 16.4 % |
| mean largest probability change per row | 0.0306 | 0.1923 |
| accuracy | 77.0 %, 77.0 %, 76.9 %, 76.8 % | 76.5 % |
| top-label ECE | 0.089, 0.093, 0.090, 0.089 | 0.085 |

**Excess disagreement caused by different neighbours:** +13.64 pp [+13.20, +14.05] (95 % bootstrap CI over rows). A CI that includes 0 means the batch context effect is not distinguishable from run-to-run noise.
