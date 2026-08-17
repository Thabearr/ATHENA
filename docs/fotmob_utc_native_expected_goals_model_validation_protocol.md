# FotMob UTC-native expected-goals model validation protocol

## Boundary

This PR pre-registers the next ATHENA model-validation experiment. It is **result-free**: merging it does not fit a model, calculate a score matrix, produce market probabilities, inspect bookmaker prices, select bets, or authorize production.

The protocol is bound to the successful V2 UTC-native feature qualification:

- run `31990121181`
- result comment `5311318782`
- evidence artifact `9275052993`
- artifact SHA-256 `f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb`
- qualified projection SHA-256 `5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed`
- 21,326 rows / 21,326 unique fixtures / zero identity-lineage conflicts
- 21,129 complete cases for form + overall Elo + fatigue

Historical `live_data_freshness` remains `NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE` and is not a numeric model input.

## Why the existing historical successor family is reused

ATHENA already pre-registered, fit, and robustness-tested a two-response home/away Poisson log-link GLM. Its predictor mathematics match the new FotMob feature projection: centered/scaled overall Elo, centered form, and raw fatigue. The historical study showed a strong retrospective signal, but it retained unresolved source-local chronology and explicitly granted no production authority.

The new V2 projection changes the evidence/chronology regime: canonical timezone-aware UTC, strict prior history, and exact same-kickoff batching. This protocol therefore tests the same reviewed model family on that newly qualified regime instead of silently replacing it with a new sklearn model family or tuning scheme.

“Reuse exact historical successor deterministic fitter” is a transitive contract against the pinned historical protocol blob `f0b3a070bcf235a097dd737d715f9d6162505509`, not permission to reimplement only the headline constants. The later implementation must preserve that protocol's deterministic `math.fsum` reductions, training-row ordering semantics adapted only from source-local kickoff to canonical UTC kickoff, response fit order, log-of-training-response-mean intercept initialization, zero non-intercept initialization, Newton system, partial-pivot linear solve, backtracking line search, convergence rule, 200-iteration ceiling, `1e-8` gradient tolerance, `0.5` backtracking factor, `2^-20` minimum step, `20.0` absolute linear-predictor guard, `1e-12` pivot tolerance, 12-place coefficient rounding, no hyperparameter search, and no post-evaluation refit. Any implementation that substitutes different fitting mechanics fails the protocol lineage gate.

The old `models/goals_model.joblib` is separately quarantined: it is a legacy Random Forest regressor for **total match goals**, trained from a different feature family. It is not a home/away expected-goals transform. The one-byte `models/expected_goals.py`, `models/poisson.py`, and `models/dixon_coles.py` placeholders are not treated as implementations.

## Frozen model arms

The later implementation must evaluate exactly five arms:

1. `FOTMOB_NATIVE_SAME_FAMILY_REFIT` — train-only refit using the exact reviewed deterministic Newton Poisson-GLM fitter.
2. `HISTORICAL_FIXED_COEFFICIENT_TRANSFER` — apply the exact historical home/away coefficients without refitting.
3. `FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM` — train-only nested Elo comparator with the same fitter.
4. `FOTMOB_NATIVE_NO_FATIGUE_ABLATION` — train-only form+Elo ablation with the same fitter.
5. `TRAIN_ONLY_GLOBAL_HOME_AWAY_MEAN_BASELINE` — constant train-only home/away goal means.

No regularization search, alpha grid, random split, generic K-fold, sklearn PoissonRegressor substitution, predictor re-standardization, or post-evaluation refit is authorized.

## Frozen predictors

Complete rows require all five numeric predictors:

- `(home_elo - 1500) / 400`
- `(away_elo - 1500) / 400`
- `home_form - 0.5`
- `away_form - 0.5`
- raw `fatigue`

Missing form/fatigue remains missing; 197 rows are excluded from this model-validation population rather than imputed. Fixture/team identifiers and evidence references are lineage only, never predictors.

## Chronological populations

Same-kickoff fixtures must remain in the same partition.

| Population | UTC interval | Complete rows |
|---|---|---:|
| Train | 2020-08-01 inclusive to 2024-07-01 exclusive | 14,181 |
| Evaluation A | 2024-07-01 inclusive to 2025-07-01 exclusive | 3,471 |
| Evaluation B | 2025-07-01 inclusive to 2026-08-15 exclusive | 3,477 |

Evaluation B is deliberately labeled **chronologically later retrospective evaluation, not prospective holdout**. These outcomes already existed before this protocol was written; the protocol must not manufacture a prospective claim.

## Evaluation

Primary metric: mean joint Poisson negative log-likelihood.

Secondary diagnostics include home/away NLL, bias, MAE, RMSE, WACE and WSCE using the frozen historical calibration bins. Required comparisons include native-refit versus Elo-only, historical fixed transfer, constant baseline, plus the no-fatigue ablation.

Temporal robustness uses UTC calendar-year-quarter clusters and reports every leave-one-quarter-out paired native-minus-Elo NLL estimate, jackknife standard error, and normal-approximation 95% interval.

The qualified projection does **not** carry competition/league identity. Competition or league robustness is therefore explicitly `BLOCKED_PROJECTION_DOES_NOT_CARRY_COMPETITION_IDENTITY`; no league may be invented or fuzzily reconstructed in this boundary.

## Interpretation rule

A `STRONG_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED` result requires all lineage/split checks, convergence of both native fits, native-refit NLL improvement over Elo-only in Evaluation A, Evaluation B and pooled evaluation, a quarter-jackknife upper 95% bound below zero, and lower home/away WACE and WSCE than Elo-only.

Anything else becomes `MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED`.

Neither state is automatic model approval. Historical-transfer and no-fatigue comparisons are report-only diagnostics.

## Safety

All model-approval, probability, ScoreMatrix, calibration-for-production, pricing, market activation, selection, production and BET authority remains exact `false`.

After this protocol is merged and verified, the next separate reviewed boundary is:

`IMPLEMENT_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION`
