# FotMob fresh-holdout zero-artifact bootstrap recovery

## Observed runtime evidence

The owner-triggered lineage audit on exact main
`ebff388a5d0014e5ed4016caf035de0f1342cab1` completed as Actions run
`32249717030` and reported `PARTIAL_UNVERIFIED_GITHUB_LINEAGE`: twenty
completed collection runs were visible but none exposed a verified canonical
state lineage.

The newest ordinary scheduled run `32248305061` failed before bootstrap or
provider acquisition because the newest completed predecessor,
`32236046186`, had no canonical state artifact.

Direct inspection of run `32236046186` proves the narrower failure:

- campaign-origin restore succeeded;
- nominal slot `2026-08-19T08:37:00.000000Z` was resolved;
- PR119 bootstrap materialization failed;
- the reviewed collection-tick step was skipped;
- staged-capture reconciliation was skipped;
- packaging then failed, leaving zero canonical state artifacts.

The bootstrap failure itself was the already-corrected pre-PR175 path that
looked for a derived NDJSON member not present in preserved PR119 artifact
`9249856559`. PR175 replaced that assumption with exact replay through the
reviewed PR119 materialization executor and also corrected the packaging
`tar_name` failure. Those fixes protect future runs but do not change the
historical fact that run `32236046186` has no artifact.

## Recovery rule

Campaign-origin recovery may therefore classify one additional exact
zero-artifact shape as proven pre-acquisition failure:

1. lineage restore completed successfully;
2. bootstrap materialization failed;
3. the reviewed collection tick was skipped;
4. staged-capture reconciliation was skipped.

The existing restore-failure/bootstrap-skipped shape remains admitted.
Anything else remains a hard stop. In particular, a successful bootstrap,
an entered collection tick, an entered reconciliation step, a successful
workflow run, unexpected artifacts, malformed job metadata, duplicate
reviewed steps, or a non-scheduled/non-main run cannot be reclassified.

This exception is still campaign-origin-only. It cannot fall back across a
proven zero-artifact failure to an older canonical campaign artifact.

## Prospective semantics

No missed nominal slot is replayed or reconstructed. When the next ordinary
scheduled run legitimately establishes Genesis, the existing collection
control records elapsed schedule opportunities as `SCHEDULER_GAP_RANGE`
with `backfill_authorized: false`. The failed `08:37` opportunity is therefore
prospective missingness, not an observation and not a backfilled tick.

This recovery performs no FotMob request and grants no model, production,
pricing, selection, or execution authority. The next boundary after merge is
to wait for the next ordinary scheduled `:07`/`:37` run and then re-run the
read-only lineage audit. The failed historical run must not be manually
rerun.

## Validation boundary

ATHENA Patch Bridge validates the exact patch against the synthetic pull-request
merge with all eight hosted test shards plus repository syntax before it may push
the implementation head. Normal pull-request CI remains the final merge gate on
the exact reviewed head; no repository-wide local pytest run is required.

<!-- identity-hardening implementation in progress -->
