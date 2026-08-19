# Fresh-holdout lineage audit fail-closed reporting

## Status

`CONTROL_WORKFLOW_OBSERVABILITY_ONLY_NOT_LINEAGE_AUTHORITY`

PR #171 hardens the owner-triggered PR #170 GitHub lineage audit after the first post-merge invocation exposed an operational presentation gap: when an authorized audit control workflow fails after the owner/main guard succeeds, the normal compact success-result comment is skipped. A client that cannot enumerate issue-comment-triggered Actions runs can therefore be left without the run ID needed to inspect the failure.

This boundary changes only that presentation failure mode. It does not change the PR #170 audit algorithm, the PR #151 collection runner, PR #168 Release durability, the prospective campaign state, or any football/model/betting semantics.

## Authorized failure comment

The existing exact three-line owner command and PR #170 binding remain unchanged. The guard now emits an internal `authorized=true` output only after it has proved:

- the comment is the exact reviewed command;
- the commenter is the repository owner;
- the command is bound to merged/closed PR #170;
- the requested lowercase SHA is exact current `main`.

If a later control-workflow step fails after that authorization, a final `failure()` step posts a compact comment to PR #170 with:

- `audit-state: AUDIT_CONTROL_WORKFLOW_FAILED_CLOSED`;
- the exact guard-observed `main` SHA;
- `lineage-result-authority: false`;
- `first-slot-status: NOT_DERIVED`;
- the exact audit Actions run ID;
- every downstream authority false.

The failure comment deliberately does **not** invent a scheduled collection run ID, collection head SHA, first-slot disposition, committed count, missing count, or any other campaign lineage result. The audit Actions run ID is an observability locator only.

## Failure remains failure

PR #171 does not use `continue-on-error` and does not turn a failed audit into a green workflow. The original failed step remains failed. The final comment only makes that failure inspectable through the PR conversation surface.

The successful path remains unchanged in meaning: only a successful read-only PR #170 audit may upload its canonical audit JSON and post the normal compact lineage result.

## No retry or repair

The hardening workflow has no Actions write permission and adds no rerun, retry, provider acquisition, Release repair, observation backfill, or evidence mutation. A failure comment is never permission to replay or reconstruct a missing prospective observation.

The failure-result comment also does not match the owner trigger command and therefore cannot self-authorize another audit.

## Safety

This boundary grants no authority for:

- FotMob, SportyBet, or Sportradar network acquisition;
- retrospective or prospective observation backfill;
- model approval or production promotion;
- bookmaker equivalence;
- fresh-price claims;
- pricing/value integration;
- selection;
- slip/ACCA construction;
- booking-code generation;
- execution;
- `BET`.

## Next boundary

`RETRIGGER_AND_REVIEW_EXPLICIT_FRESH_HOLDOUT_LINEAGE_AUDIT_RESULT`

After merge, post the exact PR #170 owner audit command again against the then-current `main`. A successful audit may produce the normal verified/partial/no-evidence result. A failed control workflow must now expose its audit Actions run ID and remain explicitly non-authoritative so the underlying job can be inspected without guessing.
