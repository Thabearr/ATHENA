# Fresh-holdout campaign-origin pre-acquisition recovery

## Status

`RESEARCH_ONLY_FAIL_CLOSED_CAMPAIGN_ORIGIN_RECOVERY`

This boundary responds to the first successful owner-triggered Actions-lineage audit after PR #173. The audit ran read-only against merged `main` and reported `PARTIAL_UNVERIFIED_GITHUB_LINEAGE`: the first nominal slot remained unresolved and 12 completed collection-workflow runs were present but none exposed a canonical unexpired state artifact.

Inspection of the collection Actions jobs established a common control-plane failure. The restore step failed before the bootstrap, reviewed collection tick, and staged-capture reconciliation steps could execute. Because schedule-slot resolution never completed, the packaging step correctly refused to fabricate an archive identity, so no canonical failure artifact was uploaded. Each later run then treated the previous no-artifact failure as its newest predecessor and failed at the same restore boundary.

The chain was already poisoned by a completed run created before the prospective holdout start. The first observed post-start run therefore inherited a pre-campaign no-artifact predecessor rather than a valid prospective state artifact.

## Recovery rule

PR #174 does not authorize skipping arbitrary failed runs. A zero-artifact completed run may be excluded from campaign-origin predecessor selection only when all of the following are true:

- its authoritative `created_at` is on or after the reviewed holdout start;
- its event is `schedule` on `main`;
- its conclusion is exactly `failure`;
- the run exposes zero Actions artifacts of any kind;
- GitHub job metadata exposes exactly one job named `execute fresh holdout tick`;
- the restore step is completed/failure;
- the bootstrap step is completed/skipped;
- the reviewed collection-tick step is completed/skipped;
- the staged-capture reconciliation step is completed/skipped.

The GitHub jobs query is read-only and uses the `GH_TOKEN` and `GITHUB_REPOSITORY` environment already present in the reviewed restore step. No workflow permission is broadened and the collection workflow blob is unchanged.

A pre-campaign completed run with authoritative `created_at` before the holdout start is not a campaign predecessor.

## What remains a hard stop

The recovery fails closed if a run has any artifact, if collection execution was entered, if the job/step proof is incomplete or duplicated, if the run is not a scheduled `main` failure, or if a canonical campaign artifact is encountered behind one of the skipped failures.

That last rule is deliberate. A canonical failure artifact may contain a real staged source observation. PR #174 never falls back across one and never converts a failed run into success.

Campaign-origin recovery is also refused if the 100-run Actions query window is saturated without reaching any pre-campaign completed run. That prevents an unproven truncated history from being declared Genesis.

## Missing slots remain missing

When every completed in-campaign run is mechanically proven to have failed before acquisition and no admissible campaign predecessor exists, the next scheduled run may establish a clean campaign Genesis. It does not reconstruct any earlier observation.

The existing activation runner then derives only the current nominal `:07` or `:37` slot from the current GitHub schedule trigger. Before any current capture is committed, its existing `SCHEDULER_GAP_RANGE` logic records every elapsed reviewed slot from `2026-08-19T00:07:00Z` through the slot immediately before the current run as missing with `backfill_authorized: false`.

No nominal schedule timestamp is substituted for a provider observation timestamp. No missed capture is regenerated. No retrospective provider request is authorized.

## Safety

This boundary grants no authority for:

- retrospective or prospective observation backfill;
- fabricated FotMob observations;
- SportyBet or Sportradar acquisition;
- model approval or production promotion;
- bookmaker equivalence or pricing;
- selection, slip construction, booking-code generation, execution, or `BET`.

## Next boundary

`MERGE_THEN_WAIT_FOR_NEXT_SCHEDULED_RUN_AND_REAUDIT_LINEAGE`

After merge, do not manually replay a missed nominal slot. Allow the next ordinary scheduled collection run to execute. Then trigger the read-only audit through control issue #172 and inspect the canonical Actions/Release evidence. A successful current tick may prove prior elapsed slots durably missing; it cannot make them observed.
