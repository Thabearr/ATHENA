# Successor robustness, calibration, and fatigue protocol

PR75 freezes the post-hoc follow-up analysis for the PR74 successor result before any such analysis is executed. Its scope is `POST_HOC_PR74_FOLLOWUP_PRE_REGISTERED_BEFORE_ROBUSTNESS_EXECUTION`: it was designed after seeing PR74, uses the same 2024-25 and 2025-26 retrospective evaluation population, and is neither an untouched holdout, prospective validation, nor independent replication.

The protocol binds the exact canonical PR74 receipt and its embedded PR73 successor candidate. It contains no fixture losses, robustness estimates, calibration comparison, refit, coefficient, or result.

## Paired NLL robustness

The primary comparison is successor minus `PR68_ELO_FALLBACK_COMPONENT` joint Poisson NLL for the same fixture across all 6,903 evaluation fixtures. The dependence-aware cluster unit is exactly `(season, identity_league)`: 22 season-league clusters. Delete-one-cluster estimates remain fixture weighted, rather than equally averaging cluster means. The protocol freezes the jackknife standard error and nominal two-sided 95% normal interval; it does not permit a later bootstrap or an alternative interval.

It also freezes leave-one-league-out sensitivity over both evaluation seasons and leave-one-season-out sensitivity. These are diagnostics on the already-observed evaluation population, not independent tests.

## Same-population calibration

Successor and legacy Elo must both be evaluated on the exact same 6,903 PR74 fixtures. PR71's larger calibration population cannot be reused as the comparator. Each model assigns its own predicted rate to the frozen bins. The descriptive absolute bias, weighted absolute calibration error, and weighted squared calibration error have fixed formulas; no smoothing, tail-bin merging, minimum-bin rule, calibration fitting, approval rule, or significance claim is permitted.

## Fatigue diagnostics

The immutable PR74 full successor is not changed. The only alternative refit is `NO_FATIGUE_ABLATION`, which omits fatigue entirely while retaining the PR72/73 fitting structure, eligible rows, training/evaluation seasons, solver, line search, convergence, and rounding. Four further full-model diagnostic refits omit exactly one training season each; they cannot select or replace a coefficient.

PR69 fatigue remains `0.30` when home rest days minus away rest days is below `-2`, `0.10` when below `0`, otherwise `0.00`. Positive fatigue therefore means the home side had fewer rest days. The existing signs are directionally counterintuitive under a simple causal fatigue-disadvantage story, and `fatigue_pr31_semantic_equivalence` remains `UNPROVEN`.

## Safety

This protocol authorizes no successor approval, production expected-goals use, score matrix, probability inference or adjustment, production calibration, pricing, market activation, selection, or betting. A later evaluator can report only the pre-registered factual fields; human interpretation remains separate.
