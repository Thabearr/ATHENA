# Win Either Half calibration and stability research

Stage 4B tests whether the frozen Stage 4A probabilities benefit from
calibration and whether their descriptive performance is stable across
predeclared subgroups. It does not add bookmaker odds, estimate betting value,
select a production threshold, deploy a model, or enable either Win Either Half
market.

## Frozen inputs and base models

The exporter verifies the complete Stage 2 evidence, Stage 3 label and feature
ancestry, and Stage 4A benchmark ancestry before fitting. It also verifies the
exact byte size and SHA-256 of the local feature CSV, Stage 4A benchmark JSON,
and 43,582-row Stage 4A prediction CSV. The feature allowlist, targets, split
seasons, split counts, selected model identifiers, numerical policy, and market
safety must match their committed manifests.

Home and Away are independent targets. Both retain the frozen
`logistic_l2_c0.1_v1` base configuration: `lbfgs`, `C=0.1`, `max_iter=2000`,
random seed 1729, TRAIN-median imputation, and TRAIN mean/population-standard-
deviation scaling. Stage 4B does not reselect or tune the base model.

## Expanding temporal calibration fit

Calibration parameters use only leakage-safe out-of-fold TRAIN probabilities:

- fit 2020-21, predict 2021-22;
- fit 2020-21 through 2021-22, predict 2022-23;
- fit 2020-21 through 2022-23, predict 2023-24.

There is no prediction for 2020-21 because no earlier frozen TRAIN season
exists. Every fold refits preprocessing and the frozen base model using only its
listed earlier seasons. No future or same/later-season row contributes to that
fold.

After calibrators are fitted from the combined out-of-fold predictions, the
base model is fitted on all frozen TRAIN rows and predicts VALIDATION. Each
target selects a calibrator independently on VALIDATION. Both selections are
frozen before TEST is transformed or evaluated. TEST never changes fitting,
selection, parameters, probability bands, subgroup rules, or thresholds.

## Calibration candidates

- `identity_calibration_v1` has complexity rank 0 and returns the canonical
  Stage 4A probability unchanged.
- `platt_logit_calibration_v1` has complexity rank 1 and fits
  `sigmoid(intercept + slope * logit(p))` with `lbfgs`, `C=1e12`,
  `max_iter=2000`, random seed 1729, and logit-only clipping epsilon `1e-6`.
  Any convergence warning or iteration-limit exhaustion fails closed.
- `isotonic_calibration_v1` has complexity rank 2, is increasing, requires at
  least three unique model probabilities and two observed outcome classes, and
  uses `out_of_bounds="clip"` so transformed values beyond the fitted input
  range use fitted boundary values.

Unavailable candidates remain in the audit with an explicit reason such as
`SINGLE_CLASS` or `INSUFFICIENT_UNIQUE_PROBABILITIES`.

The selection rule is fixed before evaluation:

1. lower canonical VALIDATION log loss;
2. lower canonical VALIDATION Brier score;
3. lower declared calibration complexity rank;
4. lexical candidate identifier.

Identity always participates. Accuracy and threshold diagnostics never select a
calibrator.

## Metrics and numerical policy

Identity and calibrated probabilities report rows, positives, prevalence, log
loss, Brier score, ROC-AUC, average precision, probability range and mean,
invalid-probability counts, deterministic tie-preserving reliability bins,
actual bin count, expected calibration error, and calibration intercept/slope.
Unavailable diagnostics use a machine-readable status and reason rather than
fabricated coefficients. Candidate and subgroup reports include deltas from
identity for log loss, Brier score, expected calibration error, ROC-AUC, and
average precision.

Thresholds 0.50, 0.60, and 0.70 are descriptive only. Probabilities and metric
floats are canonicalized to 12 decimal places before metrics, selection, and
serialization. Model fitting, prediction, calibration fitting, and diagnostic
fitting use a `threadpoolctl` limit of 1. The future manifest records the
numerical runtime and fails verification with a specific runtime-drift error.

## Predeclared subgroup stability policy

The minimum supported subgroup size is 100 rows. This rule is fixed before TEST
evaluation and is not tuned from results:

- `SUPPORTED`: at least 100 rows;
- `LOW_SUPPORT`: 1 through 99 rows, reason `INSUFFICIENT_ROWS`;
- `UNAVAILABLE`: zero rows, reason `INSUFFICIENT_ROWS`.

Metrics are still descriptive for low-support groups. Single-class groups keep
their row and outcome accounting while mathematically unavailable ROC-AUC,
average precision, or calibration coefficients remain null with explicit
reasons.

The exporter evaluates identity and the selected calibrator by split, season,
league, league-and-season, and these fixed Stage 4A model-probability bands:

- `[0.0,0.2)`
- `[0.2,0.4)`
- `[0.4,0.6)`
- `[0.6,0.8)`
- `[0.8,1.0]`

These are model-probability bands, not bookmaker price bands. Genuine odds and
price-band evaluation remain Stage 5 work.

## Output lifecycle

After this tooling PR is merged, a clean worktree with the frozen local inputs
can generate:

```powershell
python -m scripts.export_win_either_half_calibration_research --manifest-output artifacts/research-manifests/win-either-half-calibration-v1.json --expect-feature-rows 21791 --expect-stage-4-prediction-rows 43582
```

The exporter writes these ignored research outputs atomically:

- `.cache/athena-research/win-either-half/calibration-v1.json`
- `.cache/athena-research/win-either-half/calibrated-predictions-v1.csv`
- `.cache/athena-research/win-either-half/calibration-subgroups-v1.csv`

The small manifest can be verified later with:

```powershell
python -m scripts.export_win_either_half_calibration_research --check artifacts/research-manifests/win-either-half-calibration-v1.json --expect-feature-rows 21791 --expect-stage-4-prediction-rows 43582
```

Generation refuses a dirty tracked worktree or existing outputs unless
`--force` is deliberate. Inputs are read-only, no network request is made, and
no database, row-level output, calibrator object, or production model binary is
committed by this tooling PR.

Calibration improvement and subgroup stability are research evidence only.
They do not establish bookmaker value or production readiness. Both Home and
Away Win Either Half remain `DISABLED`.
