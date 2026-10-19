# How calibrated is Jev on real Postgres data? Phase 0 findings (draft technical note)

**Run:** `jev-20261017-122314` (plus `choice_base` repeats `jev-20261018-110601` / `-110607` / `jev-20261019-072124` and a shuffled-batch run `jev-20261019-072045`) · model `jev-1.13.0` via pg-jev 0.2.1 · 2,000 CFPB complaint narratives (CC0 mirror, 2015–2024, ≤ 1,500 chars) · 6 experiments, 12,000 judgments · **3.46M input tokens, ≈ $0.146**, 24 s wall-clock.
Full numbers: [`results/jev-20261017-122314/report.md`](../../results/jev-20261017-122314/report.md).

Ground truth is what the consumer selected on the CFPB form (product, issue). It is noisy and sometimes defines the question differently from the narrative, so agreement is a **lower bound** on fidelity to the text.

## 1. Product choice (9 options): useful, over-confident in the middle, fixable

- Accuracy **77.0 %** [75.4, 79.0] against the consumer's own label; macro-F1 0.66. Credit reporting is precise (90 %). Credit card (43 %), student loan (43 %) and payday loans (38 %) are over-predicted, and debt collection is under-recalled (52 %, often called credit reporting).
- Top-label **ECE 0.089** [0.075, 0.106]. Most of the miscalibration sits between 0.6 and 0.9 confidence, where observed accuracy is 13–14 points lower than stated. At 0.9–1.0 the stated confidence is 0.977 and observed accuracy 0.907.
- **Recalibration on 2,000 labels (out-of-fold):** isotonic **0.027** (3.3× lower); temperature scaling **0.029** (T = 1.13).

## 2. Jev reports probabilities on a 0.01 grid, with exact zeros

- Every probability is a multiple of 0.01. 12,104 of the 18,000 option probabilities are exactly 0, and for **54 rows (2.7 %) the consumer's label gets exactly 0**.
- Those 54 rows alone contribute ≈ 58 % of the log-loss, and the worst 5 % of rows contribute 66 %. Naive temperature scaling therefore fits **T ≈ 4** and makes calibration *worse* (ECE 0.167). Flooring zeros at half the grid step (0.005) before fitting fixes it.
- This matches the "resolution floor" bound that Rafe & Das (arXiv 2609.24052) describe for models that report on a discrete grid. **Design consequence for Docket:** default to isotonic/histogram calibration, and never fit NLL-based calibrators on raw Jev output.
- The `confidence` field tracks the maximum probability almost perfectly (r ≈ 1.00, max difference 0.09), so it adds little information.

## 3. Yes/no questions: good ranking, raw probabilities not usable as probabilities

| Question | Prevalence | AUROC | Raw ECE | Isotonic ECE |
| --- | ---: | ---: | ---: | ---: |
| "the complaint is about a debt collector or about collecting a debt" | 11.9 % | 0.884 | 0.240 | 0.016 |
| "the consumer says their credit report contains incorrect information" | 28.1 % | 0.748 | 0.380 | 0.024 |

Two different causes:

- **Debt collection: real over-estimation at the low end.** Jev seldom goes below 0.1 (121 of 2,000 rows). 1,121 non-debt-collection complaints get 0.2–0.6, and only 4 % of those mention collections at all. Rows scored 0.2–0.3 are positive 2.5 % of the time.
- **Incorrect report: mostly a mismatch between the question and the coded label.** The 310 confident "false positives" (p ≥ 0.9, coded as another issue) contain incorrect-information wording as often (52 %) as the confident true positives (50 %), against 11 % for rows scored below 0.3. Most are credit-report complaints filed under "problem with investigation" or "improper use". The model is answering the question as written; the coded field defines it more narrowly.

Either way, a raw `jev_prob() > 0.5` is the wrong operating point. At 0.5, precision is 0.43 and 0.38. The best-F1 thresholds were 0.65 and 0.71. Once mapped onto the team's own label definition with a few hundred to a few thousand labels, the scores are well calibrated (ECE ≈ 0.02). That is the calibration layer's job.

## 4. Option order matters a little, and averaging doesn't help

- **7.4 %** [6.4, 8.6] of rows change their answer across three cyclic orderings of the same options. However, three *identical* repeats already change **4.9 %** of rows (§7), so only about **2.6 points** of that is due to order.
- Listing an option first raises its probability by **+1.0 pp** [0.9, 1.2]. Within each class, recall rises **+2.3 pp** [1.4, 3.1] when the true class is listed first (credit reporting 82.3 % vs 79.8 %).
- Averaging the three orderings costs 3× and leaves accuracy unchanged (77.0 % → 76.6 %).
- **Design consequence:** option order still belongs in the decision spec hash (ADR 0002), because the paired effects are real even though they are small. Order-averaging should stay off by default.

## 5. Label-set drift: the new option takes answers, and the rest is noise

Appending "other financial product or service" (nothing in the sample has that label):

- **5.8 %** of top-1 answers change. **2.5 %** move to "other", and all of those are wrong, since no row has that label. Accuracy goes from 77.0 % to 76.2 %.
- The other **3.3 %** switch between the original nine classes. Two identical runs differ by 2.9–3.8 % (§7), so that part is **indistinguishable from run-to-run noise**, and I can't attribute it to the label change. *(The first draft of this note said otherwise. The repeats corrected it.)*
- At τ = 0.7 the auto-accepted set has Jaccard 0.92 with the original; identical repeats give 0.94–0.95. The label change adds a little churn beyond the noise, and the threshold that keeps the same volume moves to ≈ 0.68.
- **Design consequence:** a label-set change still needs a new version and a shadow diff, because a catch-all option visibly takes answers. But any diff has to be read against a run-to-run noise baseline. Docket should measure that baseline by re-judging a sample, and report it next to every version diff.

## 6. Operational notes

- Speed matches pg-jev's README: **3.1–3.7 s per 2,000 rows** per question (100 requests), ≈ 314 tokens/row for 9-way choice and ≈ 233 for yes/no, on narratives up to 1,500 characters.
- Cost per 1,000 rows: ≈ $0.013 (choice) and $0.010 (yes/no).

## 7. Identical requests do not get identical answers

`choice_base` was run three times. The rows, physical order, 100 batches of 20, options and pinned model were identical; logging the simulator's requests confirmed that pg-jev forms the same batches every time. The original ran on 17 Oct and the two repeats on 18 Oct.
Full table: [`results/jev-20261017-122314/determinism_choice_base.md`](../../results/jev-20261017-122314/determinism_choice_base.md).

| Measure | Result |
| --- | ---: |
| Rows with identical probabilities in all 3 runs | **27.5 %** |
| Rows with the same top answer in all 3 runs | **95.2 %** (4.8 % flip) |
| Pairwise top-1 agreement | 96.2 – 97.2 % |
| Rows where some option moves by ≥ 0.05 | 33.9 % |
| Largest single change | 0.87 |
| Mean confidence of rows that flip / that don't | 0.49 / 0.87 |
| Accuracy / ECE per run | 77.0 / 77.0 / 76.9 % · 0.089 / 0.093 / 0.090 |

- **Aggregates are stable; individual answers are not.** About 1 row in 30 gets a different top answer if you ask again, concentrated where Jev is unsure. Pooled pg-jev sessions, or two analysts on the same table, will disagree on those rows.
- **Design consequence:** this is the strongest argument yet for the ledger (ADR 0002). Re-judging can't reproduce a past decision; only a stored judgment can. It also sets the noise floor every comparison (orderings, label sets, model versions) must beat.

## 8. How many labels does calibration need?

Fit the calibrator on *n* random labeled rows and score ECE on 1,000 other rows, over 50 random splits. Values are means; the full table with 10th–90th percentiles is in [`results/jev-20261017-122314/learning_curve.md`](../../results/jev-20261017-122314/learning_curve.md). The *floor* is the ECE a perfectly calibrated predictor would still show on 1,000 test rows.

| Task | Raw | 100 labels | 200 | 500 | 1,000 | Floor |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Product choice: temperature (floored) | 0.090 | **0.050** | 0.044 | 0.039 | 0.037 | 0.030 |
| Product choice: isotonic | 0.090 | 0.071 | 0.062 | 0.049 | 0.043 | 0.030 |
| Debt collection: Platt | 0.239 | **0.037** | 0.031 | 0.027 | 0.024 | 0.022 |
| Debt collection: isotonic | 0.239 | 0.048 | 0.041 | 0.031 | 0.026 | 0.022 |
| Incorrect report: Platt | 0.384 | **0.065** | 0.055 | 0.045 | 0.046 | 0.029 |
| Incorrect report: isotonic | 0.384 | 0.077 | 0.060 | 0.049 | 0.043 | 0.029 |

- **About 100 labels already remove most of the miscalibration**: 80–85 % for the yes/no questions (debt collection with only ~12 positive examples among them) and about 45 % for the 9-way choice.
- **One-parameter calibrators win at small budgets.** Floored temperature and Platt beat isotonic at every budget up to 500, and are still level or better at 1,000 for two of the three tasks. Isotonic only pulls ahead at 1,000 on the weakest-ranking task. This updates ADR 0003: the default should be parametric, with isotonic as an option once ≥ 1,000 labels exist.
- **Diminishing returns after 200–500 labels.** Debt collection reaches the noise floor around 1,000. "Incorrect report" plateaus around 0.045, above its 0.029 floor, because its scores rank less well (AUROC 0.75), so no monotone map can make it perfect.
- **Review-budget rule of thumb for Docket v0.1:** ask for 200 labels per decision to start, and offer 500 for tighter guarantees. A few hours of review per decision is a reasonable request.

## 9. A row's answer depends on which rows it is batched with

pg-jev sends 20 rows per request in one shared state. To test whether the neighbours matter, `bench.items` was re-inserted in a seeded order (`jevbench reorder --seed 1`), so 83 % of rows shared no neighbour with their original batch. `choice_base` was run once. As a control, it was run again the same day with the original batches, so a server-side change on that day can't explain the result.
Full table: [`results/jev-20261017-122314/batch_context_choice_base.md`](../../results/jev-20261017-122314/batch_context_choice_base.md).

| Measure | Same batches (4 runs, 3 days) | Shuffled batches |
| --- | ---: | ---: |
| Pairwise top-1 disagreement | 2.6 – 3.8 % | **16.4 – 16.7 %** |
| Disagreement with a pair of same-batch runs that agree | 1.6 % | 15.2 % |
| Mean largest probability change per row | 0.031 | **0.192** |
| Accuracy / top-label ECE | 76.8–77.0 % / 0.089–0.093 | 76.5 % / 0.085 |

- **Changing a row's batch neighbours changes its top answer about 5× as often as asking again**: an excess of **+13.6 pp [13.2, 14.1]** over run-to-run noise. Today's same-batch control agrees with the earlier runs at noise level, so the effect is the neighbours, not the date.
- **Aggregates hide it.** Accuracy and calibration barely move, but about 1 row in 7 gets a different answer.
- **It looks like leakage between rows.** On the 267 rows that flipped, the new answer matches what the model usually says about one of the *new* neighbours 92.5 % of the time, against 82.8 % for the old neighbours (88.8 % vs 74.3 % excluding "credit reporting"). Flips also cluster on rows that sat in the last slots of their original batch: 23–30 % at positions 16–18, against 6–9 % at positions 0–2. No clear pattern shows by new position, so the mechanism isn't settled.
- **Flipped rows are hard rows.** On them, the same-batch answer was correct 49.8 % of the time and the shuffled answer 39.0 %.
- pg-jev's README reports batches of 1–20 as 100 % correct on conditions over structured columns. On free-text narratives, batch context clearly matters.
- **Design consequence for Docket:** a judgment is not a function of the row alone. Incremental judging (new rows batched together) and a backfill would disagree on about 1 row in 7. Docket must either judge rows singly or record batch composition in the ledger. Batch size 1 costs about 2.5× the tokens (≈ 435 vs 175 per row in pg-jev's measurements), which is still about $15 per million rows. The next measurement is accuracy and stability at batch size 1.

## Limits of this note

One model version, one dataset, four same-batch runs and one shuffled-batch run of one experiment, 2,000 rows (small classes have 24–39 examples), consumer-selected labels, English only, narratives truncated to 1,500 characters.

## Phase 0 go/no-go (technical half)

| Criterion | Result |
| --- | --- |
| Raw miscalibration ≥ 2× the recalibrated value | **Yes**: choice 3.3×, yes/no 15×+ |
| Option order changes answers | **Yes, small**: +1.0 pp probability lift; ≈ 2.6 % of rows beyond run-to-run noise |
| Label-set change moves decisions | **Yes, small**: 2.5 % of answers move to the new, always-wrong option; other churn is within noise |
| Answers are reproducible | **No**: 4.8 % of rows change top answer across 3 identical runs (new argument for the ledger) |
| Labels needed for calibration | ~100–200 for most of the gain |
| Answers depend on batch neighbours | **Yes, strongly**: 16.5 % of rows change top answer when neighbours change, against 3 % noise |

The user-demand half (≥ 3 people who would use durable decisions) is still open.

## Next measurements (cheap)

1. **Batch size 1:** accuracy, calibration and run-to-run stability with `jev.batch_size = 1` (≈ $0.04). Decides whether Docket judges rows singly (§9).
2. Same harness against a local Laya/stuntd backend (`--api-url`) for a cross-backend comparison.
3. A second dataset (e.g. OSHA severe-injury narratives) so the note isn't single-dataset.
