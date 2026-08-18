# FotMob UTC-native xG fresh-holdout activation runner

## Boundary

This boundary activates the live prospective collection lane frozen by merged PR #150.

It is still **research-only**. It does not authorize expected-goals production use, ScoreMatrix, probability inference or adjustment, pricing, market activation, bet selection, successor approval, or BET execution.

The immutable experiment start remains **`2026-08-19T00:00:00Z`**. Merging this runner later than that timestamp does not move the start and does not authorize backfilling any missed prospective observation.

## Reviewed ancestry

The runner fails closed against the exact merged implementation/control chain:

- PR #149 fresh-holdout core blob `5dabab12d5205d384fd3904cda0e68661ef90791`;
- PR #150 merge commit `50684a85cd528d491be812ed77d2c744855aba84`;
- PR #150 merge timestamp `2026-08-18T04:55:12Z`;
- PR #150 collection-control blob `60865e35a92e28bb0d4360223dea42b8933bb706`;
- reviewed FotMob live capture script blob `10b8858ab62f2708bd564d578a627c43718e5a12`;
- capture contract blob `ca2149395de868104666620173b55a880b10c729`;
- reviewed ordinary-FT adapter blob `868563206e09010fce74b4ba7954028930baad54`;
- PR119 materialization executor blob `2409676b4993a25024e2e8554e84e3525e7c5e6e`.

## Exact historical bootstrap

The feature-history ledger is always rooted in the exact reviewed PR119 projection:

- SHA-256 `e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2`;
- size `10,545,099` bytes;
- rows `21,326`.

The workflow first looks for the dedicated immutable bootstrap release asset:

`athena-fresh-holdout-bootstrap-v1 / pr119-materialized.ndjson`

If it does not yet exist, the workflow downloads the already-reviewed historical campaign artifact:

- source run `31887523012`;
- artifact ID `9249856559`;
- artifact name `fotmob-ordinary-ft-source-history-campaign-31887523012`;
- ZIP size `61,886,753`;
- ZIP SHA-256 `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`.

It then re-executes PR119 locally and accepts the materialized projection only if its exact frozen hash, size, and row count match. The projection is uploaded once as the bootstrap release asset. A partially created bootstrap release with a missing or wrong asset fails closed instead of silently regenerating a second authority.

## Schedule identity

The scheduled workflow uses two separate cron expressions:

- `7 * * * *`
- `37 * * * *`

This preserves the frozen 30-minute cadence while making the schedule event itself identify whether the nominal slot is `:07` or `:37`.

The workflow obtains the current Actions run `created_at` from GitHub and resolves the latest occurrence of the event's own nominal minute not later than that creation time. A nominal slot is control identity only.

The actual FotMob capture manifest `observed_at` remains the only observation time used by PR #149. A capture whose actual `observed_at` predates its nominal slot is rejected. A delayed capture remains delayed; it is never backdated to the cron slot.

There is no `workflow_dispatch` activation path in this boundary. That prevents a manual run from inventing a prospective slot.

## Scheduler gaps

The runner derives the slot lattice from the first active slot, `2026-08-19T00:07:00Z`, with exact 30-minute spacing.

If the last durable committed slot is older than the current nominal slot, the missing range is written to `control-journal.ndjson` with `backfill_authorized=false`.

A dropped or disabled scheduled run therefore becomes permanent missing prospective coverage. Later runs may resume future captures, but may not recreate the missed observation.

A duplicate run for an already committed nominal slot is idempotent and performs **zero network replay**.

## State restoration

Hosted Actions runners are ephemeral, so cache is never evidence authority.

Before each tick, the workflow restores the latest successful immutable evidence asset from releases whose tag begins:

`athena-fresh-holdout-evidence-`

Successful assets are named:

`success-YYYYMMDDTHHMMSSZ-run-<run_id>.tar.gz`

The lexicographically latest successful nominal timestamp is restored. The asset digest is checked before extraction, and extraction rejects absolute paths, traversal, symlinks, hard links, devices, or content outside the exact research state root.

The state root is:

`.cache/athena-research/fotmob-utc-native-xg-fresh-holdout`

The durable journals are the PR #150 names:

- `capture-index.ndjson`;
- `prediction-journal.ndjson`;
- `post-seal-identity-journal.ndjson`;
- `settlement-journal.ndjson`;
- `control-journal.ndjson`;
- `checkpoint.json`.

`checkpoint.json` is only a reconstructible pointer. The append-only journals remain authority.

## Long-lived evidence publication

Every successful tick is packaged into an immutable release asset. Evidence releases are split by ISO week so the asset count remains comfortably bounded:

`athena-fresh-holdout-evidence-YYYY-Www`

The bundle contains the cumulative journals/checkpoint plus a rolling four-capture raw working ring for each provider request date. Older raw captures may disappear from later working rings, but remain preserved in the earlier immutable tick asset in which they were current evidence.

The workflow verifies the uploaded release asset digest before declaring the tick durable.

A 90-day Actions artifact is also uploaded as a transport/failure fallback, but it is explicitly not the long-term evidence authority.

If the runner fails, the workflow attempts to publish a uniquely named `failure-...tar.gz` bundle and uploads the same material as a 90-day Actions artifact. Failure bundles are **never** selected for state restoration.

If durable success-asset upload or digest verification fails, the workflow fails. The next run restores the previous successful state and records the skipped nominal slot as a scheduler gap.

## Live capture order

For an open prediction population, every successful active tick executes exactly the PR #150 provider-date plan:

1. UTC yesterday;
2. UTC today;
3. UTC tomorrow.

During the selected-close settlement tail it requests only:

1. UTC yesterday;
2. UTC today.

Each request uses:

- `timezone=UTC`;
- `ccode3=NGA`;
- the reviewed unsigned transparent FotMob `data/matches` capture path.

Every request must succeed for the tick to commit. Partial live acquisition cannot become a successful state snapshot.

## Competition scope

The runner sends no hard-coded competition list to FotMob.

Every structurally qualified provider-native `primaryId` returned by the reviewed `data/matches` source remains eligible for fresh evaluation. This permits leagues, domestic cups, continental competitions, and international competitions when the provider returns them through the reviewed structure.

The 11 legacy IDs are only the history-mutation scope:

`{40,47,53,54,55,57,61,64,71,87,135}`.

A non-legacy fixture can be predicted and evaluated if its frozen inherited features are complete, but its settlement never mutates form/Elo/fatigue history.

## Within-tick ordering

A successful active tick is ordered deliberately:

1. restore and strictly revalidate durable journals;
2. reconstruct all sealed predictions;
3. revalidate or execute the required count-only close evaluation;
4. derive the exact PR #150 request-date plan;
5. journal any scheduler gap;
6. execute all required reviewed live captures;
7. qualify provider-native identities;
8. journal capture lineage;
9. append every new post-seal identity observation;
10. attempt settlements from the rolling raw capture ring;
11. append legacy settlement history updates;
12. only then construct new predictions from the current captures;
13. append same-tick post-seal observations later than a newly selected seal;
14. stage current raw captures into the rolling working ring;
15. commit the tick journal and reconstructible checkpoint.

Settlement is before prediction construction so a result already proven by source evidence available at this tick can enter the legacy history state before a later-kickoff prediction is built.

## Prediction semantics

For a fixture without a prior prediction disposition, the runner asks PR #149 to select from only the actually captured current observations.

The first actually observed capture inside the frozen 24-hour-to-60-minute window becomes the seal. If PR #149 reports missing reviewed form/fatigue, that missing-feature disposition is durably journaled and cannot later be replaced by a later capture.

No result, model metric, market state, or price can select a prediction capture.

## Post-seal identity semantics

Every newly qualified observation later than a seal is appended to the post-seal identity journal.

At settlement, the entire preserved observation sequence is supplied back to PR #149. Any observed fixture, `primaryId`, wrapper, team, or kickoff drift remains excluding even if a later provider response reverts to the original identity.

## Settlement semantics

For each unsettled seal, the runner searches the rolling raw ring for the latest two provider captures on the sealed UTC request date that:

- are both post-kickoff;
- both still contain the exact fixture through PR #149 qualification;
- are separated by at least the reviewed 300 seconds;
- have distinct raw and manifest lineages.

PR #149 then revalidates the prediction against the exact history ledger and re-runs the reviewed ordinary-FT adapter.

`EXCLUDED_NOT_REVIEWED_ORDINARY_FT` from a pair is not treated as final by the runner because a match may simply not yet be finished/stable. The fixture remains pending for later captures.

A provider-identity/kickoff-drift exclusion is terminal.

At the selected close, any already sealed prediction whose kickoff is on or after the right-exclusive close boundary is preserved but marked `EXCLUDED_OUTSIDE_SELECTED_CLOSE`; it is never settled into the scored population.

At the end of the fixed 24-hour settlement tail, any still unresolved in-population seal is marked `UNRESOLVED_AT_SETTLEMENT_TAIL`.

## Count-only close

Beginning at the +28-day boundary, the runner reconstructs the sealed-prediction population and reuses PR #150's token-protected close-control function.

An open state is revalidated at the latest required UTC midnight. A selected close receipt is revalidated on every later tick and is irreversible.

No goals, NLL, WACE, WSCE, or other performance value enters close selection.

## Safety

The live runner authorizes only the exact reviewed provider requests needed for the prospective research holdout.

All downstream ATHENA authority remains false:

- no production xG;
- no ScoreMatrix;
- no probability inference/adjustment;
- no calibration-for-production;
- no pricing;
- no market activation;
- no selection;
- no successor approval;
- no BET execution.

## Next boundary

`REVIEW_FRESH_HOLDOUT_COLLECTION_EVIDENCE_AND_CONFIRMATION_RESULT`

The later result-review boundary must reconstruct the selected population from durable evidence, run only the already frozen PR #148 confirmation mathematics, and remain review-required even if every statistical gate passes.
