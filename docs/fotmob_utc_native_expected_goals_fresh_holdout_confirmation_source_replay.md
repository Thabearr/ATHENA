# FotMob UTC-native xG fresh-holdout confirmation source replay

## Status

`IMPLEMENTED_OFFLINE_SOURCE_REPLAY_NOT_PRODUCTION_APPROVED`

This boundary connects the durable prospective collection evidence created by the reviewed PR151 runner to the frozen PR167 confirmation evaluator. It is intentionally offline and cannot acquire provider data, refit a model, change calibration, authorize pricing, choose a selection, or issue a BET.

The source-replay implementation is:

- `scripts/replay_fotmob_utc_native_xg_fresh_holdout_confirmation.py`

The frozen evaluator remains:

- `domain/fotmob_utc_native_expected_goals_fresh_holdout_confirmation_evaluator.py`

## Why this boundary exists

PR167 accepts exact reviewed Python objects. The prospective campaign, however, is persisted as cumulative durable state: append-only prediction, settlement, identity, capture, and control journals plus a checkpoint, packaged into a run-bound archive and committed by `fresh-holdout-tick-receipt.json`.

Those two representations must not be joined by an ad-hoc parser at review time. This source-replay boundary performs that translation under fail-closed rules and re-proves the frozen count-only close before fresh outcomes are evaluated.

## Required inputs

The replay accepts exactly two local files:

1. a canonical terminal **success** archive named `success-YYYYMMDDTHHMMSSZ-run-<RUN_ID>.tar.gz`; and
2. its canonical `fresh-holdout-tick-receipt.json` bytes, normally preserved long-term beside the archive by the PR168 release-receipt mirror.

No GitHub or provider network request is performed by this replay script.

## Verification chain

Before PR167 is invoked, replay requires all of the following:

1. **Frozen implementation identity**
   - PR151 activation-runner Git blob is exactly `901ab137d6601a3485eac30da7e6bad7eeefa397`.
   - PR167 evaluator Git blob is exactly `1f07292e66254ece0de25dc70e10964502a3839a`.
   - Both modules must independently revalidate their reviewed dependency chains and preserve every safety authority as false.

2. **Canonical final receipt**
   - compact sorted-key JSON with a trailing newline;
   - no duplicate JSON keys;
   - exact positive workflow run ID;
   - canonical success archive name bound to that run ID;
   - canonical release tag;
   - exact `:07` or `:37` UTC nominal slot matching the archive name;
   - `tick_exit_code == 0` and `tick_committed == true`.

3. **Archive commitment**
   - receipt SHA-256 equals the actual archive SHA-256;
   - receipt size equals the actual archive byte size;
   - the existing PR151 archive verifier rejects traversal, duplicate members, symlinks, devices, and unexpected roots;
   - extraction happens only into a temporary replay directory, never over the operator's live research state.

4. **Append-only journal replay**
   - every NDJSON journal row must remain canonical;
   - PR151's prediction-state parser must revalidate every sealed prediction hash and fixture identity;
   - missing-feature assessments are reconstructed explicitly rather than silently discarded;
   - PR151's settlement parser must revalidate every terminal disposition and settled prediction;
   - only PR167's exact terminal vocabulary is accepted.

5. **Frozen count-only close replay**
   - exactly one stored `COUNT_ONLY_CLOSE_EVALUATION` may carry `selected_close_utc`;
   - it must explicitly prove `outcome_or_performance_input_used == false`;
   - the selected close must be an exact UTC midnight;
   - `evaluate_close_control_state(...)` is rerun from the sealed prediction population;
   - decision, selected boundary, evaluated boundary, and coverage SHA-256 must exactly match the stored close row.

6. **Terminal cumulative state**
   - a committed tick must exist after the selected close's 24-hour settlement tail;
   - the latest committed tick must be `COLLECTION_COMPLETE`;
   - the final receipt's nominal slot, release tag, and archive name must equal the latest committed state;
   - checkpoint row counts must exactly equal the append-only capture, prediction, settlement, and control journals;
   - checkpoint runner ID, final phase, final slot, release tag, and archive name must match exactly.

Only after all six layers pass are reconstructed `FreshPredictionAssessment` and `TerminalSettlementRecord` objects handed to PR167.

## Result

The replay emits canonical JSON containing:

- exact source archive and receipt SHA-256/size;
- workflow run ID, nominal slot, release tag, and archive identity;
- selected close and evidence-derived evaluation time;
- source journal counts;
- the complete PR167 confirmation result;
- the PR167 canonical result SHA-256;
- all downstream safety/production authorities still false.

A passing PR167 result remains **review-required**. This boundary cannot automatically approve a successor model or enable any betting path.

## Missing and failed scheduled ticks

Scheduler gaps are evidence. They are not backfilled. The PR151 runner records `SCHEDULER_GAP_RANGE` with `backfill_authorized: false` when a nominal observation is missing from committed lineage. Source replay does not transform a gap into an observation and does not infer success merely because a cron occurrence should have happened.

Likewise, a `failure-...tar.gz` archive is not eligible for terminal confirmation evaluation. Failure archives may preserve genuine source observations for prospective lineage, but they cannot be promoted to a completed confirmation result.

## CLI

```bash
python scripts/replay_fotmob_utc_native_xg_fresh_holdout_confirmation.py \
  --archive /path/to/success-YYYYMMDDTHHMMSSZ-run-RUN_ID.tar.gz \
  --receipt /path/to/success-YYYYMMDDTHHMMSSZ-run-RUN_ID.tar.gz.receipt.json \
  --output /path/to/new-source-replay-result.json
```

`--output` is optional. If supplied, the path is no-overwrite: an existing path fails closed. Canonical result JSON is always printed to stdout on success.

## Explicit non-authorities

This PR does **not**:

- contact FotMob, SportyBet, Sportradar, or any other provider;
- repair or backfill missing scheduled observations;
- change the frozen home calibration;
- fit or refit any model;
- approve the xG successor automatically;
- establish bookmaker equivalence;
- map SportyBet markets or selections;
- prove fresh bookmaker price evidence;
- authorize pricing, selection, accumulator/slip construction, booking codes, execution, or BET.

## Next boundary

`REVIEW_SOURCE_REPLAYED_FRESH_HOLDOUT_CONFIRMATION_RESULT`

That review can happen only after the prospective campaign reaches a legitimate frozen close and terminal settlement state. Until then, the source-replay implementation may be tested synthetically but must not be represented as an executed fresh-holdout confirmation.
