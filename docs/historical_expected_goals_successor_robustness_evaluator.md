# Successor robustness evaluator

PR76 implements deterministic, research-only machinery for the PR75 protocol. It does not execute the reviewed 66-file corpus during development and records no real robustness, same-fixture calibration, no-fatigue, or leave-one-season result.

There are deliberately two boundaries. `evaluate_successor_robustness_fixture_set` and the lightweight wrapper are structural/synthetic only (`SYNTHETIC_STRUCTURAL_ONLY_NOT_SOURCE_VALIDATED`); their results cannot establish historical evidence provenance. The future source-bound builder and its full revalidator reconstruct PR69, reproduce and fully revalidate PR73, revalidate PR75, reconstruct the frozen population, recompute every statistic, and then require object and canonical-byte equality (`SOURCE_BOUND_FULL_PR69_TO_PR75_REPLAY`). A coordinated mutation of a source-bound result and its bytes therefore cannot survive full replay.

Two PR69 hash domains are checked separately and must never be substituted for one another:

- Raw source-corpus SHA-256: `c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0`.
- Canonical PR69 corpus SHA-256: `b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3`, size `39,952,730` bytes.

The source-bound path also requires the preserved source receipt of 66 files, 10,006,877 bytes, and 21,226 fixtures. It uses immutable identifier sets for the PR73 training/evaluation split rather than quadratic object-membership scans.

The synthetic seam computes same-fixture paired NLL differences, the frozen 22-cluster delete-one jackknife, leave-one sensitivity, model-specific calibration bins and WACE/WSCE, a five-column no-fatigue refit, and strict fatigue sign checks. It reuses PR73's numerical primitives; the six-column adapter has a parity regression against PR73's public fitting seam. Calibration uses lower-inclusive, upper-exclusive bins and each model's own rates. Synthetic records are not historical evidence.

Result payloads have an exact validated shape, recursively detached immutable structures, fixed record order, deterministic canonical JSON, and all-false safety flags. The factual booleans are derived from numeric fields, not caller assertions. A fatigue stability boolean is false unless all four actual leave-one-training-season refits have the same strict non-zero sign as the full model.

PR76 is research infrastructure only: no model approval, score matrix, probability inference, pricing, selection, or betting authority follows. No real robustness result was observed while implementing this PR.
