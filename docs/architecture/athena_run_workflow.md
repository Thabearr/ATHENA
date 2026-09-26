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

## P4.4H Current Shadow migration review

P4.4H is an offline migration review, not a caller migration. The live
`current-shadow-all-market.yml` workflow remains unchanged and owns the daily 09:00
UTC SHADOW schedule, manual request surface, and `/athena-shadow` issue-comment
compatibility. `athena-run` SHADOW dispatch already delegates to the reviewed
Current Shadow supervisor through `AthenaRunService` and the canonical
`RunRequest -> RunReceipt` boundary; sharing that executor alone is not a claim of
full workflow equivalence.

The scheduled requests are not yet equivalent: Current Shadow's schedule resolves
SHADOW, while the canonical schedule defaults to MAIN. Explicit date requests can
be represented when both policies see the same horizon, but Current Shadow's
calendar horizon is UTC and the canonical parser resolves relative dates in
`Africa/Lagos`. A seven-day explicit request is representable with preserved dates
at 22:59 UTC, but at 23:00 UTC the legacy window `20260924..20260930` and canonical
Lagos window `20260925..20261001` are mutually out of range; the mapping is
unrepresentable with the current canonical request surface. No date is shifted to
force a match. The old identity-state artifact ancestry and optional post-core email
also remain migration blockers. Issue-comment grammar remains explicit and retained;
P4.4H neither removes the trigger nor migrates its caller.

No Current Shadow run, provider request, workflow dispatch, or email/share-code
operation is performed by this review. Live canonical SHADOW successor proof
requires separate owner authorization. No caller migration or workflow retirement
is authorized; P4.4 and Architecture Checkpoint E remain incomplete. PR #399 closed
the previous source-review cycle at 5/5, and its mandatory architecture/source
reread was completed after that merge. The new cycle reset to 0/5: P4.4H is 0/5
while unmerged and would become 1/5 if merged. No new mandatory reread is due at
1/5; the next mandatory reread is due only when this cycle reaches 5/5.

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

## P4.4B ingest boundary

P4.4B adds a separate, manual-only `athena-ingest.yml` workflow for FotMob source
capture and offline replay. It adds one reviewed evolution transition and raises the
live workflow count to 38. `athena-run.yml`, Current Shadow, and protected Fresh
Holdout retain their existing authority and workflow bytes. Ingest has no routing,
share-code, or wagering authority. Scheduled ingest and legacy capability migration
remain for P4.4C review; P4.4 and Architecture Checkpoint E remain incomplete.

## P4.4I Current Shadow supervisor failure evidence

Canonical SHADOW run `36111105935` (`workflow_dispatch`, attempt 1) ran at exact
main `0066720de62611a3673468597335c3a2c55aacaf` for `2026-09-25`, target 20.
Its canonical request SHA-256 was
`af5b8c5de987f4dacd286f734dd57be7f17b7d0091d743e373c63683cfa1e69e`; artifact
10853141346 (`athena-run-36111105935`) had ZIP SHA-256
`2976c375787297c0759eb545e9d68706649d731b6b99fa26531f2baaab3b54d1`. The
canonical RunReceipt SHA-256 was
`4b65f9b8e9e927e6261dac48ee71557ba7645e96eccff24682dcaa15f53dbec3`, and the
inner Current Shadow receipt SHA-256 was
`63c9f0637ef5a1fa87545127577942902369e6b680eafdbcb3cd3ba965c21efe`.

GitHub reported control-plane `success`, but the canonical business status was
`RESEARCH_NO_CODE_SOURCE_INCOMPLETE`: zero selected legs, shortfall 20, no share
code, and `wager_placed=false`. The adapter recorded
`supervisor_returncode=1`; the child left the provisional startup reason
`SOURCE_CHAIN_PENDING:STARTED`, so the exact child exception is UNKNOWN and is not
inferred here. Only `CURRENT_FOTMOB_SOURCE` was checkpointed. This run therefore
did not complete the live canonical SHADOW successor proof; that blocker remains
OPEN.

The single live authorization was consumed by that run. Retry count is zero, no
retry is authorized, and the P4.4I correction is offline evidence-integrity work
only. It makes a nonzero supervisor exit fail closed as `SOURCE_INCOMPLETE`,
preserves only bounded stdout/stderr tails and structurally validated checkpoint
metadata, and rejects the exact startup-only marker as a terminal result even if
the supervisor exits zero. It does not change football/source behavior, add a
timeout, dispatch a workflow, or acquire provider data. P4.4I does not complete
the live successor proof, migrate callers, authorize retirement, or complete P4.4
or Architecture Checkpoint E.

## P4.4J explicit-date Current Shadow issuer network-control seam

Canonical SHADOW run `36119049997` ran once at exact main
`301f5d13ca8f60392c52d8ff132e8740b9b979bb` for `2026-09-25`, target 20. The
canonical request SHA-256 was
`af5b8c5de987f4dacd286f734dd57be7f17b7d0091d743e373c63683cfa1e69e`; artifact
10856121902 (`athena-run-36119049997`) had ZIP SHA-256
`d3cfc66ad2786304c2ca0c18f86d02c9a2597901a8d25c3ce5999fb0b30329a3`. Its
canonical receipt SHA-256 was
`918678993d2f08df3779e3ebf103e7acfa1c3ff8bd118e9306f6c4c7382db8e9`, and the
inner Current Shadow receipt SHA-256 was
`6e78b117cf95b5aee2ea121dd203d68d41c7c70a1c6899135cef308228c37c02`.

GitHub reported control-plane `success`, while the business result was
`SOURCE_INCOMPLETE`, with zero selected legs, shortfall 20, no share-code result,
and `wager_placed=false`. P4.4I's evidence-preservation guard correctly recorded
`supervisor_returncode=1`, rejected the provisional terminal receipt, and
preserved the bounded failure text. The exact source failure was
`TypeError: _selected_source_issuer.<locals>.issue() got an unexpected keyword
argument 'execute_live_network'`. This identifies a call-signature/network-control
passthrough mismatch in the explicit-date compatibility issuer; it is not evidence
of a provider-data, fixture, football-model, SportyBet, Router, or Portfolio
failure.

P4.4J corrects that seam offline: the selected-date issuer accepts the runner's
`execute_live_network` keyword, forwards its exact value, and retains the
reviewed default of `true`. Explicit UTC date validation/order/horizon, exact
`STATUS_NO_FIXTURES` skip behavior, other exception propagation, and unconditional
temporary issuer restoration remain unchanged. P4.4J does not perform a provider
request, workflow dispatch, or live proof; it does not change workflow YAML,
caller ownership, timeout, or authority. The single live authorization was
consumed by run `36119049997`; retries are zero and no retry is authorized. The
live canonical SHADOW successor blocker remains OPEN and requires separate owner
authorization for any future proof. P4.4, Architecture Checkpoint E, caller
migration, and workflow retirement remain incomplete/unauthorized.

## P4.4M canonical Shadow source-evidence preservation

Canonical SHADOW run `36229731847` exposed an artifact evidence gap: the active
pcUpcoming runtime evidence root existed during execution but was omitted from
the workflow's optional source-evidence preservation list. P4.4M adds that
active root to the existing copy loop so its manifest and raw pages are retained
in canonical artifacts when present, including after a business failure reaches
the preservation step. This is evidence preservation only; no source parsing,
fixture identity, or team-label semantics change. No live proof or retry was run,
and the successor proof remains incomplete. The team-label source-schema blocker
remains open. Caller migration and workflow retirement remain unauthorized.
