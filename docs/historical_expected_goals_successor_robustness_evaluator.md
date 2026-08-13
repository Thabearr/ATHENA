# Successor robustness evaluator

PR76 implements deterministic research machinery for the PR75 protocol. It does not execute the reviewed 66-file corpus during development, and it records no real robustness, same-fixture calibration, no-fatigue, or leave-one-season result.

The synthetic seam computes same-fixture paired NLL differences, the frozen 22-cluster delete-one jackknife, leave-one sensitivity, model-specific calibration bins and WACE/WSCE, five-column no-fatigue fitting, and strict non-zero fatigue sign checks. Synthetic records are not historical evidence.

The result wrapper binds PR74 and PR75 canonical identities, uses canonical JSON and all-false safety flags, and is research-only: no model approval, score matrix, probability inference, pricing, selection, or betting authority follows. A future real-corpus execution must reconstruct PR69/PR73 ancestry before it can use the evaluator.
