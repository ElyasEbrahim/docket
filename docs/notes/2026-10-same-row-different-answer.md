# Same row, different answer: what I measured running Jev over 2,000 complaints in Postgres

*ElyasEbrahim · October 2026 · [github.com/ElyasEbrahim/pgdocket](https://github.com/ElyasEbrahim/pgdocket)*

[pg-jev](https://github.com/realZachi/pg-jev) lets you filter Postgres rows with a plain-language condition, such as `WHERE jev(tickets, 'the customer threatens to cancel')`. Behind it, TypeSafe's Jev decision model returns probabilities instead of text. It is fast, cheap and pleasant to use.

Before building on it, I wanted to know whether the answers were reliable enough to store, report and act on. So I built a small benchmark and ran it on 2,000 real consumer-complaint narratives. All the API calls together cost about $0.30.

## TL;DR

- **The rows a row is batched with change its answer.** pg-jev sends 20 rows per request. Re-batching the same rows changed the top answer for **~16.5 %** of them, five times the run-to-run noise.
- **One row per request is more accurate:** +2.4 points accuracy, +0.05 macro-F1, mostly in the smaller categories, at 1.8× the tokens (about $24 per million rows).
- **Asking again changes answers too:** 4.8 % of rows changed their top answer across three identical runs. Totals stayed stable.
- **The scores are not probabilities yet.** Raw calibration error was 0.09 on a 9-way choice and 0.24–0.38 on yes/no questions. **About 100 human labels** remove 45–85 % of it, if you pick the right method.
- **Option order and label sets matter only a little,** once you account for the noise above.

## Setup

- **Data:** 2,000 CFPB consumer-complaint narratives (2015–2024, up to 1,500 characters each). CFPB stopped publishing narratives in August 2026, so these come from a CC0 mirror of earlier releases. Ground truth is the product and issue the consumer picked on the form. That's noisy, so agreement is a lower bound.
- **Model and path:** jev-1.13.0, called through pg-jev v0.2.1 in Postgres 16, exactly as a user would call it.
- **Tasks:** a 9-way choice ("which financial product is this complaint about?") and two yes/no conditions.
- **Method checks:** a simulated backend with planted flaws, so I could confirm the analysis recovers known effects before trusting it on the real model. Recalibration results are out-of-fold; intervals are bootstrap 95 % CIs.

Everything is reproducible with Docker: `make up fetch load bench`.

## 1. Your neighbours change your answer

pg-jev packs 20 rows into one request and asks one question per row. That amortises the request overhead, and the maintainer measured it as reliable on conditions over structured columns.

On free-text narratives, it isn't. I re-inserted the same 2,000 rows in a different order, so 83 % of rows had no neighbour in common with their original batch, and ran the same query. To rule out the model changing between days, I also ran a same-day control with the original batches.

| | Same batches (4 runs, 3 days) | Shuffled batches |
| --- | ---: | ---: |
| Rows whose top answer differs between two runs | 2.6 – 3.8 % | **16.4 – 16.7 %** |
| Average largest probability change per row | 0.03 | **0.19** |
| Accuracy | 76.8 – 77.0 % | 76.5 % |

**About 1 row in 7 changes its answer depending on which rows it happens to be sent with.** Accuracy in aggregate barely moves, so you won't see this in a dashboard. You see it when two runs over the same data disagree about specific rows.

It looks like leakage between rows. When an answer flipped, the new answer usually matched what the model says about one of the *new* neighbours (92.5 %, against 82.8 % for the old ones).

Judging rows **one per request** removes the dependence, and it's more accurate:

| | 20 rows per request | 1 row per request |
| --- | ---: | ---: |
| Accuracy | 77.0 % | **79.3 %** (+2.4 pp, CI 0.9–3.8) |
| Macro-F1 | 0.66 | **0.71** |
| Recall, smaller categories | | +5 to +14 pp |
| Tokens per row | 314 | 564 |

The gains are in the minority categories: debt collection, mortgage, credit card, checking, student loans. Most batches are dominated by credit-report complaints, which seem to pull their neighbours toward that answer.

**If you store or act on batched answers, the same row can get a different decision depending on what else was in the batch.** With pg-jev you can set `jev.batch_size = 1` for decisions you keep.

## 2. Asking again changes some answers

Three identical runs, with the same rows, batches, options and pinned model, agreed on the top answer for 95.2 % of rows. Only 27.5 % of rows got exactly the same probabilities every time. The rows that flipped were the ones the model was unsure about (average confidence 0.49, against 0.87).

Aggregates were stable: accuracy 77.0 / 77.0 / 76.9 %. But if a decision matters, **asking again is not a way to reproduce it. You need to store what was answered.**

## 3. The scores need calibrating, and ~100 labels go a long way

Jev is trained to produce calibrated probabilities. On this data, out of the box, they weren't:

- **9-way choice:** over-confident between 0.6 and 0.9, where stated confidence was about 14 points above actual accuracy. Calibration error (ECE) 0.089.
- **Yes/no questions:** ECE 0.24 and 0.38. At the default `jev()` threshold of 0.5, precision was only 0.43 and 0.38.

Part of the yes/no gap is a definition mismatch rather than model error. For "the consumer says their credit report contains incorrect information", confident "yes" answers on rows coded as another issue mention incorrect information as often as true positives do. The model answers the question as written; the coded field is narrower. That is the point of calibrating on *your* labels: it maps the score onto *your* definition.

How many labels does that take? I fitted calibrators on random subsets and measured on 1,000 held-out rows:

| Task | Raw | 100 labels | 1,000 labels | Noise floor |
| --- | ---: | ---: | ---: | ---: |
| 9-way choice | 0.090 | 0.050 | 0.037 | 0.030 |
| Debt collection (yes/no) | 0.239 | 0.037 | 0.024 | 0.022 |
| Incorrect report (yes/no) | 0.384 | 0.065 | 0.046 | 0.029 |

Two practical details:

- **Jev reports probabilities in steps of 0.01, with many exact zeros.** On 54 rows the consumer's label got exactly 0. Standard temperature scaling then fits a temperature near 4 and makes things *worse*. Clamping zeros at 0.005 first fixes it.
- **Simple beats flexible at small label budgets.** One-parameter methods (temperature scaling for choices, Platt scaling for yes/no) beat isotonic regression up to about 500 labels.

## 4. Smaller effects

- **Option order:** listing an option first raises its probability by about 1 point, a real but small effect. Averaging over orderings costs 3× and didn't improve accuracy.
- **Adding a catch-all option** ("other financial product or service") pulled 2.5 % of answers to it, all of them wrong. Other changes were within run-to-run noise.

## What I'd do if I used this in production

1. **Use one row per request for anything you store or act on.** It's more accurate and doesn't depend on neighbours.
2. **Store the answer, the model version, the question, the options in order, and the batch size.** You can't reproduce an answer by asking again.
3. **Label 100–200 rows per question and calibrate.** Use a one-parameter method, and clamp zeros first.
4. **Don't use 0.5 as the threshold.** Choose it from labeled data, ideally with a stated precision target.
5. **Before reading anything into a difference between two runs, compare it with run-to-run noise.**

## What I'm building

These steps are tedious to do by hand, so I'm building **[pgdocket](https://github.com/ElyasEbrahim/pgdocket)**: a layer that keeps AI decisions in Postgres stored, versioned and calibrated. The plan: judge one row per request, keep a ledger of every answer, calibrate on a few hundred of your labels, report counts with confidence intervals, and run on managed Postgres (Supabase, Neon, RDS) without special extensions. None of that is built yet. This benchmark is the first phase, and it decides what gets built.

**If you classify text stored in Postgres** (support tickets, reviews, complaints, moderation queues), I'd like to hear how you handle this today. I'm happy to run the same calibration check on a sample of your data. Open an issue on the repo to get in touch.

## Limits

- One model version (jev-1.13.0) and one dataset, with consumer-chosen labels.
- 2,000 rows, so the smallest categories have 24–39 examples.
- English text only.
- Run-to-run stability *at* one row per request isn't measured yet.
- I only tested Jev. If you batch several rows into one prompt with another model, the batching effect is worth checking for yourself.

## Reproduce it

```bash
git clone https://github.com/ElyasEbrahim/pgdocket && cd docket
make up && make test
make fetch load                       # CFPB sample → Postgres
make bench                            # simulated backend, free
cp .env.example .env                  # add a TypeSafe key, then:
make bench BACKEND=jev ARGS=--yes     # ~$0.15
```

The full findings, with every table and method detail, are in [docs/phase0/FINDINGS-jev-1.13.md](../phase0/FINDINGS-jev-1.13.md).

## Thanks

- To realZachi for pg-jev, which made this easy to test.
- To TypeSafe for an unusually cheap and fast decision model.
- To the authors of *Calibrated Decisions at Scale* (Rafe & Das, arXiv 2609.24052), whose "audit every model" advice this confirms.
