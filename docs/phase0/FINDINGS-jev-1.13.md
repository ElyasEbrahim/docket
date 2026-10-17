# How calibrated is Jev on real Postgres data? Phase 0 findings (draft technical note)

**Run:** `jev-20261017-122314` · model `jev-1.13.0` via pg-jev 0.2.1 · 2,000 CFPB complaint narratives (CC0 mirror, 2015–2024, ≤ 1,500 chars) · 6 experiments, 12,000 judgments · **3.46M input tokens, ≈ $0.146**, 24 s wall-clock.
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

- **7.4 %** [6.4, 8.6] of rows change their answer across three cyclic orderings of the same options.
- Listing an option first raises its probability by **+1.0 pp** [0.9, 1.2]. Within each class, recall rises **+2.3 pp** [1.4, 3.1] when the true class is listed first (credit reporting 82.3 % vs 79.8 %).
- Averaging the three orderings costs 3× and leaves accuracy unchanged (77.0 % → 76.6 %).
- **Design consequence:** option order belongs in the decision spec hash (ADR 0002), because about 1 in 14 answers depends on it. Order-averaging should stay off by default.

## 5. Label-set drift is real: adding "other" flips answers between unrelated classes

Appending "other financial product or service" (nothing in the sample has that label):

- **5.8 %** of top-1 answers change. Only 2.5 % move to "other"; the remaining **3.3 % switch between the original nine classes**, even though nothing about them changed.
- At τ = 0.7 the auto-accepted set changes membership by 8 % (Jaccard 0.92). The threshold that keeps the same volume moves to ≈ 0.68.
- This measures the PDF's warning that probabilities are conditional on the label set. **Design consequence:** a label-set change must create a new version and run a shadow diff before it replaces the old one.

## 6. Operational notes

- Speed matches pg-jev's README: **3.1–3.7 s per 2,000 rows** per question (100 requests), ≈ 314 tokens/row for 9-way choice and ≈ 233 for yes/no, on narratives up to 1,500 characters.
- Cost per 1,000 rows: ≈ $0.013 (choice) and $0.010 (yes/no).

## Limits of this note

One model version, one dataset, one run (run-to-run determinism not yet measured), 2,000 rows (small classes have 24–39 examples), consumer-selected labels, English only, narratives truncated to 1,500 characters.

## Phase 0 go/no-go (technical half)

| Criterion | Result |
| --- | --- |
| Raw miscalibration ≥ 2× the recalibrated value | **Yes**: choice 3.3×, yes/no 15×+ |
| Option order changes answers | **Yes**, modestly (7.4 % of rows; +1 pp lift) |
| Label-set change moves decisions | **Yes** (5.8 % flips; 8 % of the τ = 0.7 set) |

The user-demand half (≥ 3 people who would use durable decisions) is still open.

## Next measurements (cheap)

1. Re-run `choice_base` twice to measure **run-to-run determinism** (≈ $0.03).
2. Learning curve: calibration quality vs number of labels (100, 200, 500, 1,000), which determines the review budget Docket asks for.
3. Same harness against a local Laya/stuntd backend (`--api-url`) for a cross-backend comparison.
