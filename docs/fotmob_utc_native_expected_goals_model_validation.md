# FotMob UTC-native expected-goals model validation implementation

## Boundary

PR #142 implements the result-producing research validator pre-registered by
merged PR #140. Review and merge do **not** execute the real 21,326-row source
corpus. Source-bound execution remains a separate controlled boundary.

The implementation does not invoke ScoreMatrix, derive market probabilities,
inspect bookmaker prices, choose selections, write a production model artifact,
or authorize production/BET use.

## Exact reviewed parent

The implementation is bound to merged PR #140:

- merged parent `main`: `df4a24454ae479dc68f27d19ee3f9101fd1d3b7c`
- PR #140 protocol implementation blob:
  `1780330c4d0ab9140f0b2f6c776dfe79073ca7f8`
- canonical protocol SHA-256:
  `7dbae5deb711a1d456fb1304616b2f0b6741ffd2039154806f953221a61e06f6`
- canonical protocol size: `15,157` bytes

The successful V2 feature evidence is frozen as:

- execution run `31990121181`
- result comment `5311318782`
- artifact ID `9275052993`
- artifact SHA-256
  `f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb`
- artifact size `23,349,191` bytes
- projection member `utc-native-feature-projection-v2.ndjson`
- projection SHA-256
  `5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed`
- projection size `23,342,076` bytes
- 21,326 rows / 21,326 unique fixtures / zero identity-lineage conflicts

## Two-layer implementation

The implementation deliberately separates calculation from evidence authority.

`domain/fotmob_utc_native_expected_goals_model_validation.py` is the lower-level
projection evaluator. It parses canonical rows, freezes the reviewed population,
fits/evaluates the five model arms, and calculates the pre-registered metrics.
It can therefore be exercised with synthetic fixtures in tests. A direct call
to that projection evaluator does **not** by itself establish a source-bound
result.

`domain/fotmob_utc_native_expected_goals_model_validation_source_bound.py` is
the reviewed source-bound entrypoint. It accepts only the exact preserved V2
artifact ZIP, proves the archive and qualification ancestry, then supplies the
verified projection to the lower-level evaluator and seals the result with
source evidence plus per-arm membership proof.

The CLI is only a thin launcher for that domain source-bound entrypoint.

## Source-bound artifact gate

Before any fitting is allowed, the domain source-bound gate verifies:

1. exact archive SHA-256 and byte size;
2. unique ZIP member names and valid member CRCs;
3. presence of `qualification-v2-receipt.json` and the reviewed projection;
4. exact projection SHA-256, byte size, and 21,326-row count;
5. canonical qualification-receipt bytes;
6. exact qualification schema, status, state, and next boundary;
7. exact qualification protocol SHA-256 and size;
8. exact canonical UTC time-basis semantics with no source-local parity claim;
9. exact record, unique-fixture, same-kickoff, and zero-conflict counts;
10. an empty identity/lineage conflict list;
11. historical live freshness still blocked/non-numeric; and
12. the exact reviewed safety-key set with every flag `false`.

Only after those checks does the gate materialize the already-verified
projection into a temporary local file for the projection evaluator.

The final source-bound receipt records the artifact ID/name/digest/size,
qualification run/result-comment identity, projection identity, and canonical
qualification-receipt digest/size.

## Exact input semantics

The validator uses only canonical rows from source namespace:

`fotmob_data_matches_reviewed_ordinary_ft_finished_score`

Each complete model row has exactly:

1. intercept `1.0`
2. `(home_elo - 1500) / 400`
3. `(away_elo - 1500) / 400`
4. `home_form - 0.5`
5. `away_form - 0.5`
6. raw `fatigue`

Missing home form, away form, or fatigue stays missing. There is no zero fill,
constant fill, forward fill, league mean, or other imputation. Overall Elo may
use either the qualified strictly-prior state or frozen 1500 initial-state
assumption and must remain the `OVERALL` component.

Historical `live_data_freshness` remains exactly
`NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE` with null numeric value and is not a
predictor.

## Frozen common population

Complete-case membership is determined once before any reduced model arm.
Expected identities are:

| Population | Rows | Membership SHA-256 |
|---|---:|---|
| All complete | 21,129 | `1374fd323bd5aa7e6da6cee23358621c26435297c2e195553e227373008fd8ed` |
| Train | 14,181 | `4c017b9e43ab9e2f231e88187339a3960c5fdfbd087f21ba92ca8855576219a9` |
| Evaluation A | 3,471 | `4361cd60976170bd14442502025160d9b3aa97717fb94afc1b68eee9b88c429f` |
| Evaluation B | 3,477 | `4910b5db577bd87fd4bed4e24f3b1e00dff85d58f23e7ea8558cfba0aa5efd59` |
| Pooled A+B | 6,948 | `f4d713a739feeac90c166f5125dd80ab7e3063598f9ad0187f07d10b88e5bcdc` |

Membership bytes are exactly
`kickoff_utc<TAB>fixture_identifier<NEWLINE>` in chronological fixture order.
Any count/hash drift fails closed.

The source-bound receipt repeats exact train/A/B/pooled membership count/hash
under **every model arm** and reconciles each arm's reported evaluation fixture
count to the common population. The fixed historical-transfer arm correctly has
no fit population, while every fitted/baseline arm records the frozen common
training membership. Any mismatch fails closed.

Chronology remains:

- train: 2020-08-01 inclusive to 2024-07-01 exclusive
- Evaluation A: 2024-07-01 inclusive to 2025-07-01 exclusive
- Evaluation B: 2025-07-01 inclusive to 2026-08-15 exclusive

Evaluation B is retrospective, not a prospective holdout.

## Five reviewed arms

Exactly these PR #140 arms are evaluated:

1. `FOTMOB_NATIVE_SAME_FAMILY_REFIT`
2. `HISTORICAL_FIXED_COEFFICIENT_TRANSFER`
3. `FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM`
4. `FOTMOB_NATIVE_NO_FATIGUE_ABLATION`
5. `TRAIN_ONLY_GLOBAL_HOME_AWAY_MEAN_BASELINE`

The native full, Elo-only, and no-fatigue fits reuse
`historical_expected_goals_successor_robustness_evaluator.fit_poisson_design`
and therefore the frozen deterministic Newton/Poisson numerical family. There
is no sklearn substitution, regularization/alpha search, randomized split,
K-fold tuning, predictor re-standardization, or post-evaluation refit.

Historical transfer uses the exact PR #140 home/away coefficients without
refit. The global-mean baseline uses the exact common training rows only.

## Evaluation

For Evaluation A, Evaluation B, and pooled A+B every arm reports:

- joint, home, and away Poisson NLL;
- home/away bias, MAE, and RMSE;
- home/away WACE and WSCE;
- exact PR #140 calibration tables; and
- every required paired NLL delta.

Calibration uses each model's own predicted rate for bin assignment. Empty bins
carry count zero and null means/error; they are never fabricated as zero-error
observations.

Temporal robustness uses the exact 6,948 pooled evaluation fixtures and frozen
nine UTC-quarter counts: 626, 1,017, 1,073, 755, 599, 1,020, 1,097, 721, and
40 for 2024-Q3 through partial 2026-Q3. The delete-estimate center is the
**unweighted** mean of the nine delete estimates and the interval is
`full theta ± 1.96*SE` exactly as pre-registered.

A future result can only be:

- `STRONG_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED`, or
- `MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED`.

Neither state automatically approves a model. The source-bound receipt also
carries `automatic_model_approval = false`.

Competition/league robustness remains
`BLOCKED_PROJECTION_DOES_NOT_CARRY_COMPETITION_IDENTITY`; identity may not be
invented or fuzzily reconstructed here.

## Runtime provenance

The receipt records Python version/implementation, platform, and machine.
Because PR #77 identified machine-precision canonicalization differences across
runtimes, every result retains:

- `cross_runtime_bit_identity_claimed = false`
- `known_pr77_machine_precision_canonicalization_gap_cleared = false`

## Outputs and CLI

A later controlled execution writes canonical pooled A+B prediction NDJSON and
one canonical source-bound validation receipt.

The invocation shape is:

```text
python -m scripts.validate_fotmob_utc_native_expected_goals_model \
  <exact-v2-feature-qualification-artifact.zip> \
  --predictions-output <predictions.ndjson> \
  --receipt-output <receipt.json>
```

**Do not run this real source-bound command during PR #142 implementation or
review.**

## Safety and next boundary

ScoreMatrix, market probabilities, bookmaker prices, market activation,
selection, production approval and BET authorization remain false. No production
model artifact is written.

After a later controlled execution, the next boundary is:

`REVIEW_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_RESULT`
