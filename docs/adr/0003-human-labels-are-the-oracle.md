# ADR 0003: Human labels are the scarce oracle; every statistical claim derives from them

- Status: Proposed
- Date: 2026-10-17

## Context

Semantic query research (LOTUS, BARGAIN, SUPG-IT, Cortex AISQL cascades) treats the LLM as the expensive oracle. At Jev's price (~$0.042 per M input tokens, roughly $6–7 per million rows) model calls are close to free, so the scarce resource is now human verification. Studies applying Jev (e.g. police crash narratives, arXiv 2609.24052) found that calibration varies by model and task, and that recalibrating on task labels cut calibration error 3.3×.

## Decision

- Gold labels are drawn by stratified random sampling over predicted probability, and each label stores its **inclusion probability**. Pure uncertainty sampling is not used for gold, because it biases estimates. It may feed a separate "hard cases" queue that is never used for statistics.
- Calibration (Platt, isotonic, temperature) is fitted per (decision version × backend) on gold labels. Phase 0 showed that Jev reports probabilities on a 0.01 grid with exact zeros, which makes unfloored NLL-based fits (temperature) worse than no calibration. Floor at half the grid step before any NLL-based method. The Phase 0 learning curve showed that one-parameter calibrators (floored temperature for choice, Platt for yes/no) beat isotonic at every budget up to 500 labels, and about 100 labels already remove 45–85 % of the raw ECE. Default to parametric; offer isotonic once a decision has ≥ 1,000 labels.
- Thresholds with targets ("precision ≥ 0.95 with probability ≥ 1 − δ") use fixed-sequence testing with exact (Clopper–Pearson) or betting confidence bounds on gold labels.
- Aggregates (`estimate_count`, `estimate_share`) use prediction-powered inference, importance-weighted when sampling was stratified, and refuse to answer when gold coverage in the requested scope is too thin.
- Every guarantee is backed by a simulation coverage test in CI.

## Consequences

- Docket's numbers are only as good as the sampling assumptions. The docs must state them: gold drawn from the same population, labels correct, distribution stable since labeling.
- Drift monitoring (Phase 3) has to tell the user when gold labels are stale.
- The review queue becomes a core feature rather than an add-on.
