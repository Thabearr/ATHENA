# FotMob UTC-native expected-goals fresh-holdout implementation

## Boundary

This implementation realizes the pure research core pre-registered by merged PR #148. It does **not** start the prospective holdout, schedule or perform network acquisition, refit any xG/calibration coefficient, calculate market probabilities, inspect prices, select bets, or authorize production/BET use.

Implementation and activation remain separate. A later reviewed control boundary must resolve the actual holdout start from this implementation merge timestamp and install the network, scheduling and durable evidence-retention lane. Until that later boundary executes, `fresh_holdout_started = false` and every downstream safety flag remains false.

The frozen parent protocol is:

- protocol blob `9f45e17603a2678741ccc596d2542a0c6e29fa6c`;
- canonical size `9,941` bytes;
- canonical SHA-256 `d67407a315b583ddeb60514a136860fb72f1476ea3035deae8ff993e30daf171`.

## Reviewed dependency pins

The implementation fails closed if any numerical or source-semantic dependency moves:

- UTC-native feature constructor blob `9c9e424791b65292f7bbe8849b3214c140834889`;
- fixture-candidate builder blob `a3434951e87cfbd90dd2c43cccd413e7edfb08e0`;
- raw data-matches capture contract blob `ca2149395de868104666620173b55a880b10c729`;
- reviewed ordinary-FT score adapter blob `868563206e09010fce74b4ba7954028930baad54`;
- exact reviewed PR119 legacy bootstrap projection `10,545,099` bytes / SHA-256 `e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2` / `21,326` rows.

The bootstrap is accepted only by exact bytes. Metadata that merely claims the right hash, size or row count cannot construct a normal `FreshHistoryLedger`.

## Exact holdout start

`resolve_holdout_start(implementation_merge_utc)` returns the first UTC `00:00` boundary strictly after the reviewed implementation merge, never earlier than `2026-08-15T00:00:00Z`.

A merge exactly at midnight therefore resolves to the **next** midnight. The activation/control PR must record the actual merge timestamp and the resolved start; this implementation does not guess either in advance.

## Provider-native capture qualification

`qualify_capture_fixtures(...)` consumes the existing reviewed `FotMobDataMatchesCaptureManifest` plus exact raw bytes. It re-runs the reviewed capture/schema/candidate chain and then applies the stricter PR #148 provider-native identity checks.

Every admitted wrapper/fixture must prove:

- `leagues[].primaryId` is an exact positive integer;
- `leagues[].id` is an exact positive integer and wrapper IDs are unique inside the capture;
- `leagues[].matches[].id` is an exact positive integer and fixture IDs are unique inside the capture;
- `leagues[].matches[].leagueId` is an exact positive integer and equals the containing wrapper `id` exactly;
- home and away source team IDs are exact positive integers and differ;
- `status.utcTime` is exact UTC `Z` time;
- raw SHA-256 and reviewed candidate extraction agree exactly with the admitted identity.

Names, aliases and `model_league_code` never create competition identity. A structurally malformed wrapper fails closed rather than being fuzzily admitted.

## Prospective pre-kickoff seal

`select_earliest_qualifying_capture(...)` accepts observations for exactly one FotMob fixture ID. A capture qualifies only when:

`holdout_start <= capture_observed_at`

and

`kickoff - 24h <= capture_observed_at <= kickoff - 60m`.

The **earliest** qualifying observation is the prospective seal. If two observations at that exact earliest `observed_at` disagree on provider `primaryId`, wrapper ID, team IDs or kickoff, selection fails closed as ambiguous. A later observation does not retroactively replace the earliest seal.

This distinction matters: later identity/kickoff drift is an exclusion condition, not permission to mutate or retime the original prediction.

No qualifying capture returns `None`; it may not later be retrofilled from post-result evidence.

## Exact legacy-history state

Fresh prediction state is seeded from the exact reviewed PR119 materialization projection. `FreshHistoryLedger` has no normal metadata/row constructor: its normal constructor requires the exact bootstrap bytes and re-parses them before a ledger exists.

Reviewed fresh ordinary-FT settlements from the frozen 11 provider-primary-ID history scope may be appended later. The append API accepts the settlement-derived `SettledFreshPrediction`, revalidates its original seal against the current ledger, and only then appends its legacy history update. An arbitrary caller-created history row cannot use the public append path.

The frozen update scope remains:

`{40,47,53,54,55,57,61,64,71,87,135}`.

Non-legacy settlement results may be evaluated, but they never update form/Elo/fatigue history state.

For a target capture, only result rows satisfying both are replayed:

- result kickoff is strictly before target kickoff;
- reviewed result evidence was observed no later than the selected capture `observed_at`.

The implementation then calls the already-reviewed UTC-native feature constructor rather than duplicating its mathematics. A synthetic target row with dummy `0-0` score exists only so that constructor emits the target's **pre-match** feature row. The constructor calculates all target features before applying the target row's pending result update, so the dummy result never influences the sealed features and is never persisted as history.

The inherited feature semantics remain:

- overall pre-match Elo with frozen 1500 initial state, home +50 expected-score boost, divisor 400, K `32/24/16`, integer update;
- recent-five form with the reviewed `0.10..0.95` formula and no default;
- reviewed home-relative rest-day fatigue and no default;
- strictly prior UTC history with same-kickoff batching before state mutation;
- historical live-data freshness remains the exact reviewed blocked/null historical state.

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
- selected capture timestamp plus manifest/raw SHA lineage;
- exact reviewed bootstrap SHA-256;
- history-prefix hash/count;
- feature-projection hash;
- five feature values;
- native, Elo-only and calibrated rates;
- exact PR #148 protocol identity;
- all safety flags false.

The dataclass itself reconstructs every rate from the frozen five features and rejects coherent-looking rate tampering. Before settlement, `revalidate_sealed_prediction(...)` rebuilds the complete seal from the exact history ledger and selected capture; a caller who changes both features and rates coherently still fails because the rebuilt canonical seal no longer matches.

## Post-seal identity drift

PR #148 states that if the provider later changes kickoff, the old prediction is excluded and may not be reused, retimed or mapped onto the rescheduled fixture.

`post_seal_identity_drifted(...)` therefore compares every preserved post-seal observation for that fixture against the original sealed identity:

- fixture ID;
- provider `primaryId`;
- wrapper ID;
- home/away team IDs;
- sealed kickoff UTC.

Any observed difference is permanently excluding for that seal. A provider change followed by a later reversion does **not** restore eligibility.

The next control lane has an important completeness duty: every qualified observation it makes after a seal must be retained in the fixture's post-seal identity journal and supplied at settlement. Omitting a known intermediate drift would violate the reviewed boundary.

## Reviewed ordinary-FT settlement binding

The public `settle_sealed_prediction(...)` does **not** accept a caller-fabricated score mapping or a prebuilt adapter result as sufficient evidence. It requires:

- the exact `FreshHistoryLedger` used to deterministically replay the seal;
- every preserved post-seal identity observation;
- first raw post-finish capture + exact reviewed manifest;
- second raw post-finish capture + exact reviewed manifest.

The function then:

1. revalidates the sealed prediction against exact ledger state;
2. re-runs provider-native qualification on both raw settlement captures;
3. re-proves provider `primaryId`, wrapper ID, fixture/team identity and sealed kickoff from those raw captures;
4. combines those settlement identities with the preserved post-seal identity journal and excludes if **any** observation drifted;
5. invokes the existing reviewed ordinary-FT capture-pair adapter;
6. scores only if the sealed fixture passes that reviewed ordinary-FT gate.

This raw-pair requalification is necessary because the reviewed ordinary-FT score adapter retains wrapper/league ID but does not retain provider `primaryId` in its score object.

Cancelled, postponed, awarded, penalty, extra-time, unstable or otherwise unreviewed results do not become scored holdout labels.

The final settlement evidence SHA binds the prediction SHA, exact provider competition identity, both raw/manifest pair lineages and the exact qualified score.

A legacy-primary settlement emits one research history-state update. A non-legacy settlement emits none.

## Count-only close state machine

`coverage_at_boundary(...)` intentionally accepts sealed predictions only—no goals, NLL, WACE, WSCE or other performance input—and rejects a population that mixes different resolved holdout starts.

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
- at/after minimum: close immediately at the first UTC midnight where all count-only gates pass;
- at hard close with insufficient coverage: `FRESH_HOLDOUT_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION`;
- boundaries after hard close are invalid.

Kickoff is right-exclusive at the selected close boundary. Result arrival time cannot choose membership. Goals or model performance cannot choose when the population closes.

## What this PR deliberately does not implement

This PR does not:

- schedule or call FotMob;
- choose the implementation merge timestamp in advance;
- create the durable capture/prediction/post-seal-drift journals;
- upload fresh artifacts;
- start the 28/90-day clock;
- calculate the final pooled WACE/WSCE/NLL or competition jackknife result;
- approve a successor;
- authorize ScoreMatrix, probability, pricing, selection, production or BET use.

The final result evaluator may be implemented before the minimum 28-day review boundary from the already-frozen PR #148 mathematics without altering the fresh evidence sealed by the collection lane.

## Next boundary

`INSTALL_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_COLLECTION_CONTROL`

That next PR should install the smallest reviewed activation/scheduling/evidence-retention lane around this pure core. Its merge/execution boundary must remain separate from this implementation PR, and it must durably preserve both the prediction seal and every subsequent identity/kickoff observation for each sealed fixture.