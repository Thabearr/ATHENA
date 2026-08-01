# Win Either Half baseline research benchmarks

Stage 4A measures transparent probability baselines against the frozen Win
Either Half feature dataset. It does not approve, calibrate, deploy, or expose
a model. It does not use bookmaker odds or calculate betting value. Home and
Away Win Either Half remain disabled.

## Frozen inputs and predictor boundary

The exporter verifies the Stage 2 evidence baseline, Stage 3 label manifest,
Stage 3 feature manifest, and the local feature CSV. The CSV must match the
committed feature manifest's SHA-256, byte size, row count, schema, season
assignments, and split counts before parsing continues.

Only columns whose frozen role is `PRE_MATCH_FEATURE` are predictors. The
exporter rejects identifier, split-metadata, and target-only columns even if a
caller requests them. Fixture identity, kickoff, team names, league, season,
split, both Win Either Half labels, and `both_teams_won_a_half` are never model
inputs. Audit fields are retained only for deterministic row identity and split
selection.

## Frozen temporal protocol

- TRAIN: 2020-21 through 2023-24, 14,267 rows.
- VALIDATION: 2024-25, 3,476 rows.
- TEST: 2025-26, 4,048 rows.

TRAIN fits preprocessing and every candidate model. VALIDATION compares the
already-fitted candidates and selects one winner independently for each target.
TEST is not transformed or evaluated until both validation winners have been
fixed. It is evaluated once for the selected model only. TEST never selects a
feature, model, regularization value, threshold, or preprocessing statistic.
Random splitting is forbidden.

Training estimates model parameters. Validation makes a predefined research
choice among candidates. Test provides one final untouched estimate after that
choice. Reusing TEST to improve the choice would make its reported performance
optimistic and invalidate the protocol.

## Preprocessing

All predictors are numeric. Missing values are replaced with the corresponding
TRAIN median. Logistic candidates then use the TRAIN mean and TRAIN population
standard deviation for scaling; a zero TRAIN standard deviation uses scale 1.
The tree receives median-imputed, unscaled values. A predictor with no observed
TRAIN value fails closed. Existing explicit missingness indicators remain in
the predictor allowlist, and missing counts are reported for every split before
and after transformation. No validation, test, whole-dataset, or season-end
statistic is used.

## Candidate models

Each target is benchmarked independently with random seed 1729:

- `constant_train_prevalence_v1`: every probability is the target's TRAIN
  prevalence. It cannot inspect VALIDATION or TEST prevalence.
- `logistic_unregularized_v1`: deterministic `lbfgs` logistic regression with
  `C=1e12`, an explicit effectively-unregularized baseline that avoids
  version-dependent deprecated penalty arguments.
- `logistic_l2_c0.1_v1`, `logistic_l2_c1_v1`, and
  `logistic_l2_c10_v1`: the complete predefined L2 grid. Each C value is a
  separate validation candidate; TEST never tunes C.
- `decision_tree_depth4_leaf50_v1`: one deterministic nonlinear baseline with
  maximum depth 4 and minimum leaf size 50. There is no tree search.

Candidate identifiers, parameters, preprocessing, dependency versions, and
random seeds are machine-readable in the future manifest.

Any `ConvergenceWarning` from a benchmark logistic candidate fails the run and
the candidate cannot participate in validation selection. Reaching the
configured maximum iteration count is treated the same way. Calibration
intercept/slope fitting is optional diagnostic work: if it does not converge,
both coefficients are null and its machine-readable status is `UNAVAILABLE`
with reason `NON_CONVERGENCE`.

## Selection and metrics

The selection rule is fixed before evaluation:

1. lower VALIDATION log loss;
2. lower VALIDATION Brier score;
3. lower declared complexity rank;
4. lexical model identifier.

Accuracy does not select a model because it discards the magnitude and quality
of continuous probability estimates. Log loss strongly penalizes confident
errors; Brier score is mean squared probability error. ROC AUC measures ranking
across classes but can obscure probability quality. Average precision focuses
on positive-class ranking and depends on prevalence. None alone proves useful
betting performance.

TRAIN, VALIDATION, and the selected TEST evaluation report rows, positives,
prevalence, log loss, Brier score, ROC AUC, and average precision. Probability
diagnostics report minimum, maximum, mean, non-finite count, and out-of-range
count. Probabilities must be finite and in `[0, 1]`.

Thresholds 0.50, 0.60, and 0.70 report qualifying count, precision, and recall.
They are descriptive only and never select a candidate or become a production
decision rule.

Calibration uses deterministic, approximately equal-frequency bins. A group of
identical predicted probabilities is never split between bins, so ties can
reduce the actual bin count below the requested ten. A constant prediction
vector therefore produces exactly one bin. Each bin reports predicted mean and
observed rate, and the actual bin count is recorded.
Expected calibration error is:

`sum(bin_count / total * abs(predicted_mean - observed_rate))`

Calibration intercept and slope are reported when both classes and varying
logits make them mathematically available. These are diagnostics, not fitted
probability calibration. Platt scaling, isotonic regression, and any other
calibration fitting belong to a later phase.

## Numerical reproducibility contract

Model fitting, probability prediction, and calibration-diagnostic fitting run
under a `threadpoolctl` numerical thread limit of 1. Probabilities are
canonicalized to 12 decimal places before metrics, validation selection, and
CSV serialization. Reported metric floats use the same precision. Thus the
metrics are calculated from the exact canonical probabilities written to the
prediction CSV, and differences below this declared precision cannot change a
winner. Differences at or above the precision remain observable.

The future manifest records the precision and thread policy plus Python version
and implementation, operating-system family, machine architecture, NumPy,
SciPy, scikit-learn and threadpoolctl versions, and deterministically sorted
normalized BLAS/OpenMP runtime information. Library filesystem paths are never
recorded. Verification fails with a specific numerical-runtime error if that
contract changes.

The artifact is intentionally bound to its recorded numerical runtime. Decimal
canonicalization removes meaningless final-bit variation, but ATHENA does not
claim that different platforms, architectures, dependency builds, or BLAS
implementations are mathematically identical.

## Frozen Stage 4A interpretation

The committed Stage 4A manifest freezes the verified benchmark and prediction
file identities without committing their row-level contents. Under the
preregistered validation rule, both independent targets selected
`logistic_l2_c0.1_v1`. Its validation margins over `logistic_l2_c1_v1` are
small and must not be overinterpreted.

On TEST, the selected baselines remain better than the TRAIN-prevalence
constant baseline, but calibration deteriorates, especially for the home
target. This is evidence for further research, not approval of a probability
model. It does not demonstrate bookmaker value, select a betting threshold, or
authorize either Win Either Half market.

## Local generation and verification

The frozen artifact was generated from a clean worktree with the command below.
The row-level outputs remain ignored:

```powershell
python -m scripts.export_win_either_half_baseline_benchmarks --database database/athena.db --cache-directory .cache/football-data-uk --baseline artifacts/evidence-baselines/half-time-ready-for-research.json --label-manifest artifacts/research-manifests/win-either-half-labels-v1.json --feature-manifest artifacts/research-manifests/win-either-half-features-v1.json --feature-csv .cache/athena-research/win-either-half/features-v1.csv --benchmark-output .cache/athena-research/win-either-half/benchmarks-v1.json --predictions-output .cache/athena-research/win-either-half/predictions-v1.csv --manifest-output artifacts/research-manifests/win-either-half-benchmarks-v1.json --expect-total-rows 21791 --expect-train-rows 14267 --expect-validation-rows 3476 --expect-test-rows 4048
```

Verify a later committed manifest with:

```powershell
python -m scripts.export_win_either_half_baseline_benchmarks --database database/athena.db --cache-directory .cache/football-data-uk --baseline artifacts/evidence-baselines/half-time-ready-for-research.json --label-manifest artifacts/research-manifests/win-either-half-labels-v1.json --feature-manifest artifacts/research-manifests/win-either-half-features-v1.json --feature-csv .cache/athena-research/win-either-half/features-v1.csv --check artifacts/research-manifests/win-either-half-benchmarks-v1.json
```

The JSON summary and predictions CSV are UTF-8 with LF line endings and remain
under `.cache/athena-research/`. No model binary is written. The committed
manifest fingerprints inputs, outputs, configurations, dependencies,
selections, and market safety, but it does not prove causal validity,
generalization to future seasons, calibration quality, bookmaker value, or
production readiness.

Predictive performance alone cannot establish value: genuine exact-selection
bookmaker prices and a separate pricing evaluation would still be required.
Neither Win Either Half market is enabled by Stage 4A.
