# Successor robustness evaluator

PR76 implements deterministic, research-only machinery for the PR75 protocol. It does not execute the reviewed 66-file corpus during development and records no real robustness, same-fixture calibration, no-fatigue, or leave-one-training-season result.

There are deliberately two boundaries. `evaluate_successor_robustness_fixture_set` and `build_historical_expected_goals_successor_robustness_evaluation` are structural/synthetic only (`SYNTHETIC_STRUCTURAL_ONLY_NOT_SOURCE_VALIDATED`); their outputs cannot establish historical evidence provenance. The source-bound builder and full source-bound revalidator reconstruct PR69, reproduce and fully revalidate PR73, revalidate PR75, reconstruct the frozen fixture population, recompute every statistic, and then require exact object and canonical-byte parity (`SOURCE_BOUND_FULL_PR69_TO_PR75_REPLAY`). Structural validation is therefore not source-evidence validation.

Two PR69 hash domains are checked separately and must never be substituted for one another:

- raw source-corpus SHA-256: `c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0`;
- canonical PR69 corpus SHA-256: `b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3`, size `39,952,730` bytes.

The source-bound path also requires the reviewed receipt anchors of 66 files, 10,006,877 bytes, and 21,226 fixtures. It requires the exact PR73 population: 14,130 training fixtures and 6,903 evaluation fixtures, the exact 22 season×league clusters, the four frozen leave-one-training-season refits, and the complete no-fatigue refit. Identifier sets are used for the train/evaluation split so membership is explicit and disjoint.

The synthetic seam computes same-fixture paired NLL differences, the frozen 22-cluster delete-one jackknife, leave-one-league and leave-one-season sensitivity, model-specific calibration bins and WACE/WSCE, a five-column no-fatigue refit, and strict fatigue sign checks. Calibration uses lower-inclusive, upper-exclusive bins and each model's own predicted rates. Result validation requires the nominal interval to derive exactly from `theta ± 1.96 * SE`, calibration deltas to derive from the corresponding successor/ELO summaries, and duplicated fatigue scalars to equal the fitted coefficient vectors.

The generic Poisson adapter reuses PR73's frozen numerical primitives. Its six-dimensional parity regression uses a genuinely varying full-rank design, requires both PR73 home and away fits to perform Newton updates, and then requires exact equality of coefficients, update counts, convergence norms, and rounded-coefficient training NLL. The five-dimensional no-fatigue path omits only fatigue; it does not re-run eligibility.

Every canonical evaluation artifact carries the immutable lineage caveats:

- Elo initialization: `1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE`;
- fatigue PR31 semantic equivalence: `UNPROVEN`;
- historical freshness regime reconstructed: `false`.

No robustness, calibration, ablation, or diagnostic-refit result can upgrade these semantics. Source-bound artifacts also retain the exact PR74 full-model fatigue coefficients rather than interpreting or changing them.

Result payloads have an exact validated shape, recursively detached immutable structures, fixed record order, deterministic canonical JSON, and all-false safety flags. The ten factual interpretation booleans are derived from the numeric result fields rather than caller assertions. A coordinated mutation of a source-bound object and its bytes cannot survive the full source-bound replay/parity gate.

PR76 is research infrastructure only: no model approval, score matrix, probability inference, probability adjustment, production calibration, pricing, market activation, selection, production approval, or betting authority follows. No real robustness result was observed while implementing this PR.