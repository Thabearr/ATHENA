# FotMob UTC-native expected-goals model validation runner

## Boundary

This change implements the model-validation runner pre-registered by merged PR
#140. It is an **offline research evaluator**. Review/merge of this code does
not execute the preserved corpus and does not approve an expected-goals model.

The later execution input is the exact V2 feature-qualification artifact:

- artifact ID `9275052993`
- artifact SHA-256 `f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb`
- artifact size `23,349,191` bytes
- projection member `utc-native-feature-projection-v2.ndjson`
- projection SHA-256 `5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed`
- projection size `23,342,076` bytes
- rows `21,326`

The runner validates the archive identity **before** parsing or fitting.

## Frozen population

Rows with missing home form, away form, or fatigue are excluded once, before
any arm is reduced. No value is imputed. Historical live-data freshness remains
`NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE` with a null numeric value.

The exact common complete-case population is `21,129` fixtures:

| Population | Rows |
|---|---:|
| Train | 14,181 |
| Evaluation A | 3,471 |
| Evaluation B | 3,477 |
| Pooled A+B | 6,948 |

The runner recomputes every membership SHA-256 frozen in PR #140. All five arms
reuse those same fixture identities. Elo-only and no-fatigue arms do not rerun
eligibility and cannot admit extra rows.

## Model arms

Exactly five arms are evaluated:

1. `FOTMOB_NATIVE_SAME_FAMILY_REFIT`
2. `HISTORICAL_FIXED_COEFFICIENT_TRANSFER`
3. `FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM`
4. `FOTMOB_NATIVE_NO_FATIGUE_ABLATION`
5. `TRAIN_ONLY_GLOBAL_HOME_AWAY_MEAN_BASELINE`

The three fitted arms use the reviewed deterministic Newton Poisson-GLM
mathematics: train-only labels, log response-mean intercept initialization,
zero non-intercept initialization, `math.fsum` scalar reductions, deterministic
partial-pivot Gaussian elimination, frozen backtracking and convergence guards,
12-place coefficient rounding, and no regularization/search/refit.

The historical transfer arm uses the exact reviewed coefficients without
refitting. The constant baseline uses only exact common-training home/away goal
means.

The legacy Random Forest total-goals model is not loaded or used.

## Evaluation

For Evaluation A, Evaluation B, and pooled A+B, the runner reports:

- home/away and joint Poisson NLL
- bias, MAE, RMSE
- WACE and WSCE
- exact PR #140 calibration bins
- every required paired model delta

The pooled native-vs-Elo fixture differences are also evaluated with the exact
nine UTC-quarter delete-one-cluster jackknife. The delete-estimate center is an
**unweighted** mean of the nine delete estimates, exactly as pre-registered.

The pooled prediction file contains all `6,948` evaluation fixtures and all five
model arms. It is canonical NDJSON and SHA-256 sealed in the validation receipt.

## Runtime portability

PR #140 preserved the earlier cross-runtime canonicalization caveat. The
validation receipt therefore records Python/runtime provenance and explicitly
keeps `cross_runtime_bit_identity_qualified = false`.

A strong statistical signal is still only:

`STRONG_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED`

and otherwise:

`MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED`

Neither state approves a model.

## Safety

The runner never:

- builds `ScoreMatrix`
- calculates market probabilities
- reads bookmaker prices
- selects bets
- writes a production model artifact
- uses historical freshness as a numeric predictor
- invents league/competition identity

Every model-production, probability, calibration-production, pricing,
market-activation, selection, production and BET authority flag remains false.

After this implementation is reviewed and merged, the next separate boundary is:

`EXECUTE_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION`

The preserved 21,129-row study must not be executed during this implementation
PR review.
