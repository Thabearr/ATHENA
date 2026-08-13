# Historical expected-goals successor candidate fitter

## Purpose

This boundary implements the deterministic fitting and retrospective evaluation
machinery frozen by PR #72. It does **not** change the protocol and it does not
execute the fitter against the reviewed 21,226-fixture real corpus during this
PR.

That separation is deliberate. The implementation must be reviewed and merged
before ATHENA observes the successor model's real learned coefficients or its
2024-25 / 2025-26 evaluation result.

## Two execution layers

The module exposes two distinct layers.

### Synthetic/adversarial fixture-set execution

`fit_historical_expected_goals_successor_fixture_set(...)`

This accepts the exact frozen PR72 protocol and exact
`HistoricalReplayFixture` values. It is the test seam used to verify the fitting
math, chronology, comparator parity, calibration, and fail-closed numerical
behavior without claiming that supplied fixtures are the reviewed PR69 corpus.

It must never be presented as source-validated historical evidence by itself.

### Evidence-bound candidate construction

`build_historical_expected_goals_successor_candidate(...)`

This is the real-evidence boundary. Before fitting it must:

1. revalidate the exact PR72 protocol from the canonical PR71 receipt bytes;
2. fully rebuild/revalidate PR69 from exact supplied source CSV bytes;
3. require the rebuilt PR69 canonical SHA and source-corpus SHA to match the
   frozen protocol;
4. rebuild PR70 from those same source bytes;
5. require the rebuilt PR70 validation SHA to match the frozen protocol;
6. only then execute the successor fitter.

The corresponding full revalidator rebuilds all ancestry, refits both models,
reevaluates them, and requires exact canonical candidate-byte parity.

## Frozen model family

No modelling choice is introduced here. PR72 already froze:

`INDEPENDENT_POISSON_LOG_LINK_TWO_RESPONSE_GLM_V1`

ATHENA fits one home-goals response and one away-goals response independently.
Each uses exactly the six PR72 predictors, in order:

1. intercept;
2. `(home_elo - 1500) / 400`;
3. `(away_elo - 1500) / 400`;
4. `home_form - 0.5`;
5. `away_form - 0.5`;
6. raw fatigue.

The implementation reads the transform definitions from the frozen protocol
object instead of reopening the constants.

Eligibility remains the exact conjunction:

- `form_path_component_eligible == True`; and
- `elo_fallback_component_eligible == True`.

Blocked or missing replay features are excluded; there is no defaulting or
imputation.

## Chronology

Training seasons are exactly:

- 2020-21
- 2021-22
- 2022-23
- 2023-24

Evaluation seasons are exactly:

- 2024-25
- 2025-26

Eligible rows are ordered by:

`source_local_kickoff ASC, fixture_identifier ASC`

Every frozen season must retain eligible fixtures. An eligible fixture without a
source-local kickoff fails closed because PR72 requires deterministic
chronological ordering.

Evaluation outcomes and evaluation feature values never enter fitting. Synthetic
regression tests mutate both and require the learned training coefficients to
remain unchanged.

The evaluation label remains:

`RETROSPECTIVE_CHRONOLOGICAL_EVALUATION_NOT_UNTOUCHED_HOLDOUT`

## Deterministic Newton implementation

The fitter implements PR72's exact engine:

`DETERMINISTIC_NEWTON_POISSON_GLM_WITH_BACKTRACKING_V1`

For a response model:

- initial intercept = `log(mean training response)`;
- all other coefficients initialize at zero;
- non-positive or non-finite response mean fails;
- `mu_i = exp(x_i beta)`;
- Newton direction solves
  `X^T diag(mu) X delta = X^T (y - mu)`;
- the linear system uses deterministic Gaussian elimination with partial
  pivoting;
- an exact pivot tie retains the lowest row index because only a strictly larger
  absolute pivot replaces the current pivot;
- pivot magnitude at or below `1e-12` fails;
- line search begins at step 1;
- candidate absolute linear predictor above 20 is rejected;
- otherwise a candidate is accepted only when candidate Poisson NLL is less than
  or equal to current NLL;
- rejected steps multiply by 0.5;
- falling below `2^-20` fails;
- convergence requires gradient infinity norm at or below `1e-8`;
- no more than 200 Newton updates are allowed;
- converged coefficients are rounded to exactly 12 decimal places;
- the rounded coefficients, not the hidden unrounded vector, are used for every
  evaluation rate.

Every scalar reduction used by objective, gradient, Hessian, fit summaries, and
evaluation summaries uses Python `math.fsum`.

No optimizer fallback exists.

## Evaluation

The successor candidate reports the PR72 primary metric:

`MEAN_JOINT_POISSON_NEGATIVE_LOG_LIKELIHOOD`

The Poisson NLL retains the `lgamma(y + 1)` factorial term through the reviewed
PR70 scoring primitive.

Each evaluation fixture is compared against all four frozen references:

1. `PR68_FORM_COMPONENT`
2. `PR68_ELO_FALLBACK_COMPONENT`
3. `PR68_FROZEN_CONSTANT_BASELINE`
4. `STRICT_PREMATCH_ROLLING_IDENTITY_LEAGUE_BASELINE`

FORM and ELO comparator rates are mechanically reproduced from the frozen PR68
specification. Tests require exact parity with the reviewed PR70 implementation.

The rolling league baseline reproduces PR70 chronology:

- exact identity leagues remain separate;
- only strictly prior evidence contributes;
- same-kickoff fixtures are evaluated from state before the whole batch, then
  updated together;
- a missing source time makes the whole same-league/source-date baseline
  unavailable;
- once that date completes, all outcomes on the date can enter state for later
  dates.

Tests require exact rolling-baseline parity with PR70.

## Reported evidence

The candidate structure contains:

- training/evaluation fixture counts;
- counts for every frozen train/evaluation season;
- rounded home and away coefficients;
- Newton update counts and convergence gradient norms;
- training NLL evaluated with rounded coefficients;
- aggregate goal-rate metrics;
- candidate-vs-comparator paired NLL deltas;
- evaluation-season breakdowns;
- exact identity-league breakdowns;
- home and away calibration in the exact PR70 bins.

No comparator result is an automatic approval decision. `BETTER`, `WORSE`, and
`EXACT_TIE` only encode the sign of a paired NLL difference.

## Historical replay caveats

The candidate retains PR72's exact semantic warnings:

- Elo 1500 is
  `1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE`;
- historical fatigue PR31 semantic equivalence remains `UNPROVEN`.

Learning a coefficient cannot upgrade either statement.

Historical live-data freshness remains unreconstructed.

## Safety boundary

This module does not import or execute:

- SQLite;
- network clients;
- pandas/numpy/scipy/sklearn/joblib;
- score-matrix code;
- market probability engines;
- bookmaker/SportyBet pricing;
- EV/selection/betting code.

The evidence-bound artifact records that research training occurred, but every
downstream authorization remains exact `false`:

- successor candidate approval;
- expected-goals transform approval;
- probability inference;
- score matrix;
- probability adjustment;
- production calibration;
- pricing;
- market activation;
- selection;
- production approval;
- betting.

Training a research candidate is not production approval.

## Deliberately absent from this PR

This PR must not contain:

- coefficients learned from the reviewed real corpus;
- real 2024-25 / 2025-26 successor evaluation metrics;
- tuning after observing those results;
- a persisted real-data successor artifact;
- any production model activation.

After this implementation passes adversarial review and merges unchanged, ATHENA
may perform a one-shot evidence-bound execution against the exact reviewed
football-data.co.uk corpus. A later receipt boundary can then record the learned
coefficients and evaluation result without changing this fitter or PR72's frozen
protocol.
