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

## Schedule identity and cron slot isolation

The scheduled workflow uses two separate cron expressions:

- `7 * * * *`
- `37 * * * *`

This preserves the frozen 30-minute cadence while making the schedule event itself identify whether the nominal slot is `:07` or `:37`.

The triggering expression (`github.event.schedule`) uniquely dictates the nominal minute:

- `7 * * * *` strictly evaluates nominal minute `7`;
- `37 * * * *` strictly evaluates nominal minute `37`.

A delayed `:07` event arriving after `:37` is never re-slotted to `:37`; it retains its `:07` identity. A delayed `:37` event arriving in the next hour is never re-slotted to `:07`. If transport delay causes a tick to be missed or dropped, it is treated as permanent coverage loss.

The workflow obtains the current Actions run `created_at` from GitHub and resolves the latest occurrence of the event's own nominal minute not later than that creation time. A nominal slot is control identity only.

The actual FotMob capture manifest `observed_at` remains the only observation time used by PR #149. A capture whose actual `observed_at` predates its nominal slot is rejected. A delayed capture remains delayed; it is never backdated to the cron slot.

There is no `workflow_dispatch` activation path in this boundary. That prevents a manual run from inventing a prospective slot.

## Scheduler gaps

The runner derives the slot lattice from the first active slot, `2026-08-19T00:07:00Z`, with exact 30-minute spacing.

If the last durable committed slot is older than the current nominal slot, the missing range is written to `control-journal.ndjson` with `backfill_authorized=false`.

A dropped or disabled scheduled run therefore becomes permanent missing prospective coverage. Later runs may resume future captures, but may not recreate the missed observation.

A duplicate run for an already committed nominal slot is idempotent and performs **zero network replay**.

## Authoritative state restoration & genesis control

Hosted Actions runners are ephemeral, so cache is never evidence authority.

Before each tick, the workflow resolves prior state with strict fail-closed genesis semantics:

1. **Genesis vs Restore Distinction**: Genesis (starting from empty state) is permitted ONLY when the workflow queries GitHub Actions runs and proves that zero prior successful workflow runs exist in the repository.
2. **Fail-Closed on Uncertainty**: If the GitHub API fails, returns malformed metadata, or permissions are insufficient, execution fails closed immediately. It NEVER falls back to empty state.
3. **Artifact-Backed Cryptographic Restore**: The primary restore authority is the immutable GitHub Actions artifact emitted by the latest successful run.
4. **Archive Member Safety**: Before extraction, every archive member is strictly verified:
   - no absolute paths;
   - no directory traversal (`..`);
   - no symlinks (`issym()`);
   - no hardlinks (`islnk()`);
   - no special devices, pipes, FIFOs (`ischr()`, `isblk()`, `isfifo()`, `isdev()`);
   - no duplicate archive entries;
   - all paths reside under the exact allowed root.
5. **State Invariant Verification**: After extraction, all append-only journals (`capture-index.ndjson`, `prediction-journal.ndjson`, `post-seal-identity-journal.ndjson`, `settlement-journal.ndjson`, `control-journal.ndjson`) and `checkpoint.json` are validated for canonical JSON structure, non-empty records, and pointer consistency.

The state root is:

`.cache/athena-research/fotmob-utc-native-xg-fresh-holdout`

`checkpoint.json` is only a reconstructible pointer. The append-only journals remain authority.

## Immediate raw capture staging & partial failure preservation

To satisfy ATHENA's evidence-preservation contract, raw live captures are staged and fsynced **immediately upon successful verification of each network response**:

1. Immediately after a request date response is verified against request parameters and `observed_at >= scheduled`, its exact `raw.json` and canonical `manifest.json` are written to `working-captures/<request_date>/<capture_id>/` and fsynced.
2. This occurs BEFORE the next network request, and BEFORE qualification, prediction, or settlement operations.
3. If a subsequent request or operation fails, the already-staged captures remain on disk and are archived into the `failure-...tar.gz` artifact.
4. A partial tick failure preserves all raw observations made before failure without classifying the failed nominal slot as a committed tick.

## Zero PyPI runtime dependencies

The entire activation runner execution path (runner, FotMob data/matches capture, PR119 bootstrap materialization, PR149 fresh-holdout core, and ordinary-FT adapter) is implemented strictly using the Python 3.12 standard library.

The scheduled collection workflow performs zero `pip install` commands and avoids unpinned PyPI dependencies.

## Long-lived evidence publication

Every successful tick is packaged into an archive and published:

1. **Authoritative 90-day Actions Artifact**: Uploaded as an immutable GitHub Actions artifact with `retention-days: 90`.
2. **Long-Lived Release Mirror**: Published to weekly ISO release tags (`athena-fresh-holdout-evidence-YYYY-Www`) without `--clobber`.

Failure bundles (`failure-...tar.gz`) are uploaded to 90-day Actions artifacts and release mirrors for auditing, but are never selected for state restoration.

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
6. execute reviewed live captures, staging each raw response immediately to disk and fsyncing;
7. qualify provider-native identities;
8. journal capture lineage;
9. append every new post-seal identity observation;
10. attempt settlements from the rolling raw capture ring;
11. append legacy settlement history updates;
12. only then construct new predictions from the current captures;
13. append same-tick post-seal observations later than a newly selected seal;
14. prune the rolling working ring to keep the latest 4 captures per date;
15. commit the tick journal and reconstructible checkpoint.

Settlement is before prediction construction so a result already proven by source evidence available at this tick can enter the legacy history state before a later-kickoff prediction is built.

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
