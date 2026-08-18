# FotMob UTC-native expected-goals fresh-holdout collection control

## Boundary

This boundary installs the reviewed **pre-activation collection control** required after merged PR #149. It freezes the exact experiment clock, fixed provider-date capture cadence, count-only population-close state machine, provider-native competition scope, and durable evidence obligations before any live collection is allowed.

It does **not** install a scheduled GitHub workflow, perform a FotMob request, start the holdout campaign, calculate confirmation performance, approve a successor, or grant production/BET authority.

The next boundary remains the explicit live activation runner.

## Exact implementation merge and holdout clock

Merged PR #149 is fixed as:

- merge commit: `9ba66cff0677b5952c6c931ddf3cefb7c9565187`;
- merge timestamp: `2026-08-18T04:18:35Z`;
- merged implementation blob: `5dabab12d5205d384fd3904cda0e68661ef90791`.

The frozen PR #148/PR #149 resolver therefore gives:

- fresh holdout start: **`2026-08-19T00:00:00Z`**;
- first count-only gate boundary: **`2026-09-16T00:00:00Z`** (`+28 days`);
- hard close: **`2026-11-17T00:00:00Z`** (`+90 days`);
- latest possible 24-hour settlement-tail end: **`2026-11-18T00:00:00Z`**.

The scored-population close can occur earlier than hard close. Beginning at the +28-day UTC midnight, PR #149's count-only evaluator is the sole authority for deciding whether the population closes. If it closes early, the settlement tail ends exactly 24 hours after that selected close rather than running automatically to day 90.

## Fixed capture cadence

The activation runner must use an outcome-independent UTC cadence:

- every **30 minutes**;
- exact nominal UTC minutes `:07` and `:37`;
- no goal, result, NLL, WACE, WSCE, competition performance, bookmaker price, or bet state may alter that cadence.

The off-hour slots deliberately avoid the start-of-hour scheduling peak while preserving the same 30-minute spacing.

The nominal scheduled tick is control identity only. The live runner must retain the **actual reviewed capture `observed_at`** returned by the existing FotMob capture path; scheduler delay may never be rewritten as the nominal tick time.

Scheduled execution is treated as best-effort transport, not evidence authority. A delayed or dropped scheduled run is a missing capture opportunity and must be journaled. It may reduce power or eventually produce the frozen insufficient-coverage state, but it never authorizes a synthetic observation, a backdated capture, or a post-result prediction retrofill.

For a public repository, automatic schedule disablement after a long inactivity period is handled the same way: as a coverage/continuity risk. It cannot change the frozen start, move the selected close, or create backfill authority.

During prediction/settlement collection, each tick plans three existing reviewed FotMob `data/matches` request dates:

1. UTC yesterday;
2. UTC today;
3. UTC tomorrow.

All use:

- `timezone=UTC`;
- `ccode3=NGA`;
- the existing transparent reviewed FotMob data-matches request/capture contract.

The control contract itself keeps `network_acquisition_authorized = false`; the live activation PR must add that authority narrowly and explicitly.

## Why yesterday + today + tomorrow

Tomorrow is required because the frozen prediction window starts 24 hours before kickoff. Yesterday is required because a fixture that kicked shortly before UTC midnight may only become a stable reviewed ordinary-FT result after midnight while remaining addressable through the prior UTC match date.

Using only today + tomorrow would create a deterministic midnight hole in the settlement evidence chain. The three-date plan closes that hole without introducing league-name discovery, fuzzy mapping, or outcome-dependent requests.

Observations earlier than the allowed 24h-to-60m prediction window are retained as source evidence but cannot be selected as the prediction seal. PR #149 still chooses the earliest **actually observed** qualifying capture inside the frozen window.

## Count-only selected close is a control input, never an outcome input

At every UTC midnight beginning `2026-09-16T00:00:00Z`, the runner must reconstruct the current sealed-prediction population and call PR #149 `evaluate_holdout_boundary(...)` before allowing that midnight's prediction-sealing work.

`CloseControlState` records only:

- the UTC boundary evaluated;
- the PR #149 close/open decision;
- selected close UTC, if any;
- SHA-256 of the count-only coverage receipt.

An **open** close state is valid only through the latest required UTC midnight. At the next midnight it becomes stale and prediction sealing must fail closed until the new count-only evaluation is recorded.

A selected close is irreversible. At the selected boundary itself:

- new prediction sealing is disabled immediately;
- membership remains `kickoff_utc < selected_close_utc` exactly;
- collection switches to settlement-only requests;
- no result-arrival time can add a fixture to the closed population.

At day 90, PR #149 necessarily returns either a count-qualified close or the frozen insufficient-coverage close. There is no path that keeps prediction collection open past hard close.

## Competition coverage

Fresh capture is deliberately **not limited to the 11 legacy provider primary IDs**.

Every wrapper/fixture returned by the reviewed FotMob capture must pass PR #149 structural qualification:

- exact positive `leagues[].primaryId`;
- exact positive wrapper `leagues[].id`;
- exact positive fixture `leagues[].matches[].id`;
- exact `match.leagueId == containing league.id`;
- exact source team IDs;
- exact source UTC kickoff.

All structurally qualified provider `primaryId` clusters returned by this source are retained for the fresh holdout. This is what permits non-legacy leagues, domestic cups, continental competitions, and international competitions to enter the evaluation **when FotMob exposes them through the reviewed `data/matches` structure**. This control does not claim that `ccode3=NGA` exposes every competition worldwide; it preserves every structurally qualified competition the reviewed source actually returns.

The distinction remains strict:

- **evaluation scope:** all structurally qualified fresh provider-native competition IDs returned by the source;
- **form/Elo/fatigue history mutation:** only `{40,47,53,54,55,57,61,64,71,87,135}`.

A non-legacy fixture may be predicted and scored when its inherited frozen-history features are complete, but its result may never expand or mutate the legacy feature-history scope.

## Durable evidence requirements

The activation runner must maintain one state root:

`.cache/athena-research/fotmob-utc-native-xg-fresh-holdout`

with append-only or immutable evidence including:

- `capture-index.ndjson` — every reviewed raw capture lineage;
- `prediction-journal.ndjson` — every sealed complete-case prediction and explicit missing-prediction disposition;
- `post-seal-identity-journal.ndjson` — every later qualified observation for each sealed fixture;
- `settlement-journal.ndjson` — reviewed ordinary-FT settlement/exclusion results;
- `control-journal.ndjson` — tick/control progress, count-only close receipts, and fail-closed execution events;
- `checkpoint.json` — reconstructible cross-run progress pointer, never sole evidence authority.

The runner must preserve the exact raw capture directories produced by the existing reviewed FotMob capture utility. Journal entries may reference those immutable captures/manifests by SHA; they may not replace the raw evidence.

Close state must be reconstructible and revalidated from the durable prediction journal. A checkpoint claiming the population is still open cannot override a previously selected close receipt.

The control journal must also record detected scheduler gaps or disabled-schedule intervals. A later run may resume future captures, but missed prospective capture opportunities remain missing permanently.

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

The repeated post-finish raw captures used by the reviewed ordinary-FT adapter are also provider-requalified by PR #149 before a result may be scored.

## Settlement-only tail

Once a selected close exists, prediction sealing stops immediately. For the next 24 hours the fixed request dates become only:

1. UTC yesterday;
2. UTC today.

Tomorrow is no longer needed because no new predictions may enter the population. Yesterday remains necessary for fixtures crossing UTC midnight.

At `selected_close_utc + 24 hours`, this control envelope is complete. Any unresolved fixture remains unscored/excluded unless a later separately reviewed protocol says otherwise.

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

That PR must implement resumable cross-run state restoration, exact bootstrap retrieval, existing FotMob capture calls, immutable journal publication, count-only close-state persistence/revalidation, prediction sealing, post-seal observation retention, and reviewed ordinary-FT settlement. Only that separately reviewed/merged activation boundary may begin live requests on or after `2026-08-19T00:00:00Z`.
