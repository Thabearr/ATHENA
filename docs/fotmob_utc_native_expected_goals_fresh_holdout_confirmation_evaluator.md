# FotMob UTC-native xG fresh-holdout confirmation evaluator

## Boundary

This boundary implements the **pure offline result evaluator** for the prospective
FotMob UTC-native expected-goals holdout. It does not execute the live experiment
and it does not inspect the current fresh journals by itself.

The evaluator is deliberately separate from the PR #151 activation runner. Live
collection remains frozen and outcome-independent. This implementation only
encodes the confirmation mathematics and terminal-accounting rules that were
already pre-registered by PR #148.

It performs no provider request, no model refit, no calibration refit, no feature
definition change, no competition-registry mutation, no bookmaker work, and no
production/BET authorization.

## Reviewed ancestry

The evaluator fails closed against the exact reviewed implementation chain:

- PR #148 calibration/competition protocol blob
  `9f45e17603a2678741ccc596d2542a0c6e29fa6c`;
- PR #148 canonical protocol SHA-256
  `d67407a315b583ddeb60514a136860fb72f1476ea3035deae8ff993e30daf171`;
- PR #149 fresh-holdout core blob
  `5dabab12d5205d384fd3904cda0e68661ef90791`;
- PR #150 collection-control blob
  `60865e35a92e28bb0d4360223dea42b8933bb706`;
- PR #151 activation-runner blob
  `901ab137d6601a3485eac30da7e6bad7eeefa397`;
- frozen holdout start `2026-08-19T00:00:00Z`.

If any of those reviewed dependencies moves, the evaluator refuses to run until a
new explicit review boundary is created.

## Inputs

The calculation seam accepts only already-constructed reviewed domain objects:

1. exact `FreshPredictionAssessment` values from the PR #149 core, including both
   sealed complete cases and explicit `MISSING_REVIEWED_FEATURES` assessments;
2. exact terminal records for every sealed prediction;
3. the selected UTC close boundary;
4. an evaluation timestamp.

This is intentionally not the source-execution boundary. A later executor must
reconstruct those values from the durable PR #151 journals and source evidence
before calling this evaluator.

## Missingness

The pre-registration requires missingness to remain visible by provider
`primaryId`. Therefore the evaluator consumes the complete reviewed prediction
assessment population, not only the sealed complete cases.

For each provider `primaryId` it reports:

- total reviewed prediction assessments before the selected close;
- sealed complete-case count;
- explicit missing-feature prediction count;
- counts for each missing feature ID;
- reviewed ordinary-FT scored count;
- settlement exclusions/unresolved count and terminal disposition counts.

Missing-feature assessments never enter the count-only complete-case denominator
and are never imputed or retrofilled.

## Count-only close is revalidated before outcomes

The caller does not get to assert that a date is a valid close.

The evaluator first extracts only exact sealed complete cases and calls the
already-reviewed PR #149 `evaluate_holdout_boundary(...)`. The supplied boundary
must resolve to exactly one of the two terminal states:

- `CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED`; or
- `FRESH_HOLDOUT_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION`.

An earlier `OPEN_*` boundary is rejected.

The frozen count-only gates therefore remain:

- at least 1,000 complete-case sealed fixtures;
- at least 8 provider-`primaryId` clusters with at least 30 complete cases each;
- at least 2 qualifying clusters outside the legacy 11 IDs.

Goals, NLL, calibration error, settlement success, or any later performance value
cannot choose the close.

## Settlement-tail and terminal accounting

Confirmation cannot run before `selected_close_utc + 24 hours`.

Every sealed prediction must have exactly one terminal record. The terminal
vocabulary is the exact final PR #151 state:

- `SETTLED_REVIEWED_ORDINARY_FT`;
- `EXCLUDED_PROVIDER_IDENTITY_OR_KICKOFF_DRIFT`;
- `EXCLUDED_OUTSIDE_SELECTED_CLOSE`;
- `UNRESOLVED_AT_SETTLEMENT_TAIL`.

A settled terminal must bind the **exact canonical sealed prediction** supplied to
the evaluator, not merely the same fixture ID.

A sealed fixture with kickoff at or after the selected close must carry
`EXCLUDED_OUTSIDE_SELECTED_CLOSE`. A fixture inside the selected population may
not carry that disposition.

Settlement availability never changes the selected complete-case population.
Missing or excluded settlements are reported explicitly.

## Frozen calibration metrics

Calibration uses the seven pre-registered bins:

- `[0.0, 0.5)`;
- `[0.5, 1.0)`;
- `[1.0, 1.5)`;
- `[1.5, 2.0)`;
- `[2.0, 2.5)`;
- `[2.5, 3.0)`;
- `[3.0, +inf)`.

Each model assigns a fixture to a bin using **its own** predicted rate.

For a side, weighted absolute calibration error is

`WACE = sum(n_bin * abs(mean_predicted_bin - mean_observed_bin)) / N`.

Weighted squared calibration error is

`WSCE = sum(n_bin * (mean_predicted_bin - mean_observed_bin)^2) / N`.

For observed goals `y` and rate `lambda`, Poisson negative log likelihood is

`lambda - y * ln(lambda) + lgamma(y + 1)`.

Joint fixture NLL is exact home NLL plus away NLL.

No coefficient or calibration parameter is fitted in this evaluator.

## Frozen pooled gates

On reviewed scored settlements the evaluator applies exactly the PR #148 gates:

1. calibrated home WACE < uncalibrated native home WACE;
2. calibrated home WACE < Elo-only home WACE;
3. calibrated home WSCE < uncalibrated native home WSCE;
4. calibrated home WSCE < Elo-only home WSCE;
5. calibrated joint Poisson NLL < Elo-only joint NLL;
6. calibrated joint NLL <= uncalibrated native joint NLL;
7. unchanged native away WACE < Elo-only away WACE;
8. unchanged native away WSCE < Elo-only away WSCE.

Away calibration remains exact native-away identity.

## Competition robustness

Competition identity is exact provider `primaryId`.

The qualifying cluster set comes from the **count-only sealed population**, so
settlement outcomes cannot change which competition clusters qualified at close.

For scored fixtures in those qualifying clusters:

`paired_delta = calibrated joint NLL - Elo-only joint NLL`.

The evaluator preserves the frozen jackknife:

1. full estimate = fixture-weighted mean paired delta on the qualifying-cluster
   union;
2. delete cluster `i` and take the fixture-weighted mean of all remaining paired
   fixture deltas;
3. `theta_bar` = arithmetic mean of delete estimates;
4. `SE = sqrt(((K-1)/K) * sum((theta_delete_i - theta_bar)^2))`;
5. 95% interval = `full_estimate +/- 1.96 * SE`.

The upper bound must be strictly below zero. At least 75% of qualifying clusters
must also have a negative within-cluster mean paired delta.

If a cluster qualified by sealed count but has no reviewed scored settlement, the
robustness gate fails closed and the missing settlement coverage remains visible.

Small competitions below 30 complete cases are still reported but remain
report-only.

## Result states

The result vocabulary is unchanged:

- all pooled and robustness gates pass:
  `FRESH_HOLDOUT_CALIBRATION_AND_COMPETITION_ROBUSTNESS_SIGNAL_REVIEW_REQUIRED`;
- hard close occurs without count coverage:
  `FRESH_HOLDOUT_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION`;
- a pooled or robustness gate fails:
  `FRESH_HOLDOUT_CALIBRATION_OR_ROBUSTNESS_GATE_FAILED_REVIEW_REQUIRED`.

Even the all-pass state remains **review required**.

There is no automatic successor approval.

## Safety

This implementation grants no:

- fresh-label model training or refitting;
- production expected-goals authority;
- ScoreMatrix authority;
- probability inference or adjustment authority;
- calibration-for-production authority;
- pricing or market activation;
- selection, ACCA/slip, booking-code, SportyBet execution, or BET authority.

The implementation receipt itself is result-free and reads no fresh labels.

## Next boundary

`SOURCE_REPLAY_AND_REVIEW_FRESH_HOLDOUT_CONFIRMATION_RESULT`

That later boundary should restore and source-revalidate the durable PR #151
evidence, reconstruct the exact prediction assessments and terminal records,
invoke this evaluator only after the selected settlement tail is complete, store a
canonical result receipt, and still require an explicit review before any
successor model authority can move.
