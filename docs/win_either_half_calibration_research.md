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
random seed 1729, complexity rank 2, family `logistic_regression`, and
`train_median_imputation_and_standard_scaling`. The complete configuration,
including every field and parameter, must match exactly for both targets;
missing, extra, or altered values fail before fitting. Stage 4B does not
reselect or tune the base model.

## Expanding temporal calibration fit

Calibration parameters use only leakage-safe out-of-fold TRAIN base-model
probabilities:

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

“OOF” describes the base-model predictions. The selected calibrator is itself
fitted on the combined 2021-22 through 2023-24 OOF rows. Consequently, its
performance on those same rows is calibration-fit-sample evidence, not
out-of-sample calibrated performance. ATHENA keeps those rows for audit and
retains their identity/base-model OOF metrics, but reports selected-calibration
TRAIN subgroup evaluation as `UNAVAILABLE` with reason
`CALIBRATION_FIT_SAMPLE`. VALIDATION is explicitly selection-sample evidence.
FINAL_TEST is the only independent final calibration evaluation.

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
calibrator. The candidate set and every parameter are exact frozen contracts;
omissions, duplicates, additions, or parameter and complexity drift fail before
calibration fitting.

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
fitting use a `threadpoolctl` limit of 1. The frozen manifest records the
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

Every subgroup row includes both an evaluation role and scope:

- `CALIBRATION_FIT_OOF` / `CALIBRATION_FIT_SAMPLE`;
- `VALIDATION_SELECTION` / `SELECTION_SAMPLE`;
- `FINAL_TEST` / `INDEPENDENT_FINAL_TEST`.

No subgroup silently combines these roles. The exporter reports evaluation
role, split-and-league, split-and-model-probability-band, and
league-and-season dimensions. TEST includes every frozen league and every one
of these five fixed Stage 4A model-probability bands, including explicit
zero-row groups:

- `[0.0,0.2)`
- `[0.2,0.4)`
- `[0.4,0.6)`
- `[0.6,0.8)`
- `[0.8,1.0]`

These are model-probability bands, not bookmaker price bands. Genuine odds and
price-band evaluation remain Stage 5 work.

## Output lifecycle

The reviewed Stage 4B run was generated from a clean worktree with the frozen
local inputs using:

```powershell
python -m scripts.export_win_either_half_calibration_research --manifest-output artifacts/research-manifests/win-either-half-calibration-v1.json --expect-feature-rows 21791 --expect-stage-4-prediction-rows 43582
```

The exporter writes these ignored research outputs atomically:

- `.cache/athena-research/win-either-half/calibration-v1.json`
- `.cache/athena-research/win-either-half/calibrated-predictions-v1.csv`
- `.cache/athena-research/win-either-half/calibration-subgroups-v1.csv`

The small tracked manifest can be verified later with:

```powershell
python -m scripts.export_win_either_half_calibration_research --check artifacts/research-manifests/win-either-half-calibration-v1.json --expect-feature-rows 21791 --expect-stage-4-prediction-rows 43582
```

Generation refuses a dirty tracked worktree or existing outputs unless
`--force` is deliberate. Inputs are read-only, no network request is made, and
no database, row-level output, calibrator object, or production model binary is
committed. The manifest records the clean generator revision. Its existing
revision-relationship policy permits a later artifact-only descendant only
when that manifest is the sole tracked path changed; any other tracked change
fails verification.

## Frozen Stage 4B interpretation

The frozen manifest selects `isotonic_calibration_v1` for Home and
`identity_calibration_v1` for Away. Each target used 10,635 expanding temporal
OOF calibration-fitting rows (with 2020-21 excluded), 3,476 VALIDATION rows,
and 4,048 FINAL_TEST rows.

For Home, isotonic calibration gives a modest aggregate FINAL_TEST improvement:
log loss changes from 0.653048479324 to 0.649747309432, Brier score from
0.230023921580 to 0.228957360638, and ECE from 0.043758010704 to
0.037185180715. Calibration remains imperfect: its TEST slope is
0.749546866238, still below 1. ROC-AUC and average precision decline by
0.002043156794 and 0.008827249022 respectively. Ten of twelve supported
leagues improve both log loss and Brier score; I1 worsens both, while E0 is
mixed and approximately neutral. ECE does not improve in every league. The
largest band improvement occurs in the LOW_SUPPORT `[0.0,0.2)` band, while
supported probability bands improve or are effectively neutral.

For Away, learned calibration candidates did not improve VALIDATION, so
identity calibration correctly remains selected. Identity-versus-selected
TEST and subgroup deltas are therefore exactly zero.

Calibration improvement and subgroup stability are research evidence only.
They do not establish bookmaker value or production readiness. Both Home and
Away Win Either Half remain `DISABLED`.
