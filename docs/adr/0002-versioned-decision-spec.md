# ADR 0002: The versioned decision spec is the unit of deployment

- Status: Proposed
- Date: 2026-10-17

## Context

Decision-model probabilities are conditional on everything in the request. Adding an option changes every other option's probability (label-set drift), option order matters (Jev documents a first-option bias), and the same question gets different scores on different backends or model versions. The pg-jev article states it directly: the deployable unit is model, prompt, tokenizer, label set and threshold, versioned together.

## Decision

A `decision_version` stores a canonical JSON spec and its `spec_hash`. The hash covers:

- backend and pinned model version (never `*-latest` for an active version),
- prompt/question template version and the question text,
- options **in order**, and the kind (`noul` / `choice` / `score`),
- input projection (which columns are sent, plus any redaction rule),
- order-debiasing setting,
- calibrator id and threshold policy id.

Changing any of these creates a new version in `shadow` status. Phase 0 also showed that the backend is not deterministic: identical requests to jev-1.13.0 changed the top answer for 4.8 % of rows across three runs. Re-judging therefore can't reproduce a past decision, and the stored judgment is the record. A shadow version is judged on the gold set and a random sample, and `docket.diff` reports flip rate, calibration shift and gold accuracy. `promote` makes it `active` only if its policy (e.g. a precision guarantee) is feasible. Judgments are never mutated; they belong to exactly one version.

## Consequences

- Every stored decision can be traced to the exact spec that produced it.
- Gold labels attach to the decision and an options-set hash. When the label set changes, old labels need an explicit remap, and pgdocket refuses to reuse them silently.
- Storage grows with versions. Retired versions can be compacted to summary statistics.
- **Batching (resolved by Phase 0, FINDINGS §9–§10):** with 20 rows per request, changing a row's batch neighbours changed its top answer for ~16 % of rows (≈ 5× run-to-run noise). Judging rows one at a time was 2.4 pp more accurate (+0.05 macro-F1) at 1.8× the tokens (~$24 per million rows). **Decision: pgdocket judges one row per request by default.** Batch size stays part of the spec hash, so a version that opts into batching is a different version.
