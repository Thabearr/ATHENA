# FotMob UTC-native expected-goals fresh-holdout implementation

## Boundary

This implementation realizes the pure research core pre-registered by merged PR #148. It does **not** start the prospective holdout, schedule or perform network acquisition, refit any xG/calibration coefficient, calculate market probabilities, inspect prices, select bets, or authorize production/BET use.

The implementation is intentionally separated from activation. A later reviewed control boundary must resolve the actual holdout start from this implementation merge timestamp and install the network/scheduling/evidence-retention lane. Until then, `fresh_holdout_started = false` and all downstream authority remains false.

The frozen parent protocol is:

- protocol blob `9f45e17603a2678741ccc596d2542a0c6e29fa6c`;
- canonical size `9,941` bytes;
- canonical SHA-256 `d67407a315b583ddeb60514a136860fb72f1476ea3035deae8ff993e30daf171`.

## Reviewed dependency pins

The implementation fails closed if any numerical/source dependency moves:

- UTC-native feature constructor blob `9c9e424791b65292f7bbe8849b3214c140834889`;
- fixture-candidate builder blob `a3434951e87cfbd90dd2c43cccd413e7edfb08e0`;
- raw data-matches capture contract blob `ca2149395de868104666620173b55a880b10c729`;
- reviewed ordinary-FT score adapter blob `868563206e09010fce74b4ba7954028930baad54`;
- exact reviewed PR119 legacy bootstrap projection `10,545,099` bytes / SHA-256 `e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2` / `21,326` rows.

The bootstrap is accepted only by exact bytes. The implementation does not infer its league composition from names or regenerate an approximate replacement.

## Exact holdout start

`resolve_holdout_start(implementation_merge_utc)` returns the first UTC `00:00` boundary strictly after the reviewed implementation merge, never earlier than `2026-08-15T00:00:00Z`.

Because the boundary is strict, a merge exactly at midnight still resolves to the **next** midnight.

The activation/control PR must record the actual merge timestamp and resolved start. This implementation does not guess that timestamp in advance.

## Provider-native capture qualification

`qualify_capture_fixtures(...)` consumes only the existing reviewed `FotMobDataMatchesCaptureManifest` plus exact raw bytes and re-runs the reviewed capture/schema/candidate chain before applying the stricter PR #148 identity checks.

Every admitted raw wrapper/fixture must prove:

- `leagues[].primaryId` is an exact positive integer;
- `leagues[].id` is an exact positive integer and wrapper IDs are unique in a capture;
- `leagues[].matches[].id` is an exact positive integer and fixture IDs are unique in a capture;
- `leagues[].matches[].leagueId` is an exact positive integer and equals the containing wrapper `id` exactly;
- home/away source team IDs are exact positive integers and different;
- `status.utcTime` is exact UTC `Z` time;
- raw SHA-256 and reviewed candidate extraction agree exactly with the admitted identity.

Names, aliases and `model_league_code` are never used to create competition identity. A structurally malformed/non-legacy wrapper fails closed rather than being fuzzily admitted.

## Pre-kickoff capture selection

`select_earliest_qualifying_capture(...)` requires all observations supplied for one fixture to agree on fixture ID, provider `primaryId`, wrapper ID, team IDs and kickoff UTC.

A capture qualifies only when:

`holdout_start <= capture_observed_at`

and

`kickoff - 24h <= capture_observed_at <= kickoff - 60m`.

The earliest qualifying capture is selected; capture-manifest SHA is the deterministic tie-break. No qualifying capture returns `None` and may not later be retrofilled from post-result evidence.

## Exact legacy-history state

Fresh prediction state is seeded from the exact reviewed PR119 materialization projection. Each row is canonical, has reviewed source namespace `fotmob_data_matches_reviewed_ordinary_ft_finished_score`, and carries immutable result/evidence lineage. `build_fresh_history_ledger(...)` accepts that bootstrap only when its complete `10,545,099` bytes and SHA-256 match exactly; the public prediction API requires the resulting `FreshHistoryLedger` rather than an arbitrary caller-supplied history list.

Reviewed fresh ordinary-FT settlements from the frozen 11 provider-primary-ID history scope may then be appended to the ledger. Non-legacy settlement rows cannot enter the history ledger.

For a target capture, only result rows satisfying both are replayed:

- result kickoff is strictly before the target kickoff;
- reviewed result evidence was observed no later than the selected capture `observed_at`.

The implementation then calls the already-reviewed UTC-native constructor rather than copying its mathematics. A synthetic target row with dummy `0-0` score is appended **only** so the constructor emits the target's pre-match feature row. The constructor calculates all target features before applying that target row's pending result update, so the dummy score never influences the sealed target features and is never persisted as history.

The inherited reviewed semantics therefore remain exactly:

- pre-match overall Elo, 1500 initial state, home +50 expected-score boost, divisor 400, K `32/24/16`, integer update;
- recent-five form with the reviewed `0.10..0.95` formula and no default;
- reviewed home-relative rest-day fatigue and no default;
- UTC ordering and same-kickoff batching before state mutation.

If home form, away form or fatigue is unavailable, the result is explicit `MISSING_REVIEWED_FEATURES`; nothing is imputed.

## Frozen xG prediction seal

For complete feature rows the predictor vector is exactly:

1. intercept `1`;
2. `(home_elo - 1500) / 400`;
3. `(away_elo - 1500) / 400`;
4. `home_form - 0.5`;
5. `away_form - 0.5`;
6. `fatigue`.

Native and Elo-only rates use the exact coefficients frozen by PR #148. Home calibration remains:

`exp(0x1.11df1d736f167p-4 + 0x1.b4f2aad487cafp-1 * ln(native_home_lambda))`.

Away calibration is exact native-away identity.

A `SealedFreshPrediction` binds:

- resolved holdout start;
- exact fixture/provider competition identity;
- selected capture timestamp + manifest/raw SHA lineage;
- history-prefix hash/count;
- feature-projection hash;
- five feature values;
- native, Elo-only and calibrated rates;
- exact PR #148 protocol identity;
- all safety flags false.

The dataclass itself rechecks holdout-start and 24h-to-60m temporal admission, so callers cannot construct a valid-looking seal outside the pre-registration window.

## Reviewed ordinary-FT settlement binding

`settle_sealed_prediction(...)` accepts the **reviewed pair-adapter result**, not a caller-fabricated score mapping. The adapter result must be `QUALIFIED_WITH_ORDINARY_FT_SCORES` and the sealed fixture must match exactly one qualified score.

Settlement must preserve exact:

- fixture ID;
- wrapper/league ID;
- home and away team IDs;
- sealed kickoff UTC.

The settlement evidence hash binds the sealed prediction SHA to both adapter capture lineages and the exact qualified ordinary-FT score.

If the sealed provider `primaryId` belongs to `{40,47,53,54,55,57,61,64,71,87,135}`, the settled result is emitted as an authorized **research history-state update** for later fresh predictions. A non-legacy result is still evaluated/settled but produces no history-state update. This is the frozen feature-scope rule from PR #148; it is not production/model-training authorization.

## Count-only close state machine

`coverage_at_boundary(...)` intentionally accepts sealed predictions only—no goals, NLL, WACE, WSCE or other performance input.

Population membership is exactly:

`holdout_start <= selected_capture_observed_at`

and

`holdout_start <= sealed_kickoff_utc < evaluated_boundary`.

At a UTC boundary it reports:

- complete-case sealed-prediction count;
- exact per-`primaryId` counts;
- qualifying `primaryId` clusters with at least `30` rows;
- qualifying non-legacy clusters;
- the three frozen count-only gates.

`evaluate_holdout_boundary(...)` freezes:

- minimum boundary = `holdout_start + 28 days` exactly;
- hard close = `holdout_start + 90 days` exactly;
- before minimum: remain open;
- at/after minimum: close immediately at the first boundary all count-only gates pass;
- at hard close with insufficient coverage: `FRESH_HOLDOUT_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION`;
- boundaries after hard close are invalid.

Kickoff is right-exclusive at the selected close boundary. Result arrival time cannot select membership.

## What this PR deliberately does not implement

This PR does not:

- schedule or call FotMob;
- choose the implementation merge timestamp in advance;
- create durable capture/prediction journals;
- upload fresh artifacts;
- start the 28/90-day clock;
- calculate the final pooled WACE/WSCE/NLL or competition jackknife result;
- approve a successor;
- authorize ScoreMatrix, probability, pricing, selection, production or BET use.

The final result evaluator can be implemented before the minimum 28-day review boundary from the already-frozen PR #148 mathematics without changing the fresh evidence that collection has sealed.

## Next boundary

`INSTALL_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_COLLECTION_CONTROL`

That next PR should install the smallest reviewed activation/scheduling/evidence-retention lane around this pure core. Its merge/execution boundary must remain separate from this implementation PR.
