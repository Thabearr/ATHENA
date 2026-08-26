# Goal/Score Dynamics v2

## Status and authority

Live Expansion PR **#233** is the offline Goal/Score Dynamics v2 challenger protocol. Its authoritative base is `06c3df0b040e7314e6361cdd2d7732cf27a7e38c`. The infrastructure hotfix shifted the dated roadmap by one live PR number: #232 is the merged Richness/Coverage + Market-Label corpus, #233 is Goal/Score Dynamics v2, and forward-chaining calibration follows as #234.

This layer has **research model authority only**. It does not replace `engine/score_engine.py`, `engine/probability_engine.py`, `intelligence/match_analyst.py`, model-status promotion, pricing, routing, selection, accumulator logic, or BET authority. It does not fit calibration and never consumes bookmaker odds, prices, implied probabilities, offered lines, EV, Kelly, or SportyBet popularity information.

The current operational probability path is explicitly `BLOCKED_NOT_CANONICALLY_REPLAYABLE` as a historical comparator because Historical As-Of v1 does not canonically reconstruct all historical Elo, live-freshness, defaults, and fatigue inputs. No fake champion metric is manufactured.

## One football distribution

The research question is the regulation-time joint distribution `P(HomeGoals=h, AwayGoals=a | strictly pre-match evidence)`. Each challenger emits positive Home/Away goal intensities and one adaptive normalized score surface. 1X2, total goals, goal margin, BTTS, Over 2.5 and related diagnostics are projections of that same football state rather than separately trained market probabilities.

Win Either Half remains a Half Dynamics problem. 1UP/2UP remains a Lead Path problem. Neither specialist family is inferred from the full-time matrix.

The existing adaptive Poisson-tail machinery is reused rather than a hard 0..5 grid. Policy: `ADAPTIVE_POISSON_RECTANGLE_TAIL_1E10_V1`. Every surface retains the retained mass, omitted-tail bound, and normalization method.

## Exact source lineage and firewall

The canonical training view is generated from exact supplied files:

- `athena_history_asof_features.db` — strictly pre-match Historical As-Of evidence;
- `athena_tactical_identity.db` — strictly pre-match Tactical Identity evidence;
- `athena_training_coverage_labels.db` — #232 post-match label truth.

All are opened query-only/read-only, internally SHA-256 hashed, frozen-contract validated, protected against active SQLite companions, and cross-bound. Warehouse SHA must agree across all three. Tactical must name the exact supplied As-Of corpus SHA. #232 must name the exact supplied As-Of and Tactical corpus SHAs. Canonical row JSON and row SHA are replayed before a training row is emitted.

The #232 corpus contributes only `HOME_GOALS` and `AWAY_GOALS` when both are `AVAILABLE`. Target FT/HT/events/xG/shots, final lineup, target coach, referee, warehouse `data_quality`, post-match richness, path completeness, and label/capability availability are not model features.

## Feature registry

Goal/Score feature registry version **1** contains **120** explicit pre-match features and is pinned to:

`8052e9177e5c9d88226d36b5e7b11308ba0871889439638eb9f3570d37972bb0`

It contains no raw team/manager identity. Historical evidence preserves Home/Away and OVERALL vs target-venue scope, including form/results, scoring environment, clean-sheet/blank/BTTS/total tendencies, xG, shots/SOT, possession proxy, first-half environment, and competition-scoped schedule context. Tactical Identity contributes continuous EVENT_ENVIRONMENT, ATTACKING_PRODUCTION, DEFENSIVE_SUPPRESSION, SHOT_PROFILE, FIRST_HALF_ENVIRONMENT, CONTROL_TEMPO and SCORING_RELIABILITY signals for overall and target-venue profiles.

Competition-scoped schedule features are never described as complete all-competition workload.

## Missingness and competition prior

Upstream `AVAILABLE`, `MISSING`, and `BLOCKED` stay distinct. Numeric estimators use `TRAIN_FOLD_MEDIAN_PLUS_MISSING_BLOCKED_INDICATORS_V1`: each source feature becomes a numeric column plus separate MISSING and BLOCKED indicators. Medians are fit on TRAIN rows only. An all-missing feature uses zero only as a model-space anchor accompanied by a status indicator; no source fact is recovered or rewritten.

`TRAIN_FOLD_HIERARCHICAL_COMPETITION_GOAL_PRIOR_K20_V1` computes global and competition HomeGoals/AwayGoals rates from TRAIN outcomes only. For competition sample `n`, `weight=n/(n+20)` and `shrunk_rate=weight*competition_rate+(1-weight)*global_rate`. Unknown competitions use the train-global prior. Validation/holdout outcomes cannot change preprocessing or priors.

## Challenger registry

Model registry version **1** is pinned to:

`11d0d68078f9deeb0d9386aaa07581bf842feea4d33c310b3c86664fb8999768`

Candidates:

1. `POISSON_GLM_SCORE_V1`: separate `PoissonRegressor` Home/Away models (`alpha=0.25`, `max_iter=500`, `tol=1e-8`).
2. `DIXON_COLES_SCORE_V1`: same feature-conditioned Poisson intensities plus standard four-cell 0-0/0-1/1-0/1-1 Dixon-Coles correction. `rho` is fit on TRAIN rows only inside a mathematically safe interval keeping all corrected low-score cells positive; the retained surface is normalized after correction.
3. `HIST_GRADIENT_BOOSTING_POISSON_V1`: separate deterministic `HistGradientBoostingRegressor(loss="poisson")` models with fixed reviewed hyperparameters and seed 233.

No model contains a hand-written `LOW_EVENT => lambda -= x` rule. Tactical effects must be learned from training evidence; raw club names are absent from the model vector.

## Frozen evaluation and training-view contracts

Evaluation contract v1:

`dd14b3aedf90619cee53de5a6b01c24674401eaca9b24b86fa9cf3d871f7a690`

Training-view generation contract v1:

`dc7d58e1fec2f7a27f6bb8cb8dd2849ebb6b65f0d2185c76c4ac10b5d1c4455d`

These bind registry identities, missingness, train-only competition prior, date-bucket split, rolling-origin policy, terminal holdout, target firewall, adaptive tail, Dixon-Coles semantics, metrics, paired comparison, random seed, no-bookmaker input, and no-production-promotion semantics. Same-version drift fails closed.

## Chronology and evaluation

There is no random split. Rows are grouped by complete `match_date` buckets. The latest **20% of unique dates** (ceiling, at least one) form the terminal holdout; same-date rows cannot straddle development and holdout.

Development uses `DATE_BUCKET_EXPANDING_5_FOLD_V1`: the earlier half of development dates seeds the initial training window and the remainder is deterministically divided into five ordered validation blocks. Each fold satisfies `max(train_date) < min(validation_date)`. Preprocessing, competition priors, estimators, and Dixon-Coles `rho` are train-fold only.

Primary metric is mean exact-score negative log likelihood using the positive infinite-support Poisson/Dixon-Coles probability of the observed regulation score. Secondary diagnostics include Home/Away and combined Poisson deviance, 1X2 multiclass log loss/Brier, total-goal and goal-margin log loss, BTTS Brier/log loss, Over-2.5 Brier/log loss, predicted-vs-observed Home/Away goal means, and prediction availability. No calibration is fit here.

Pairwise comparisons use the same target set and a deterministic paired date-bucket bootstrap. Challenger disagreement retains Home/Away/total intensity ranges and mean pairwise total-variation distance.

## Tactical ablation and full-corpus honesty

The best development candidate is re-evaluated on identical rolling folds with Historical As-Of core only versus Historical As-Of + Tactical Identity. The delta is reported; Tactical improvement is not assumed. Synthetic tests verify evidence-dependent low/high scoring behavior without team identity.

The generated Phase 2/3/#232 database artifacts are not committed to Git. Therefore this PR does not invent real football performance. Until the exact artifacts are supplied to the offline runner:

`FULL_CORPUS_EVALUATION = NOT_RUN_SOURCE_CORPORA_UNAVAILABLE`

Synthetic CI metrics are never represented as full-corpus model performance. A `RESEARCH_CHALLENGER_WINNER` remains research-only and cannot grant production probability, calibration, pricing, routing, selection, accumulator, production approval, or BET authority.
