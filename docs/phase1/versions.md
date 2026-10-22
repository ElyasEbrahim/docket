# Comparing versions before switching

*2026-10-22 · issues #15, #16 · design: [ADR 0002](../adr/0002-versioned-decision-spec.md), [ADR 0003](../adr/0003-human-labels-are-the-oracle.md)*

Changing a decision (its question, its options, the model) changes some answers. Two questions decide whether to switch:

1. **How many answers does the change move?** Jev isn't deterministic: asked the same thing twice, it changes 1–5 % of its answers anyway ([Findings §7](../phase0/FINDINGS-jev-1.13.md)). Only the changes beyond that noise are caused by the new version.
2. **Are the moved answers better or worse?** That needs labels, but fewer than it seems. Where the two versions give the same answer, they are both right or both wrong. **Only the rows where they disagree decide which version is more accurate.** Label those, and the accuracy difference is known on every compared row.
3. **How much could each version decide on its own?** Two versions can be equally accurate while one separates its right answers from its wrong ones better. That one can auto-accept more rows at the same guaranteed precision.

## Use

```bash
pgdocket revise triage --options-file teams-v2.json      # v2 as a shadow version: nothing judged, view unchanged
pgdocket compare triage 2 --sample 300 --run --out results/compare-v2
pgdocket compare triage 2 --export-disagreements todo.csv    # the rows where they disagree, still unlabelled
pgdocket label triage --csv todo.csv                     # after filling in the label column
pgdocket compare triage 2                                # report again from stored answers (no API calls)

pgdocket backfill triage --version 2 && pgdocket worker --once   # then, to switch:
pgdocket promote triage 2
pgdocket retire triage 2                                 # or, to keep the current version: stop judging for v2
pgdocket versions triage
```

`revise` takes the active spec and replaces what you pass (`--question`, `--options` / `--options-file`, `--model`, `--backend`, `--batch-size`).

## How it works

- **Sample.** `compare --sample N` takes rows the active version has answered. Rows with random-sample labels go first, then a seeded random sample of the rest. The labels were drawn at random, so the union is still a uniform random sample.
- **Both versions judge it at the same time.** The shadow version judges each sampled row. The active version is asked again as a **probe**: a judgment recorded in the ledger with `purpose = 'probe'`. Probes never become the current answer, and the view ignores them. They measure the noise at the same time and on the same rows as the new version.
- **Changed answers.** For each row: did the new version change the answer, and did the re-ask? The excess (changed − noise) gets a paired 95 % bootstrap interval over rows.
- **Accuracy difference.** If every disagreement in the sample has a label (of any kind), the difference is known on every sampled row. Rows where the versions agree contribute exactly zero. Otherwise the difference is measured on random-sample labels alone, and needs at least 30 of them. The report also gives an exact sign test on the disagreements where exactly one version is right.
- **Verdict.**
  - **promote:** the accuracy interval is above zero.
  - **keep current:** the interval is below zero.
  - **no clear difference:** the interval includes zero. The report says how much worse and how much better the new version could be.
  - **needs labels:** there aren't enough labels to judge, and the report says which rows to label.
- **Stored.** The comparison is saved as JSON on `docket.version.comparison`, and `pgdocket versions` shows the last verdict.
- **Calibration, on the same labels.** With 30 or more random labels, both versions are calibrated on them as `calibrate` would do it. The report shows each one's calibration error, its guaranteed threshold for the precision target (the active version's, or 90 %), and the share of compared rows it would mark `auto`.
- **Promotion is gated, then recalibrated.** `promote` refuses while the shadow version hasn't answered every row the active one answers, because those rows would show as `pending`. `--force` overrides this. If the old version was calibrated, the new one is fitted on the same labels and precision target in the same transaction, so `auto` keeps working. Labels naming an option the new version lacks count as wrong for it.
- **A shadow version keeps up.** It also judges new and changed rows, so it is complete when promoted. It also costs money while it exists, so `retire` it when the answer is "keep current".
- **Labels.** Labels can name an option that only the shadow version has. Re-labelling a row that was drawn at random keeps it in the random sample, because sampling records how the row was chosen, not who labelled it.

## Experiment: are the option descriptions worth their tokens?

**Setup.**
- The decision is `k8s_route` on `demo.k8s_live`: the 300 Kubernetes issues from the [live replay](ledger.md), each routed to one of 10 SIGs.
- v1 (active) gives each SIG a one-line description ([examples/k8s_sig_options.json](../../examples/k8s_sig_options.json)). v2 uses the same 10 names with no descriptions.
- `compare --sample 300` covered all 300 issues: 300 judgments by v2 and 300 re-asks of v1, about 600 Jev calls for **$0.024**.
- The user's view had 80 random-sample labels. Every issue also has the SIG people applied, so the verdict can be checked against all 300 ([`jevbench comparevalidate`](../../results/compare-k8s-descriptions/validation.md)).
- The 10 exported disagreements were labelled with those human SIGs. The copies in `results/` keep only the key, both answers and the label, not the issue text.

| Labels used | Rows | Labels | Due to the change | Accuracy v1 → v2 | Difference [95 %] | Auto-accept v1 → v2 | Verdict |
| --- | ---: | ---: | --- | --- | --- | --- | --- |
| 80 random-sample labels | 300 | 80 | 3.3 % [1.0, 6.0] | 91.2 % → 91.2 % | +0.0 pp [−3.8, +3.8] | 78.3 % → 74.7 % | no clear difference |
| a 150-row sample, same labels | 150 | 80 | 3.3 % [0.0, 6.7] | 91.2 % → 91.2 % | +0.0 pp [−3.8, +3.8] | 81.3 % → 76.7 % | no clear difference |
| **80 random + the 10 unlabelled disagreements** | 300 | **90** | 3.3 % [1.0, 6.0] | 91.2 % → 91.2 % | **−2.0 pp [−4.0, 0.0]** | 78.3 % → 74.7 % | no clear difference |
| all 300 human labels | 300 | 300 | 3.3 % [1.0, 6.0] | 91.3 % → 89.3 % | −2.0 pp [−4.0, 0.0] | **95.0 % → 90.0 %** | no clear difference |

Auto-accept is the share of compared rows each version would mark `auto` at ≥ 90 % precision (95 % confidence), with both calibrated on the same random labels. The disagreement labels are hand-picked, so they don't enter calibration.

**Findings.**

1. **Dropping the descriptions moves answers, beyond noise.** It changed 4.3 % of answers, against 1.0 % when v1 was simply asked again: 3.3 % [1.0, 6.0] due to the change. Most moves went between `node`, `api-machinery`, `storage` and `scheduling`, the SIGs whose descriptions draw the lines between them ([report](../../results/compare-k8s-descriptions/report.md)).
2. **80 random labels could not see the difference.** Only 3 of the 13 disagreements were among them, and the interval was ±3.8 pp.
3. **Labelling the 10 remaining disagreements gave exactly the all-300-labels answer.** On the 13 issues where the versions disagree, v1 was right 8 times, v2 twice, and neither 3 times. That is −2.0 pp [−4.0, 0.0], with an exact sign test p = 0.11. Ninety labels did the work of 300.
4. **Answer: keep the descriptions.** They cost 14 % more tokens: 1,024 against 884 per issue, about $43 against $37 per million issues at $0.042 per million tokens. Removing them probably costs accuracy. This sample doesn't prove it at 95 %, but v1 won 8 of the 10 disagreements where one version was right. v2 was retired.
5. **The descriptions matter more for automation than for accuracy.** With all 300 labels, v1 could auto-route 95.0 % of issues at the guaranteed 90 % precision, and v2 90.0 %. That's a loss of 5 points of automation for a 2-point accuracy difference. v1 is also better calibrated (error 0.030 against 0.052 on the 80 labels). With only 80 labels, both guarantees need a high threshold and the gap shrinks to 78.3 % against 74.7 %.
6. **A wrong nudge, caught by this check.** A first draft of the report said "no detectable difference, so the cheaper version". The full labels showed that would have been the worse choice. The report now states the worst case ("between 4.0 pp less and 0.0 pp more accurate") and points to labelling the disagreements instead.

## Limits

- **One decision, one change, 300 rows.** The disagreement method holds generally, but the numbers are specific to this change.
- **The labels already existed.** The disagreement labels came from the human SIG labels on each issue, not from new labelling, so the time a person would spend labelling 10 rows wasn't measured.
- **Few disagreements make the bootstrap approximate.** With 13 disagreements, the percentile bootstrap interval is coarse. The exact sign test is the safer reading.
- **The noise baseline is a single re-ask per row.** Its own uncertainty is included in the paired interval.
- **80 labels make the guarantee fragile.** Over 500 random draws of 80 labels from these 300 issues, a 90 % guarantee could be certified in 54 % of draws for v1 and 66 % for v2. When it was, true precision was below 90 % in under 1 % of draws. Whether the auto-accept comparison has anything to compare depends on which rows happened to be labelled. 150–200 labels make it dependable.
- **Building this found a bug.** The guaranteed threshold used to be chosen on cross-fitted calibrated scores and applied on the final calibrator's. On these answers, one fold assignment in 20 left the threshold (0.978) above every row's confidence (at most 0.973). `auto` was empty while `calibrate` reported 21.7 % coverage. Thresholds are now chosen and applied on the model's own score ([ADR 0003](../adr/0003-human-labels-are-the-oracle.md)). Coverage was unchanged, and the result no longer depends on the fold assignment.
- **The sample here was the whole table.** On a large table the result carries to the table through the random sample, and the intervals say how far.
