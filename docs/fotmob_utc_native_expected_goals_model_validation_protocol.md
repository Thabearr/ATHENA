# FotMob UTC-native expected-goals model validation protocol

## Status

`PRE_REGISTERED_NOT_EXECUTED`

This document defines the next reviewed model-validation boundary after the successful FotMob UTC-native successor feature qualification. It does **not** execute training, select a winning model, authorize the score matrix, activate any market, or grant pricing/selection/production/BET authority.

## Exact upstream evidence

The protocol is anchored to the successful reconciled V2 feature-qualification execution:

- main SHA: `cd67be14f6a4f09484d18a57de360b8a5d4c51d7`
- run ID: `31990121181`
- result comment ID: `5311318782`
- artifact ID: `9275052993`
- artifact name: `fotmob-utc-native-feature-qualification-v2-31990121181`
- artifact SHA-256: `f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb`
- artifact size: `23,349,191` bytes
- qualified projection SHA-256: `5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed`
- expected canonical rows: `21,326`
- expected unique fixtures: `21,326`

The V2 receipt is feature evidence only. It grants no model, pricing, selection, production, or BET authority.

## Why a new xG model boundary is necessary

ATHENA currently contains several different historical/legacy model paths that must not be conflated:

1. `engine/score_engine.py` is a legacy heuristic that converts a team-strength difference into home/away xG using fixed base goals, fixed coefficients, clamps and rounding.
2. `engine/analyzer.py` can fabricate default team statistics when its statistics source is empty before invoking that heuristic.
3. `models/goals_model.joblib` is a legacy Random Forest regressor for **total goals**, not separate home/away expected-goals rates.
4. `tools/train_model.py` trains that Random Forest from a different feature family: pre-match Elo plus rolling xG, possession, goals-for and goals-against.
5. `scripts/backfill_xg.py` historically populates xG/possession by fuzzy team-name matching against post-match FotMob advanced statistics. Those values are not accepted as exact pre-kickoff evidence for this boundary.
6. `models/expected_goals.py`, `models/poisson.py`, and `models/dixon_coles.py` are placeholders, not authoritative implementations.

None of those paths is promoted by this protocol.

## Reviewed feature contract

The numeric model features are exactly:

- `home_form`
- `away_form`
- `home_elo`
- `away_elo`
- `fatigue`

`live_data_freshness` remains a **runtime trust gate**, not a historical numeric predictor. The qualified historical projection correctly reports historical freshness as blocked/unreconstructible. The model-validation implementation must not invent a numeric surrogate, default it, or treat source labels as proof of freshness.

At runtime, a future model must still fail closed if the reviewed freshness gate is not available/acceptable.

## Targets

The validation target is a pair of separate non-negative expected-goals rates:

- home goals
- away goals

A model that only predicts total goals cannot be relabeled as a home/away xG model.

## Pre-registered model families

The execution implementation may compare exactly these candidate families:

1. L2-regularized Poisson regression, trained separately for home and away goals.
2. Histogram gradient boosting with Poisson loss, trained separately for home and away goals.

No candidate is selected by this protocol. Hyperparameter search on the final holdout is forbidden.

## Baselines

Every candidate must be compared against:

1. a global home/away mean-goals baseline; and
2. a strictly-prior rolling competition mean-goals baseline.

The rolling baseline must obey the same UTC chronology and same-kickoff grouping rules as the candidate model.

## Temporal split

The split is season-ordered:

- development: `2020-21`, `2021-22`, `2022-23`, `2023-24`
- validation: `2024-25`
- final temporal holdout: `2025-26`

The final holdout is historical, **not prospective**, and must never be described as prospective evidence.

Exact same-UTC-kickoff groups must stay in the same partition. Historical state must obey `history_kickoff_utc < target_kickoff_utc`.

## Metrics

Primary metrics are recorded separately for home and away targets:

- Poisson negative log-likelihood
- MAE
- RMSE
- mean prediction bias

Results must also be broken down by competition family, season, and observed home/away goal bands. Aggregate success may not hide severe subgroup failure.

## Fail-closed rules

The future execution must reject or block rather than guess when any of these invariants cannot be proven:

- no random/shuffled split;
- no same-kickoff leakage;
- no post-match xG or possession promoted to pre-match features;
- no fuzzy team identity;
- no numeric freshness surrogate;
- no missing-feature defaults;
- no total-goals model relabeled as separate home/away xG;
- no final-holdout model-family selection;
- no score-matrix or market approval inside this boundary.

## Outcome semantics

A successful validation may produce only:

`QUALIFIED_EXPECTED_GOALS_MODEL_CANDIDATE_MODEL_USE_UNREVIEWED`

That means the candidate has survived the pre-registered historical xG validation. It still does **not** authorize production model use.

Failure produces:

`EXPECTED_GOALS_MODEL_VALIDATION_NOT_QUALIFIED`

No threshold may be weakened after seeing results merely to force a pass.

## Downstream authority

The protocol keeps all of the following false:

- expected-goals model production approval
- score-matrix authorization
- probability inference authorization
- calibration production authorization
- pricing authorization
- market activation authorization
- selection authorization
- production approval
- BET authorization

If and only if this model-validation boundary succeeds, the next reviewed boundary is:

`PRE_REGISTER_REVIEWED_SCORE_MATRIX_AND_CORE_MARKET_PROBABILITY_VALIDATION_PROTOCOL`
