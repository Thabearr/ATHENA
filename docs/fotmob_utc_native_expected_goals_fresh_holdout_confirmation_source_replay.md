# FotMob UTC-native xG fresh-holdout confirmation durable-state replay

## Status

`IMPLEMENTED_OFFLINE_PR151_DURABLE_STATE_REPLAY_NOT_PRODUCTION_APPROVED`

This boundary connects the cumulative prospective state emitted by the reviewed PR151 scheduled runner to the frozen PR167 confirmation evaluator. It is intentionally offline and cannot acquire provider data, refit a model, change calibration, authorize pricing, choose a selection, or issue a BET.

Implementation:

- `scripts/replay_fotmob_utc_native_xg_fresh_holdout_confirmation.py`

Frozen evaluator:

- `domain/fotmob_utc_native_expected_goals_fresh_holdout_confirmation_evaluator.py`

## Exact source scope

The replay scope is deliberately precise:

`PR151_DURABLE_STATE_ARCHIVE_AND_CANONICAL_TICK_RECEIPT`

PR151 already seals prospective source observations, prediction assessments, post-seal identity observations, terminal settlements, control events, and checkpoint state into an append-only cumulative research state. PR169 revalidates and reconstructs that durable state.

PR169 does **not** claim to contact FotMob again or independently re-derive every provider raw response from the network. `provider_raw_capture_rederivation_performed` remains false in its result.

PR168 is the transport/durability layer that, while the Actions artifact still exists, independently binds the Actions ZIP to GitHub `artifact.digest`, checks archive↔receipt equality, checks the long-lived Release archive byte-for-byte, and mirrors the exact canonical receipt beside that archive. PR169 accepts the resulting exact local archive/receipt bytes as its offline input boundary; it does not make a second GitHub API assertion about how those local bytes were obtained.

## Why this boundary exists

PR167 accepts exact reviewed Python objects. The live campaign persists durable bytes. Joining those representations with an ad-hoc review-time parser would create an unaudited trust gap.

PR169 therefore reconstructs PR167 inputs only after the terminal PR151 archive and receipt re-prove the frozen collection semantics.

## Required input

The replay accepts exactly:

1. a terminal committed success archive named `success-YYYYMMDDTHHMMSSZ-run-<RUN_ID>.tar.gz`; and
2. the exact canonical tick-receipt bytes for that archive.

No GitHub or provider network request is performed by the replay script.

## Verification chain

Before PR167 is invoked, replay requires all of the following.

### 1. Frozen implementation identity

- PR151 activation-runner Git blob: `901ab137d6601a3485eac30da7e6bad7eeefa397`.
- PR167 evaluator Git blob: `1f07292e66254ece0de25dc70e10964502a3839a`.
- Both modules independently revalidate their reviewed dependency chains.
- Every downstream safety authority remains false.

### 2. Exact terminal PR151 receipt

The canonical compact sorted-key receipt must prove:

- `schema_version == 1`;
- exact PR151 `runner_id` and `runner_state`;
- `phase == COLLECTION_COMPLETE`;
- exact positive workflow run ID matching the archive name;
- `scheduled_for_utc == nominal_scheduled_for_utc`;
- exact UTC `:07` or `:37` slot;
- exact cron identity (`7 * * * *` or `37 * * * *`) matching that slot;
- canonical release tag and asset name;
- zero network requests and `network_acquisition_performed == false` for the final collection-complete tick;
- no claim that fresh collection started in that terminal tick;
- exact PR151 next-boundary value;
- exact safety-key vocabulary with every value false;
- `tick_exit_code == 0` and `tick_committed == true`.

Duplicate JSON keys, non-canonical formatting, wrong types, or semantic drift fail closed.

### 3. Archive commitment and safe extraction

- receipt SHA-256 equals the supplied archive SHA-256;
- receipt byte size equals the supplied archive byte size;
- the existing PR151 archive verifier rejects traversal, duplicate archive members, symlinks, devices, and unexpected roots;
- extraction occurs only into a temporary replay directory, never over an operator's live research state.

### 4. Capture and post-seal identity lineage replay

- every capture-index and post-seal identity row must remain canonical;
- PR151's post-seal identity parser is rerun, so duplicate `(fixture_id, capture_manifest_sha256)` identity keys and observation/row identity disagreement fail closed;
- every capture manifest SHA-256 must be valid and unique in the capture index;
- capture rows must preserve `schema_version == 1`, valid raw SHA-256/size, exact UTC `observed_at`, and `network_acquisition_performed == true`;
- a `preserved_from_uncommitted_tick` marker, when present, must remain exactly true;
- every post-seal identity observation must be anchored to a manifest SHA-256 present in the durable capture index;
- the identity observation's raw SHA-256 and `capture_observed_at` must equal that indexed capture;
- every post-seal identity observation must belong to a fixture that has an actual sealed prediction in the durable prediction journal.

These checks prevent a locally canonical but semantically forged identity journal or duplicated capture-manifest lineage from being accepted merely because the archive structure itself is valid.

### 5. Append-only prediction and settlement replay

- every NDJSON journal row must remain canonical;
- PR151's prediction-state parser revalidates every sealed prediction hash and fixture identity;
- missing-feature assessments are explicitly reconstructed instead of silently disappearing;
- PR151's settlement parser revalidates terminal identities and settled prediction payloads;
- every terminal settlement row must reference a fixture with a sealed prediction;
- every row-level `prediction_sha256` must equal the exact sealed prediction journal hash;
- any nested settled-prediction payload must bind back to the same sealed prediction;
- only PR167's exact terminal vocabulary is accepted.

### 6. Result-free close replay

- count-only close evaluations must remain strictly increasing in append order;
- duplicate or reordered close evaluations fail closed;
- exactly one close row may select a close;
- no later close evaluation may exist after that selected close;
- the selected boundary must equal the evaluated exact UTC midnight;
- the stored row must prove `outcome_or_performance_input_used == false`;
- `evaluate_close_control_state(...)` is rerun from the sealed prediction population;
- decision, boundary, and coverage SHA-256 must match exactly.

### 7. Terminal committed-lineage replay

The durable control vocabulary is limited to the reviewed runner/failure-lineage events: `COUNT_ONLY_CLOSE_EVALUATION`, `SCHEDULER_GAP_RANGE`, `TICK_COMMITTED`, and `UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED`. Unknown event types fail closed.

- committed `:07/:37` slots must be strictly increasing in journal order;
- duplicate or reordered committed slots fail closed rather than being sorted away;
- `committed_at_utc` may not predate its nominal slot;
- every `SCHEDULER_GAP_RANGE` must preserve `backfill_authorized == false`;
- an `UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED` row must preserve `tick_committed == false` and `backfill_authorized == false` and must bind its manifest/raw SHA-256/observed-at values to the indexed preserved capture;
- the final control-journal row must be the terminal `TICK_COMMITTED` row;
- that row must be `COLLECTION_COMPLETE` and at/after selected close + 24 hours;
- its nominal slot, committed-at time, release tag, and asset name must match the final receipt exactly.

### 8. Checkpoint reconstruction

The checkpoint must exactly equal the reconstructed append-only state for:

- runner ID;
- final nominal slot;
- `COLLECTION_COMPLETE` phase;
- capture-row count;
- sealed-prediction count;
- terminal-settlement count;
- control-event count;
- release tag;
- durable asset name.

Only after every layer passes are reconstructed `FreshPredictionAssessment` and `TerminalSettlementRecord` objects supplied to PR167.

## Output

The replay emits canonical JSON binding:

- the explicit durable-state source scope;
- archive and receipt SHA-256/size;
- workflow run ID, nominal slot, release tag, and asset identity;
- selected close and evidence-derived evaluation time;
- source-journal counts;
- the complete PR167 result;
- the canonical PR167 result SHA-256;
- `durable_state_journals_replayed == true`;
- `provider_raw_capture_rederivation_performed == false`;
- all downstream production/pricing/selection/BET authorities false.

Even an eventual PR167 all-pass signal remains **review-required**. PR169 cannot approve the successor automatically.

## Missing and failed scheduled ticks

Scheduler gaps are evidence, not data to repair. PR151 records `SCHEDULER_GAP_RANGE` with `backfill_authorized: false`; PR169 refuses any gap row that changes that authority and never converts a gap into an observation.

A `failure-...tar.gz` archive may preserve genuine prospective source observations through the failed-tick lineage, including capture-index rows marked `preserved_from_uncommitted_tick: true` and non-committed qualification-failure control evidence. Those rows remain auditable source evidence but do not commit the failed nominal tick. A failure archive itself is not eligible to become a terminal confirmation result: PR169 accepts only a final committed success archive after the settlement tail.

## CLI

```bash
python scripts/replay_fotmob_utc_native_xg_fresh_holdout_confirmation.py \
  --archive /path/to/success-YYYYMMDDTHHMMSSZ-run-RUN_ID.tar.gz \
  --receipt /path/to/success-YYYYMMDDTHHMMSSZ-run-RUN_ID.tar.gz.receipt.json \
  --output /path/to/new-durable-state-replay-result.json
```

`--output` is optional. If supplied, the destination is no-overwrite. Canonical result JSON is printed to stdout on success.

## Explicit non-authorities

PR169 does not:

- contact FotMob, SportyBet, Sportradar, or any provider;
- backfill or retrofill a missing schedule slot;
- fabricate a first-tick success from cron occurrence;
- independently claim current GitHub Actions metadata for local input bytes;
- change the frozen home calibration;
- fit or refit any model;
- approve the xG successor automatically;
- establish bookmaker equivalence;
- map SportyBet markets or selections;
- prove fresh bookmaker pricing;
- authorize pricing, selection, slip/ACCA construction, booking codes, execution, or BET.

## Next boundary

`REVIEW_SOURCE_REPLAYED_FRESH_HOLDOUT_CONFIRMATION_RESULT`

That review can occur only after the real campaign reaches a legitimate frozen close and terminal settlement state. Until then the replay implementation can be tested synthetically, but must not be represented as an executed fresh-holdout confirmation.
