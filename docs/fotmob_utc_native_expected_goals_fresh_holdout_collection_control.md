# FotMob UTC-native expected-goals fresh-holdout collection control

## Boundary

This boundary installs the reviewed **pre-activation collection control** required after merged PR #149. It freezes the exact experiment clock, request cadence, provider-native capture scope, and durable evidence obligations before any live collection is allowed.

It does **not** install a scheduled GitHub workflow, perform a FotMob request, start the holdout campaign, calculate confirmation metrics, approve a successor, or grant production/BET authority.

The next boundary remains the explicit live activation runner.

## Exact implementation merge and holdout clock

Merged PR #149 is fixed as:

- merge commit: `9ba66cff0677b5952c6c931ddf3cefb7c9565187`;
- merge timestamp: `2026-08-18T04:18:35Z`;
- merged implementation blob: `5dabab12d5205d384fd3904cda0e68661ef90791`.

The frozen PR #148/PR #149 start resolver therefore gives:

- fresh holdout start: **`2026-08-19T00:00:00Z`**;
- minimum count-only gate boundary: **`2026-09-16T00:00:00Z`** (`+28 days`);
- hard close boundary: **`2026-11-17T00:00:00Z`** (`+90 days`);
- deterministic settlement-only tail end: **`2026-11-18T00:00:00Z`**.

The 24-hour settlement tail does not add fixtures to the scored population. It exists only to allow repeated ordinary-FT evidence for fixtures whose sealed kickoff is before hard close but whose stable result is observed shortly after the close boundary.

## Capture cadence

The activation runner must use a fixed outcome-independent UTC cadence:

- every **30 minutes**;
- exact scheduled UTC minutes `:00` and `:30`;
- no result, goal, NLL, WACE, WSCE, competition performance, price, or bet state may alter that cadence.

During the prediction/settlement collection phase, each tick plans exactly two existing reviewed FotMob `data/matches` requests:

1. `date = UTC today`;
2. `date = UTC tomorrow`.

Both requests use:

- `timezone=UTC`;
- `ccode3=NGA`;
- the existing reviewed transparent FotMob data-matches request/capture contract.

The control contract itself keeps `network_acquisition_authorized = false`; the live activation PR must add that authority narrowly and explicitly.

## Why today + tomorrow

The frozen prospective prediction window is 24 hours to 60 minutes before kickoff. Capturing UTC today plus UTC tomorrow at every fixed tick lets the later runner observe fixtures before and during that window without fuzzy league discovery or a separate competition list.

Observations earlier than the allowed window are retained as source evidence but cannot be selected as the prediction seal. The merged PR #149 selector still chooses the earliest **actually observed** qualifying capture inside the frozen window.

## Competition coverage

Fresh capture is deliberately **not limited to the 11 legacy provider primary IDs**.

Every wrapper/fixture returned by the reviewed FotMob capture must pass the PR #149 structural qualification:

- exact positive `leagues[].primaryId`;
- exact positive wrapper `leagues[].id`;
- exact positive fixture `leagues[].matches[].id`;
- exact `match.leagueId == containing league.id`;
- exact source team IDs;
- exact source UTC kickoff.

All structurally qualified provider `primaryId` clusters are retained for the fresh holdout. That is what allows non-legacy leagues, cups, continental competitions, and international competitions to enter the evaluation when the provider exposes them through the same reviewed source structure.

The distinction remains strict:

- **evaluation scope:** all structurally qualified fresh provider-native competition IDs;
- **form/Elo/fatigue history mutation:** only the frozen legacy primary IDs `{40,47,53,54,55,57,61,64,71,87,135}`.

A non-legacy fixture may be predicted and scored when its inherited legacy-history features are complete, but its result may never expand or mutate the frozen history-state scope.

## Durable evidence requirements

The activation runner must maintain one state root:

`.cache/athena-research/fotmob-utc-native-xg-fresh-holdout`

with append-only or immutable evidence including:

- `capture-index.ndjson` — every reviewed raw capture lineage;
- `prediction-journal.ndjson` — every sealed complete-case prediction and explicit missing-prediction disposition;
- `post-seal-identity-journal.ndjson` — every later qualified observation for each sealed fixture;
- `settlement-journal.ndjson` — reviewed ordinary-FT settlement/exclusion results;
- `control-journal.ndjson` — tick/control progress and fail-closed execution events;
- `checkpoint.json` — reconstructible cross-run progress pointer, never sole evidence authority.

The runner must preserve the exact raw capture directories produced by the existing reviewed FotMob capture utility. Journal entries may reference those immutable capture/manifests by SHA; they may not replace the raw evidence.

## Prediction durability rule

A prediction is usable only if its complete canonical `SealedFreshPrediction` record is durably published **before kickoff**.

The activation runner must first restore the exact reviewed PR119 bootstrap projection, build the PR #149 `FreshHistoryLedger`, append only reviewed legacy fresh settlements, and then call the merged PR #149 predictor.

No default or imputation is permitted for missing form/fatigue. Missing cases are journaled and cannot later be retrofilled after the result is known.

## Post-seal identity completeness

Every qualified source observation made after a fixture is sealed must be retained in the post-seal identity journal.

At settlement the runner must supply that entire preserved observation sequence to PR #149. Therefore:

- later kickoff drift excludes the original seal;
- provider `primaryId`, wrapper, team, or fixture-identity drift excludes the seal;
- a change followed by a later reversion **remains excluded**;
- omitting a known intermediate drift is forbidden.

The first/second post-finish raw captures used by the reviewed ordinary-FT adapter are also provider-requalified by PR #149 before a result may be scored.

## Close and settlement phases

Before `2026-11-17T00:00:00Z`, scheduled ticks are in `PREDICTION_AND_SETTLEMENT_COLLECTION` phase. The eventual selected scored-population close may occur earlier, beginning at the +28-day boundary, but only through PR #149's count-only close state machine.

The live runner must stop admitting new scored-population predictions once the selected close boundary is known. Result timing cannot change membership.

At the hard-close boundary this control switches to `SETTLEMENT_TAIL_ONLY`: only UTC-today capture is planned, prediction sealing is disabled, and the purpose is stable settlement of already pre-close fixtures.

At `2026-11-18T00:00:00Z`, this fixed control envelope is complete. Any unresolved fixture remains unscored/excluded unless a later separately reviewed protocol says otherwise.

## Safety

This control grants no:

- production expected-goals authority;
- ScoreMatrix authority;
- probability inference/adjustment authority;
- calibration-for-production authority;
- pricing or market activation authority;
- selection or BET authority;
- competition-registry mutation;
- successor approval.

It also performs no network acquisition itself.

## Next boundary

`ACTIVATE_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_COLLECTION_RUNNER`

That PR must implement the resumable cross-run state restoration, exact bootstrap retrieval, existing FotMob capture calls, immutable journal publication, prediction sealing, post-seal observation retention, and reviewed ordinary-FT settlement loop. Only that separately reviewed/merged activation boundary may begin live requests on or after `2026-08-19T00:00:00Z`.
