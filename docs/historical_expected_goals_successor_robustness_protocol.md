# Successor robustness, calibration, and fatigue protocol

PR75 freezes the post-hoc follow-up analysis for the PR74 successor result before any such analysis is executed. Its scope is `POST_HOC_PR74_FOLLOWUP_PRE_REGISTERED_BEFORE_ROBUSTNESS_EXECUTION`: it was designed after seeing PR74, uses the same 2024-25 and 2025-26 retrospective evaluation population, and is neither an untouched holdout, prospective validation, nor independent replication.

The protocol binds the exact canonical PR74 receipt and its embedded PR73 successor candidate. It contains no fixture losses, robustness estimates, calibration comparison, refit, coefficient, or result.

## Paired NLL robustness

The primary comparison is successor minus `PR68_ELO_FALLBACK_COMPONENT` joint Poisson NLL for the same fixture across all 6,903 evaluation fixtures. The full estimate is the fixture-weighted arithmetic mean of all paired differences. The dependence-aware cluster unit is exactly `(season, identity_league)`: the ordered Cartesian product of the two evaluation seasons and eleven frozen identity leagues, therefore exactly 22 clusters. Every one of the 6,903 fixtures must belong to one and only one frozen cluster; unknown, missing, merged, or alternative clusters fail closed. Delete-one-cluster estimates remain fixture weighted, rather than equally averaging cluster means. Their center is the unweighted arithmetic mean of exactly the 22 delete-one estimates, never weighted by their remaining fixture counts. The protocol freezes the jackknife standard error and nominal two-sided 95% normal interval; it does not permit a later bootstrap or an alternative interval.

It also freezes leave-one-league-out sensitivity over both evaluation seasons and leave-one-season-out sensitivity. These are diagnostics on the already-observed evaluation population, not independent tests.

## Same-population calibration

Successor and legacy Elo must both be evaluated on the exact same 6,903 PR74 fixtures. PR71's larger calibration population cannot be reused as the comparator. Each model assigns its own predicted rate to the frozen bins. The descriptive absolute bias, weighted absolute calibration error, and weighted squared calibration error have fixed formulas; no smoothing, tail-bin merging, minimum-bin rule, calibration fitting, approval rule, or significance claim is permitted.

## Fatigue diagnostics

The immutable PR74 full successor is not changed. Membership is frozen before ablation as the exact PR73 successor-eligible fixture set reconstructed from the bound PR69 corpus: 14,130 training rows (3,517 / 3,566 / 3,536 / 3,511 by training season) and the same 6,903 evaluation rows (3,468 / 3,435). The only alternative refit is `NO_FATIGUE_ABLATION`, which removes fatigue entirely from that already-frozen design matrix; it may not rerun eligibility under reduced predictors. Four further full-model diagnostic refits omit exactly one named training season from that same PR73 eligible set—without rerunning eligibility—and leave the exact 6,903 evaluation rows unchanged, leaving 10,613, 10,564, 10,594, and 10,619 training rows respectively. They cannot select or replace a coefficient.

PR69 fatigue remains `0.30` when home rest days minus away rest days is below `-2`, `0.10` when below `0`, otherwise `0.00`. Positive fatigue therefore means the home side had fewer rest days. The existing signs are directionally counterintuitive under a simple causal fatigue-disadvantage story, and `fatigue_pr31_semantic_equivalence` remains `UNPROVEN`. A home or away fatigue sign is stable only if every leave-one-training-season coefficient has the same strict non-zero sign as the corresponding immutable PR74 full-model coefficient; zero and every sign flip are unstable.

## Safety

This protocol authorizes no successor approval, production expected-goals use, score matrix, probability inference or adjustment, production calibration, pricing, market activation, selection, or betting. A later evaluator can report only the pre-registered factual fields; human interpretation remains separate.
