# FotMob UTC-native expected-goals model validation implementation

## Boundary

This implementation is the executable research validator for merged PR #140.
It **does not execute the preserved 21,326-row validation during this pull
request**. Review and execution remain separate trust boundaries.

The implementation may, in a later controlled execution, consume the exact
qualified V2 UTC-native feature projection and produce hash-sealed research
predictions plus a canonical validation receipt. It does not call ScoreMatrix,
derive market probabilities, inspect bookmaker prices, choose selections, or
authorize production/BET use.

## Exact reviewed parent

The implementation is bound to merged PR #140:

- merged `main`: `df4a24454ae479dc68f27d19ee3f9101fd1d3b7c`
- PR #140 protocol implementation blob:
  `1780330c4d0ab9140f0b2f6c776dfe79073ca7f8`
- canonical protocol SHA-256:
  `7dbae5deb711a1d456fb1304616b2f0b6741ffd2039154806f953221a61e06f6`
- canonical protocol size: `15,157` bytes

The underlying successful V2 feature evidence remains:

- execution run `31990121181`
- artifact `9275052993`
- artifact SHA-256
  `f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb`
- artifact size `23,349,191` bytes
- projection SHA-256
  `5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed`
- projection size `23,342,076` bytes
- 21,326 rows / 21,326 unique fixtures / zero identity-lineage conflicts

The source-bound builder verifies the exact projection digest, size, and row
count before any fitting work is allowed to begin.

## Exact input semantics

The validator accepts only canonical NDJSON rows from source namespace:

`fotmob_data_matches_reviewed_ordinary_ft_finished_score`

Each complete model row uses exactly:

1. intercept `1.0`
2. `(home_elo - 1500) / 400`
3. `(away_elo - 1500) / 400`
4. `home_form - 0.5`
5. `away_form - 0.5`
6. raw `fatigue`

`home_form`, `away_form`, and `fatigue` must have the reviewed strictly-prior
UTC status. Missing values remain missing and the row is excluded. No zero fill,
constant fill, forward fill, league mean, or other imputation is permitted.

Overall Elo may be either strictly-prior constructed state or the frozen 1500
initial-state assumption already qualified upstream. Elo must remain the
`OVERALL` component.

Historical `live_data_freshness` must remain exactly
`NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE` with a null value. It is not a
numeric predictor.

## Frozen common population

The complete-case population is determined once, before any reduced model arm
is fit. Every arm must preserve the same evaluation fixture identities.

Expected common population:

| Population | Rows | Membership SHA-256 |
|---|---:|---|
| All complete | 21,129 | `1374fd323bd5aa7e6da6cee23358621c26435297c2e195553e227373008fd8ed` |
| Train | 14,181 | `4c017b9e43ab9e2f231e88187339a3960c5fdfbd087f21ba92ca8855576219a9` |
| Evaluation A | 3,471 | `4361cd60976170bd14442502025160d9b3aa97717fb94afc1b68eee9b88c429f` |
| Evaluation B | 3,477 | `4910b5db577bd87fd4bed4e24f3b1e00dff85d58f23e7ea8558cfba0aa5efd59` |
| Pooled A+B | 6,948 | `f4d713a739feeac90c166f5125dd80ab7e3063598f9ad0187f07d10b88e5bcdc` |

Membership bytes are exactly:

`kickoff_utc<TAB>fixture_identifier<NEWLINE>`

in `(kickoff_utc, fixture_identifier)` order. Any count or membership-hash
drift fails closed.

Chronology remains:

- train: 2020-08-01 inclusive to 2024-07-01 exclusive
- Evaluation A: 2024-07-01 inclusive to 2025-07-01 exclusive
- Evaluation B: 2025-07-01 inclusive to 2026-08-15 exclusive

Evaluation B is retrospective, not a prospective holdout.

## Five reviewed arms

The implementation evaluates exactly the five PR #140 arms:

1. `FOTMOB_NATIVE_SAME_FAMILY_REFIT`
2. `HISTORICAL_FIXED_COEFFICIENT_TRANSFER`
3. `FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM`
4. `FOTMOB_NATIVE_NO_FATIGUE_ABLATION`
5. `TRAIN_ONLY_GLOBAL_HOME_AWAY_MEAN_BASELINE`

The native full, Elo-only, and no-fatigue fits all reuse
`historical_expected_goals_successor_robustness_evaluator.fit_poisson_design`,
which reuses the frozen PR #73 Newton/Poisson numerical primitives. The
implementation does not substitute sklearn, add regularization, tune alpha,
change predictor scaling, use randomized splits, perform K-fold search, or
refit after evaluation.

Historical transfer uses the exact reviewed historical home/away coefficient
vectors frozen in PR #140. The global-mean baseline uses only the exact common
training rows.

## Metrics and calibration

For Evaluation A, Evaluation B, and pooled A+B, every arm reports:

- mean joint Poisson NLL
- home NLL and away NLL
- home/away bias
- home/away MAE
- home/away RMSE
- home/away WACE
- home/away WSCE
- complete calibration tables

Calibration uses each model's own predicted rate for bin assignment and the
exact PR #140 bins. Empty bins have count zero and null means/error; they do not
become fabricated zero-error observations.

The required paired NLL deltas are also emitted exactly as frozen in PR #140.

## UTC-quarter paired jackknife

Temporal robustness uses the exact 6,948 pooled evaluation fixtures and the
exact frozen quarter counts:

- 2024-Q3: 626
- 2024-Q4: 1,017
- 2025-Q1: 1,073
- 2025-Q2: 755
- 2025-Q3: 599
- 2025-Q4: 1,020
- 2026-Q1: 1,097
- 2026-Q2: 721
- 2026-Q3: 40

The paired fixture difference is native-refit joint NLL minus Elo-only joint
NLL. The delete-quarter estimator is the mean on the remaining fixtures;
`theta_bar` is the **unweighted** mean of the nine delete estimates. The
jackknife standard error and `full theta ± 1.96*SE` interval follow PR #140
exactly.

Unexpected, missing, duplicated, or count-drifted quarters fail closed.

## Interpretation only, never automatic approval

The validator may report either:

- `STRONG_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED`, or
- `MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED`.

Even the strong state requires a separate human/review boundary. It does not
approve an expected-goals transform or grant ScoreMatrix/probability authority.

Competition/league robustness remains exactly:

`BLOCKED_PROJECTION_DOES_NOT_CARRY_COMPETITION_IDENTITY`

No competition identity may be inferred, fuzzily reconstructed, or imported
from a different evidence surface in this boundary.

## Runtime provenance and the PR #77 portability caveat

The validation receipt records the exact Python version, Python implementation,
platform, and machine used for execution.

PR #77 demonstrated that the historical fitter can reproduce the same
substantive coefficients and NLLs across runtimes while unrounded convergence
gradient diagnostics differ at machine-precision scale. This implementation
does not claim that cross-runtime canonicalization issue is solved.

Every source-bound receipt therefore records:

- `cross_runtime_bit_identity_claimed = false`
- `known_pr77_machine_precision_canonicalization_gap_cleared = false`

That portability issue remains a separate production-hardening boundary.

## Outputs

A later controlled execution may write:

- evaluation prediction NDJSON for the exact 6,948 A+B fixtures; and
- one canonical validation receipt.

The prediction artifact contains each A/B fixture once and carries the five
model-arm home/away expected-goals rates. The receipt records exact input
membership, all fit diagnostics, metrics, calibration, paired deltas,
quarter-jackknife results, prediction digest/size/count, runtime provenance,
and the all-false safety map.

No production model artifact is written.

## CLI

After this implementation is separately reviewed and merged, a controlled
execution boundary may invoke:

```text
python -m scripts.validate_fotmob_utc_native_expected_goals_model \
  <exact-v2-projection.ndjson> \
  --predictions-output <predictions.ndjson> \
  --receipt-output <receipt.json>
```

**Do not run that source-bound command as part of PR #142 implementation or
review.** The real 21,326-row validation is a later reviewed execution boundary.

## Safety

All of these remain exact false:

- successor candidate approval
- model-training authorization for production
- expected-goals transform approval/production
- ScoreMatrix authorization
- probability inference or adjustment
- calibration for production
- pricing
- market activation
- selection
- production approval
- BET authorization

The next boundary after a later successful source-bound execution is:

`REVIEW_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_RESULT`
