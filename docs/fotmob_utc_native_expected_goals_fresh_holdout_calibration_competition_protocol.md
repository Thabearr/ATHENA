# FotMob UTC-native xG fresh-holdout calibration and competition-identity protocol

## Boundary

This is a result-free pre-registration for the follow-up required by the reviewed UTC-native expected-goals result. It does **not** collect a fresh fixture, refit the xG model on fresh labels, change ScoreMatrix, calculate market probabilities, inspect bookmaker prices, select bets, or grant production/BET authority.

The parent review is merged on `main` at `5c46aa8fcaf4338e8968c50e1c852301f8e2e0cd`. The successful model-validation evidence remains run `32049714066`, artifact `9294215497`, archive SHA-256 `e9eac385a66df04bf28e7d69062e55db516829e94405e4a8def0e4d6a346d6c5`, canonical receipt SHA-256 `1fffee7474ab37ee613e6a7943b57fd9231f6d6bdf53ffa6b13ee2b62ceca06a`, and predictions SHA-256 `2f4939a8f2d41674660144f5315d2420ce2f006ce2b885e52c6655abd0e52420`.

## What is being calibrated

The native xG family itself is not refit. Its reviewed coefficients remain frozen. The already-inspected A+B labels are development evidence only and can never become a fresh confirmation set again.

The selected home-only calibration is the monotone positive two-parameter Poisson rate transform

`calibrated_home_lambda = exp(a + b * ln(native_home_lambda))`

with exact binary64 coefficients:

- `a = 0x1.11df1d736f167p-4` (`0.0668631697107621`);
- `b = 0x1.b4f2aad487cafp-1` (`0.853413904613168`).

Away xG is unchanged.

Those coefficients were selected only from the consumed `6,948` A+B rows. On those development rows the transform reduced home WACE from `0.05778673203465596` to `0.016320745023423927` and home WSCE from `0.0069982959681213885` to `0.0006027164419862363`. These numbers are **not confirmation evidence**. After this protocol is merged the calibration parameters may not be tuned again before the fresh result is reviewed.

## Exact competition identity

The old 11 model codes are not the competition universe.

The preserved FotMob source parser proves that the raw `data/matches` payload carries provider-native competition identity directly:

- competition family identity: `leagues[].primaryId`;
- competition wrapper/edition identity: `leagues[].id`;
- fixture wrapper identity: `leagues[].matches[].leagueId`;
- fixture identity: `leagues[].matches[].id`.

For every admitted fixture, `match.leagueId` must exactly equal the containing wrapper `league.id`. `primaryId`, wrapper `id`, and fixture `id` must be positive integers. Names, aliases and fuzzy mapping cannot create identity.

The 11 historical training-scope primary IDs remain `{40,47,53,54,55,57,61,64,71,87,135}`. Fresh **capture/evaluation discovery is not capped at those IDs**. `model_league_code` is legacy classification only and cannot substitute for provider-native competition identity.

## Feature-semantics guard

Broader evaluation must not silently change the model inputs that were trained and validated.

The historical state used for Elo, form and fatigue continues to update only from the frozen 11-primary-ID ordinary-FT history scope. A non-legacy competition fixture may be evaluated when both teams have complete frozen-semantics features, but that non-legacy result does not then enter the state update. Missing histories stay missing; they are not fuzzily reconstructed or imputed.

This makes the follow-up a test of transfer to additional exact competitions, not an unreviewed feature-definition change. Any future decision to make cups or international matches update form/Elo/fatigue is a separate model-feature boundary.

## Prospective fresh confirmation

The confirmation cannot start before `2026-08-15T00:00:00Z`, and in practice starts at the first UTC midnight strictly after the reviewed implementation PR is merged. That protects the confirmation from the fact that this protocol itself is being written after August 15.

For each fixture, the prediction and exact competition identity must be sealed before kickoff using the earliest qualifying source capture between 24 hours and 60 minutes before kickoff. A fixture with no qualifying pre-kickoff capture is missing and may not be reconstructed after the result is known.

Settlement must preserve exact fixture and competition identity and may admit only the already-reviewed ordinary-FT result semantics. Cancelled, postponed, special-result or otherwise unreviewed states are not scored.

## Outcome-independent close rule

The fresh population closes only by time and coverage, never by model performance.

The earliest close is after 28 calendar days. At the first later UTC day boundary, close when all of these count-only conditions are true:

- at least `1,000` complete-case fresh fixtures;
- at least `8` provider `primaryId` clusters with at least `30` complete-case fixtures each;
- at least `2` of those qualifying clusters are outside the legacy 11 primary IDs.

If those gates have not been met by 90 calendar days, the window closes anyway and the result is `FRESH_HOLDOUT_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION`.

Goals, errors, WACE, NLL and calibration performance may not influence when the population closes.

## Fresh pooled gates

On the sealed fresh population, the calibrated candidate must satisfy all of the following:

- home WACE is strictly below the uncalibrated native model;
- home WACE is strictly below Elo-only;
- home WSCE is strictly below the uncalibrated native model;
- home WSCE is strictly below Elo-only;
- calibrated joint Poisson NLL is strictly below Elo-only;
- calibrated joint NLL is not above the uncalibrated native model;
- the unchanged native away WACE remains strictly below Elo-only;
- the unchanged native away WSCE remains strictly below Elo-only.

Calibration uses the same frozen bins as the prior validation and each model is assigned to bins by its own predicted rate.

## Competition robustness gate

Competition robustness clusters by exact provider `primaryId`, not names and not model codes. A qualifying cluster needs at least `30` fresh complete-case fixtures.

On the union of qualifying clusters:

- compute fixture-paired `calibrated native joint NLL - Elo-only joint NLL`;
- compute a leave-one-`primaryId`-out jackknife with fixture-weighted remaining means;
- require the jackknife upper 95% bound to be strictly below zero;
- require at least 75% of qualifying competition clusters to have a negative within-cluster mean paired delta.

Per-competition NLL, home/away WACE, WSCE, row count and missingness must all be reported. Smaller competitions remain visible but report-only.

This is deliberately broader than the old 11-league test while still preserving the model's original feature semantics.

## Authority

Even if every fresh gate passes, the state is only:

`FRESH_HOLDOUT_CALIBRATION_AND_COMPETITION_ROBUSTNESS_SIGNAL_REVIEW_REQUIRED`

There is no automatic successor approval. ScoreMatrix, probability inference/adjustment, pricing, selection, production and BET authority remain false.

## Next boundary

`IMPLEMENT_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_CALIBRATION_AND_COMPETITION_IDENTITY_FOLLOWUP`
