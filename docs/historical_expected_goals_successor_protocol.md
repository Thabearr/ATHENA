# Historical expected-goals successor protocol

## Purpose

This boundary freezes the first data-backed successor-model protocol **before any
successor coefficients are learned**.

PR #71 established that the frozen PR68 FORM and ELO components both contain
broad retrospective predictive signal on the reviewed football-data.co.uk
corpus, with ELO descriptively stronger, while also exposing material
calibration error in the old direct ELO-to-goal-rate mapping.

The correct next step is therefore not to approve the legacy mapping and not to
tune it after seeing its weaknesses. Instead, ATHENA freezes a small,
interpretable Poisson regression protocol that can learn how the existing
reviewed replay features relate to home and away scoring rates.

This module is a **protocol only**. It contains no learned coefficients and
performs no fitting, probability inference, pricing, selection, or betting.

## Evidence ancestry

The builder accepts only the exact canonical PR71 real-corpus execution receipt
bytes.

Required receipt SHA-256:

`9680b108ac308df5f9d58f18ddacbb8ce1cda8e8806232519d4d327aea2d6da0`

The receipt must continue to bind:

- 66 reviewed football-data.co.uk CSV files;
- 10,006,877 exact source bytes;
- 21,226 parsed fixtures;
- PR69 source-corpus SHA-256
  `c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0`;
- PR69 canonical replay SHA-256
  `b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3`;
- PR70 validation SHA-256
  `c13287a28ac1ffc1bfc02b1ea283c34840a7a00eb14ec13cac39ca67c14ab5e5`;
- frozen PR68 transform identity and specification;
- unreconstructed historical freshness;
- successful PR69 and PR70 revalidation;
- all recorded downstream authorizations false.

A one-byte receipt mutation fails before the protocol is built.

## Model family

Protocol identity:

`HISTORICAL_EXPECTED_GOALS_SUCCESSOR_PROTOCOL_V1`

Model family:

`INDEPENDENT_POISSON_LOG_LINK_TWO_RESPONSE_GLM_V1`

ATHENA will fit two independent count models:

- one for full-time home goals;
- one for full-time away goals.

Each model uses a Poisson response with a log link:

`lambda = exp(beta_0 + beta_1*x_1 + ... + beta_5*x_5)`

The home and away models are fit separately. Coefficients are **not shared**.

This does not assert that football scores are truly independent Poisson random
variables. It is a deliberately simple, interpretable first successor candidate
that can be compared directly with the old PR68 Poisson-rate heuristic.

## Frozen predictors

Exactly six predictors, in exact order:

1. `intercept`
2. `home_elo_centered_scaled`
3. `away_elo_centered_scaled`
4. `home_form_centered`
5. `away_form_centered`
6. `fatigue_raw`

Transforms are frozen before fitting:

### Intercept

`1`

### Home Elo

`(home_elo - 1500) / 400`

### Away Elo

`(away_elo - 1500) / 400`

### Home form

`home_form - 0.5`

### Away form

`away_form - 0.5`

### Fatigue

`fatigue`

### Replay-semantic caveats

The numerical transforms above do not upgrade the status of their historical
inputs.

PR69 reconstructs Elo deterministically from source results, and a source-scoped
team begins its replay at 1500. That 1500 value is an **initial-state replay
assumption, not observed football evidence**. The successor protocol therefore
carries the exact semantic marker:

`1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE`

PR69 also records the historical fatigue scalar with:

`fatigue_pr31_semantic_equivalence = UNPROVEN`

That warning is a first-class field of this protocol and must survive into any
later trained candidate. Fitting a coefficient to the replayed scalar does not
prove it is semantically equivalent to the generic PR31 fatigue feature.

There are deliberately no:

- bookmaker odds;
- target-score-derived features;
- xG fields that are absent from the reviewed historical evidence;
- possession fields;
- current mutable team records;
- fuzzy identities;
- hidden defaults;
- league cherry-picking;
- interaction terms;
- polynomial terms;
- automatic feature selection.

The model is small on purpose. If this candidate fails, ATHENA should learn from
that failure rather than silently expand the specification after seeing the
result.

## Eligibility

A historical fixture is eligible only when PR69 reports both:

- `form_path_component_eligible == True`; and
- `elo_fallback_component_eligible == True`.

Therefore all five non-intercept inputs are supported by the reviewed replay for
that fixture.

No missing value is defaulted, imputed, or substituted.

PR69 fatigue retains its existing warning that exact semantic equivalence to the
generic PR31 fatigue concept is unproven. This protocol does not erase that
warning.

## Frozen chronology

Training seasons:

- `2020-21`
- `2021-22`
- `2022-23`
- `2023-24`

Evaluation seasons:

- `2024-25`
- `2025-26`

The sets are disjoint.

The evaluation is labeled:

`RETROSPECTIVE_CHRONOLOGICAL_EVALUATION_NOT_UNTOUCHED_HOLDOUT`

This wording is important. ATHENA has already inspected aggregate historical
results across the complete corpus while validating PR68. The later seasons are
still out of the successor model's fitting sample, but they are **not honestly
claimable as never-before-seen research data**.

Consequently, even an excellent retrospective result cannot by itself authorize
production use.

Production approval will require future evidence that did not exist when this
protocol was frozen.

## Frozen fitting algorithm

The subsequent training boundary must implement exactly:

`DETERMINISTIC_NEWTON_POISSON_GLM_WITH_BACKTRACKING_V1`

Objective:

sum of independent Poisson negative log-likelihoods over the training sample.

No regularization is used in this first protocol.

Initialization for each response:

- intercept = log(mean training response);
- every non-intercept coefficient = 0.

Fit order:

1. home-goals model;
2. away-goals model.

Frozen numerical controls:

- maximum iterations: `200`;
- gradient infinity-norm convergence tolerance: `1e-8`;
- backtracking factor: `0.5`;
- minimum accepted step size: `2^-20`;
- candidate steps with absolute linear predictor above `20` are rejected rather
  than silently clipped into the model;
- deterministic linear-solve pivot tolerance: `1e-12`;
- final fitted coefficients are rounded to exactly 12 decimal places before the
  candidate artifact is evaluated and canonicalized.

There is no hyperparameter search.

There is no post-evaluation refit in the same research boundary.

If the frozen solver cannot converge under these rules, the training attempt
fails closed. The implementation must not silently switch optimizers.

## Evaluation contract

Primary metric:

`MEAN_JOINT_POISSON_NEGATIVE_LOG_LIKELIHOOD`

For each evaluation fixture, home and away Poisson NLL are summed exactly as in
the reviewed PR70 scoring rule.

The successor candidate must be compared against all four frozen references:

1. PR68 FORM component;
2. PR68 ELO fallback component;
3. PR68 frozen constant baseline;
4. strict pre-match rolling identity-league baseline.

The later implementation must report:

- aggregate evaluation metrics;
- each evaluation season separately;
- each exact identity league separately;
- home and away calibration using the exact PR70 bins;
- mean predicted and actual home/away goals;
- home/away bias;
- home/away MAE;
- home/away RMSE;
- joint Poisson NLL and paired deltas versus every comparator where applicable.

Calibration bins remain:

- `[0.0, 0.5)`
- `[0.5, 1.0)`
- `[1.0, 1.5)`
- `[1.5, 2.0)`
- `[2.0, 2.5)`
- `[2.5, 3.0)`
- `[3.0, +infinity)`

The open upper bound is represented canonically as `null`, never JSON Infinity.

## No approval threshold

This protocol intentionally does **not** encode a rule such as:

> beat legacy ELO by X percent and become approved.

That would create a false sense of model certainty and would encourage tuning to
a threshold on already-observed research evidence.

The training/evaluation boundary will report the evidence. A later explicit
human-reviewed boundary can decide whether the candidate deserves further work.

## Safety

All protocol safety values are exact false, including:

- successor protocol approved;
- successor model trained;
- expected-goals transform approved;
- probability inference authorized;
- score matrix authorized;
- production calibration authorized;
- pricing authorized;
- market activation authorized;
- selection authorized;
- production approval authorized;
- betting authorized.

Freezing a research protocol is not model approval.

## Next boundary

Only after this protocol passes review and merges may a later PR implement the
frozen deterministic fitter and execute it against the exact PR69 evidence.

That later PR must not modify this protocol after seeing learned coefficients or
evaluation results. Any desired protocol change must be proposed explicitly as
a new version and must not be represented as if it had been pre-registered.
