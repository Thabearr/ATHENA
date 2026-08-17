# FotMob UTC-native expected-goals model validation protocol

## Boundary

PR #140 pre-registers the next ATHENA model-validation experiment. It is
**result-free**: merging it does not fit a model, calculate a ScoreMatrix,
produce market probabilities, inspect bookmaker prices, select bets, or
authorize production.

The protocol is bound to the successful V2 UTC-native feature qualification:

- run `31990121181`
- command comment `5311311034`
- attempt marker `5311311868`
- result comment `5311318782`
- evidence artifact `9275052993`
- artifact size `23,349,191` bytes
- artifact SHA-256 `f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb`
- qualified projection size `23,342,076` bytes
- projection SHA-256 `5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed`
- 21,326 rows / 21,326 unique fixtures / zero identity-lineage conflicts
- 21,129 five-feature complete cases

Historical `live_data_freshness` remains
`NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE`; it is blocked/null and is not a
numeric model input.

## Why the reviewed successor family is reused

ATHENA already pre-registered, fit, and robustness-tested a two-response
home/away Poisson log-link GLM. The predictor mathematics match the newly
qualified FotMob projection: centered/scaled overall Elo, centered form, and
raw fatigue.

The historical study was retrospective and used source-local chronology. The
new projection is different evidence: canonical timezone-aware UTC, strict
prior history, and same-kickoff batching. PR #140 therefore tests the same
reviewed model family on the new chronology instead of silently changing model
families or promoting historical coefficients.

“Reuse the exact historical deterministic fitter” is a transitive contract
against the pinned historical protocol. The later implementation must retain
`math.fsum` reductions, response fit order, log-of-training-response-mean
intercept initialization, zero non-intercept initialization, Newton equations,
deterministic partial-pivot solving, backtracking, convergence rules, the
200-iteration ceiling, `1e-8` gradient tolerance, `0.5` backtracking factor,
`2^-20` minimum step, `20.0` absolute eta guard, `1e-12` pivot tolerance,
12-place coefficient rounding, no regularization/search, and no
post-evaluation refit. The only chronology adaptation is source-local kickoff
to the already-qualified canonical UTC kickoff.

The legacy `models/goals_model.joblib` remains quarantined. It is a Random
Forest for **total match goals** from a different feature family, not a
home/away expected-goals transform. The one-byte `models/expected_goals.py`,
`models/poisson.py`, and `models/dixon_coles.py` placeholders are not treated as
implementations.

## Frozen input population

Five numeric predictors are required:

- `(home_elo - 1500) / 400`
- `(away_elo - 1500) / 400`
- `home_form - 0.5`
- `away_form - 0.5`
- raw `fatigue`

Missing form or fatigue stays missing. Exactly 197 of 21,326 rows are excluded,
leaving **21,129 complete cases**.

The complete-case fixture population is determined **once before any model arm
is reduced**. Elo-only and no-fatigue arms may not admit extra rows just
because they need fewer columns. Historical transfer and the constant baseline
must also evaluate the exact same fixture identities.

The frozen membership representation is:

`kickoff_utc<TAB>fixture_identifier<NEWLINE>`

sorted by `(kickoff_utc, fixture_identifier)`.

| Population | Rows | Membership SHA-256 |
|---|---:|---|
| All complete | 21,129 | `1374fd323bd5aa7e6da6cee23358621c26435297c2e195553e227373008fd8ed` |
| Train | 14,181 | `4c017b9e43ab9e2f231e88187339a3960c5fdfbd087f21ba92ca8855576219a9` |
| Evaluation A | 3,471 | `4361cd60976170bd14442502025160d9b3aa97717fb94afc1b68eee9b88c429f` |
| Evaluation B | 3,477 | `4910b5db577bd87fd4bed4e24f3b1e00dff85d58f23e7ea8558cfba0aa5efd59` |
| Pooled A+B | 6,948 | `f4d713a739feeac90c166f5125dd80ab7e3063598f9ad0187f07d10b88e5bcdc` |

Any arm membership mismatch makes the later validation fail closed.

## Frozen model arms

Exactly five arms are allowed:

1. `FOTMOB_NATIVE_SAME_FAMILY_REFIT` — exact common training population,
   full five predictors, reviewed deterministic fitter.
2. `HISTORICAL_FIXED_COEFFICIENT_TRANSFER` — exact historical home/away
   coefficients, no refit, exact common evaluation population.
3. `FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM` — exact common training population,
   Elo-only nested comparator; **eligibility is not rerun**.
4. `FOTMOB_NATIVE_NO_FATIGUE_ABLATION` — exact common training population,
   form+Elo; **eligibility is not rerun**.
5. `TRAIN_ONLY_GLOBAL_HOME_AWAY_MEAN_BASELINE` — means calculated from the
   exact same 14,181 training rows and evaluated on the exact common A/B rows.

No sklearn PoissonRegressor substitution, regularization/alpha search, random
split, K-fold search, predictor re-standardization, or post-evaluation refit is
authorized.

## Chronological populations

Same-kickoff fixtures must stay in the same partition.

| Population | UTC interval | Complete rows |
|---|---|---:|
| Train | 2020-08-01 inclusive to 2024-07-01 exclusive | 14,181 |
| Evaluation A | 2024-07-01 inclusive to 2025-07-01 exclusive | 3,471 |
| Evaluation B | 2025-07-01 inclusive to 2026-08-15 exclusive | 3,477 |

Evaluation B is a **chronologically later retrospective evaluation, not a
prospective holdout**. Its outcomes existed before this protocol.

## Evaluation and calibration

Primary metric: mean joint Poisson negative log-likelihood.

For Evaluation A, Evaluation B, and pooled A+B, report home/away NLL, bias,
MAE, RMSE, WACE, WSCE, and the required paired NLL deltas. Every model is
evaluated on the same fixture population.

Calibration bins are frozen as
`[0,.5), [.5,1), [1,1.5), [1.5,2), [2,2.5), [2.5,3), [3,∞)`.
Each model assigns rows using **its own predicted rate**. Every bin reports
count, mean predicted goals, mean observed goals, and
`predicted - observed` calibration error.

For population size `N`:

- `WACE = Σ count_b * |error_b| / N`
- `WSCE = Σ count_b * error_b² / N`

An empty bin is represented with `count=0` and null means/error. It contributes
zero *weight*; ATHENA must not fabricate a zero calibration error observation.
Bin counts must reconcile exactly to the evaluation population.

The strong-signal calibration gate uses the **pooled A+B** population. A and B
tables are still mandatory diagnostics.

## UTC-quarter paired jackknife

Temporal robustness operates on the exact 6,948 pooled evaluation fixtures.
For each fixture:

`d_i = native-refit joint NLL - Elo-only joint NLL`

The full estimate is the arithmetic mean of all 6,948 `d_i`.

Exact non-empty UTC calendar-quarter clusters are:

| Quarter | Rows |
|---|---:|
| 2024-Q3 | 626 |
| 2024-Q4 | 1,017 |
| 2025-Q1 | 1,073 |
| 2025-Q2 | 755 |
| 2025-Q3 | 599 |
| 2025-Q4 | 1,020 |
| 2026-Q1 | 1,097 |
| 2026-Q2 | 721 |
| 2026-Q3 | 40 |

`2026-Q3` is intentionally partial because the frozen evaluation ends before
2026-08-15.

For each of the nine clusters, delete that cluster and compute the
fixture-weighted arithmetic mean on all remaining paired differences. Then:

- `theta_bar` is the **unweighted arithmetic mean of the nine delete estimates**
- `SE = sqrt(((K-1)/K) * Σ(theta_delete_j - theta_bar)^2)`, `K=9`
- interval = **full theta ± 1.96 × SE**
- the strong-signal temporal gate requires the exact upper endpoint to be
  strictly below zero

Do not weight `theta_bar` by the differing remaining-fixture counts. Every
pooled evaluation row must map to exactly one frozen non-empty quarter;
missing, unexpected, duplicated, or empty cluster membership fails closed.

## Interpretation

`STRONG_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED` requires:

- exact lineage, split, missingness, and common-population checks;
- convergence of native home and away fits;
- native-refit NLL below Elo-only in Evaluation A, Evaluation B, and pooled;
- quarter-jackknife upper 95% endpoint below zero;
- pooled home/away WACE and WSCE each lower than Elo-only.

Otherwise the result is
`MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED`.

Neither state automatically approves a model. Historical transfer and
no-fatigue comparisons remain report-only diagnostics.

The projection does not carry league/competition identity, therefore
league/competition robustness is exactly
`BLOCKED_PROJECTION_DOES_NOT_CARRY_COMPETITION_IDENTITY`. No identity may be
invented or fuzzily reconstructed in this boundary.

## Receipt and safety

A later implementation must hash-seal predictions and its validation receipt,
revalidate the V2 artifact/projection, recompute the common-population hashes,
report exact arm membership, A/B/pooled calibration tables, all nine quarter
counts/delete estimates, fitted coefficients and convergence diagnostics, and
all required metrics.

It must not write a production model artifact or calculate ScoreMatrix,
market probabilities, prices, selections, or bets.

All model-approval, expected-goals production, probability, ScoreMatrix,
production calibration, pricing, market activation, selection, production and
BET authority remains exact `false`.

Canonical protocol SHA-256: `7dbae5deb711a1d456fb1304616b2f0b6741ffd2039154806f953221a61e06f6`  
Canonical protocol size: `15157` bytes

After review and merge, the next separate boundary is:

`IMPLEMENT_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION`
