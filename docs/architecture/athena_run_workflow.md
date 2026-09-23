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
At the P4.2 checkpoint, `current-shadow-all-market.yml` and
`current-sportybet-accumulator.yml` remained unchanged and enabled; P4.2 claimed
no workflow retirement. No wager authority was granted.

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

## P4.3C spent V1 evidence-workflow retirement

The immutable P4.3A census records 40 workflows. P4.3B records the separate
40→39 owner-reviewed Current SportyBet retirement. P4.3C retires exactly two
spent V1 evidence predecessors, reducing the live set from 39 to 37. The V1
workflows had no successful run; their run/artifact failures are explicitly
reconciled by the corresponding V2 workflows, whose successful run identities
are bound in the P4.3C receipt. Neither V1 success nor byte-equivalence is claimed.

The exact V1 YAML bytes remain as non-executable historical fixtures. V1 tests
read those fixtures; the unchanged V2 tests continue to cover the live V2 paths.
The cumulative retirement ledger, not the older phase-specific audits, owns
current workflow-set accounting. Current Shadow remains active and unretired,
Fresh Holdout remains protected, and `athena-draft-ready-bridge.yml` remains
pending owner review. P4.3C does not claim Architecture Checkpoint E complete.
P4.4 is not started.

## P4.3B one-workflow retirement

P4.3A remains the immutable 40-workflow pre-retirement census. P4.3B separately
owner-reviewed the no-run target-only Current SportyBet workflow and proved its
MAIN fail-closed request capability against `athena-run` offline for targets 1,
20, and 50. The supported hosted mapping is `target_size=N` to `days=today`,
`target_legs=N`, `target_total_odds=null`, `bookie=sportybet`, `profile=main`.
The old YAML is retired; its exact bytes remain only at
`tests/fixtures/architecture/retired_workflows/current-sportybet-accumulator.yml`.
The target-only Python request and execution compatibility modules remain.
The canonical artifact name differs, but the underlying target-only result is
persisted inside the canonical run directory and uploaded by `athena-run`.
The old 15-minute and canonical 90-minute job ceilings are control-plane
differences, not a claim of equal timeout semantics. Neither MAIN path gains
provider, share-code, or wager authority.

Current Shadow remains active and unretired with its scheduled, notification,
identity-ancestry, and issue-comment responsibilities. Fresh Holdout workflows
remain protected. P4.3B retires no other workflow, makes no broad workflow
consolidation claim, and does not start P4.4.

## P4.3D retirement-audit checkpoint

P4.3D freezes the exact P4.3C cumulative-ledger state as an immutable phase snapshot
and changes historical audits to distinguish that snapshot from the extendable
current ledger. P4.3A continues to describe 40 historical workflows; current
accounting is 37 live and 3 retired. P4.3D changes no workflow YAML and retires
nothing. Later ledger extensions must preserve all earlier retirement metadata and
arithmetic; this does not pre-authorize any next retirement. Current Shadow remains
active, Fresh Holdout remains protected, Architecture Checkpoint E is not fully
claimed, and P4.4 has not started. If this PR merges, the source-review counter is
5/5 and a mandatory source reread is required before any further remediation.

## P4.4A workflow-evolution boundary

After the mandatory 5/5 source reread, P4.4A establishes a reviewed evolution
ledger for canonical workflow paths added after the frozen P4.3D checkpoint. The
P4.3A census and P4.3 retirement evidence remain immutable. Current-tree checks
derive from those historical identities plus explicit, evidence-bound evolution
transitions. The initial ledger has none: all 37 live workflow YAMLs remain
byte-identical, the three reviewed retirements remain recorded, and
`athena-ingest.yml` is absent. A future P4.4B PR must provide a reviewed ADD
transition before that path can exist. Current Shadow, provider diagnostics, and
Fresh Holdout are untouched. The zero-transition P4.4A ledger is also preserved as
an immutable phase snapshot; its receipt binds that snapshot separately from the
then-current ledger path. Later current P4.3 retirement state may extend the frozen
P4.3D checkpoint through separate review, and later evolution transitions must each
bind their own immutable cumulative snapshot. A prior transition receipt's backlink
must match its exact phase snapshot, not merely have a valid-looking hash. P4.4 and
Architecture Checkpoint E are not complete.

## P4.4A1 retained-workflow maintenance authority

P4.3A remains immutable historical evidence, and the P4.3 retirement ledger owns
removal of baseline paths. Ordinary evolution REVISE and RETIRE remain limited to
paths introduced by reviewed ADD transitions. P4.4A1 adds the narrowly scoped
MAINTENANCE_REVISE operation for a live retained P4.3A survivor; it preserves the
workflow path and count, the P4.3A successor-family label, and all trigger,
permission, concurrency, provider, model, pricing, selection, betting, and
retirement authority boundaries.

Each revision binds its exact before/after identities and preserves the immediately
preceding bytes in a unique source-controlled fixture under
tests/fixtures/architecture/revised_workflows/. The fixed maintenance contract
prohibits authority changes. P4.3A historical identity is resolved from the first
maintenance fixture, independently from the current workflow identity derived from
reviewed transitions, including in a shallow checkout.

P4.4A1 changes no real workflow YAML and adds no transition. It authorizes no
Fresh-Holdout repair by itself; the release-visibility race hotfix remains a
separate next step. P4.4B is not started, and P4.4 and Architecture Checkpoint E
remain incomplete.
