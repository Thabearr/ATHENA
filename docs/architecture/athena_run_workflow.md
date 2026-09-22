# Canonical `athena-run` workflow

P4.2 adds `.github/workflows/athena-run.yml` as a second thin transport over the
existing `RunRequest -> AthenaRunService -> RunReceipt` path. It does not add a
decision engine, alter run-contract semantics, or retire any existing workflow.

## Event surface and defaults

The workflow has only two triggers: the daily schedule (`0 9 * * *`) and
`workflow_dispatch`. Dispatch accepts exactly `days`, `target_legs`,
`target_total_odds`, `bookie`, and `profile`; `mode`, authority, share-code intent,
and wager intent are derived by the shared P4.1 parser/service contracts.

The source-controlled schedule defaults and workflow-dispatch defaults are the same:
`days=today`, `target_legs=20`, no target-total-odds objective,
`bookie=sportybet`, and `profile=main`. Consequently the automatic schedule is MAIN /
`main_application`, currently fail-closed at the reviewed Phase 6 authority boundary,
with no provider acquisition, share-code generation, or wager authority. Manual
`profile=shadow` is supported for explicit operator intent but was not dispatched as
part of P4.2 review. The automatic schedule remains MAIN while
`current-shadow-all-market.yml` still owns the existing scheduled research run;
whether the canonical schedule later succeeds it is a P4.3 capability-migration
decision.

## Resolve once, execute exact lineage

`scripts.resolve_athena_run_workflow_request` sends either event through
`services.athena_run_workflow_request`, which delegates to the same
`parse_explicit_request` implementation as the CLI. Relative dates resolve once in
`Africa/Lagos`; canonical `RunRequest` bytes are persisted at
`artifacts/athena-run-workflow/resolved-run-request.json` before dependency setup or
Shadow restoration. The executor consumes those bytes and never reparses a relative
date token.

The workflow checks out `${{ github.sha }}` and verifies the exact `GITHUB_SHA`.
Execution is restricted to `refs/heads/main`, so a dispatch from another ref cannot
gain the reviewed SHADOW executor. The noninteractive transport
`scripts.execute_athena_run_workflow` validates the canonical request and delegates
to `AthenaRunService`; it does not run business logic itself.

## Shadow compatibility and operating envelope

Only a resolved SHADOW request restores the reviewed Current Shadow prerequisites:
the trusted-main durable-history prime artifact (with its established verified
live-transport fallback), fixed PR119 bootstrap, persistent identity state, and
current main-lineage SHA. The existing Current Shadow supervisor remains the owner of
its 75-minute timeout and timeout-receipt finalization. The GitHub job retains the
90-minute ceiling, leaving 15 minutes for receipt finalization, evidence preservation,
and artifact upload. P4.2 adds no competing service or shell timeout.

The workflow uses read-only `contents` and `actions` permissions, stable concurrency
groups, and `cancel-in-progress: false`; a manually requested SHADOW run shares the
existing `current-shadow-all-market` group. It always attempts to upload the resolved
request and run directory for 30 days. For SHADOW runs it also preserves the same
optional source-cache families and identity-state file when present.

There is no email or notification step in this core workflow. Notification capability
mapping remains `PENDING_P4_3_CAPABILITY_MAPPING`. The existing
`current-shadow-all-market.yml` and `current-sportybet-accumulator.yml` workflows
remain unchanged and enabled; P4.2 claims no workflow retirement. No wager authority
is granted.

## P4.3A workflow capability census

P4.3A adds an evidence-backed capability and run-history census for all 40
workflows present at the P4.2 merge base. No workflow was changed, disabled, renamed,
or retired, and no rollback tag was created. The canonical `athena-run` surface is
mapped, while Current Shadow remains active with its scheduled run, notification,
issue-comment, and identity/history-artifact responsibilities. The legacy
target-only SportyBet workflow is retained for owner review because the captured
GitHub history contains no run. Any later P4.3B retirement decision must be made
from the reviewed census; P4.3A does not claim the P4.3 retirement gate or broad
workflow consolidation.
