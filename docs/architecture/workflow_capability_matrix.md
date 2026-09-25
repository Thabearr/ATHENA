# P4.3A workflow capability and run-history census

P4.3 was split after the proposed target-only workflow was checked against live
GitHub history. `.github/workflows/current-sportybet-accumulator.yml` has no successful
run and no latest run. The architecture rule requires owner review when a workflow has
no successful history, so capability mapping is evidence-only in P4.3A; it does not
authorize a deletion based on apparent overlap with `athena-run`.

## Snapshot scope and method

The matrix at `artifacts/architecture/p4_3_workflow_capability_matrix_v1.json` binds
the 40 workflow YAML blobs at main commit
`475f1dcd825cd2ad32c9b9946b4a7ca24817433f`. Its offline fields are derived from
those exact tracked YAML blobs and repository references. Its run-history fields were
captured read-only with two GitHub CLI `gh run list` queries per workflow: latest
successful, and latest regardless of conclusion. An API/CLI error aborts capture; it
is never translated into “no run.” `scripts.capture_p4_3_workflow_capability_matrix`
has explicit read-only `--capture`, offline `--refresh-static` (which preserves the
captured history while rebuilding source metadata from pinned base blobs), and
`--check-static` modes; normal tests use only the offline audit.

At capture, 35 workflows had a successful run, two had no run history, and three had
run history but no successful run. All five are in the explicit owner-review queue.

The snapshot distinguishes successful history, a latest run without any successful
run, and no run history. Both no-success categories require owner review and are never
treated as deletion eligibility. The owner-review queue is included at the matrix
top level. `successor_family` is a classification destination and
`successor_workflow_path` is a mapping hint; neither establishes capability
equivalence. Every P4.3A row has `capability_mapping.equivalence_claimed=false`,
including canonical, future, protected, and pending-audit rows. Only a later
owner-reviewed retirement proof can establish equivalence for a specific candidate
across its inputs, outputs, artifacts, and fail-closed behavior.

## Retention decisions recorded

- `athena-run.yml` is the canonical run surface; `tests.yml` remains the canonical
  hosted test gate.
- `current-shadow-all-market.yml` remains active and is not retirement-eligible. Its
  blockers include unmigrated scheduled SHADOW ownership, notification/email,
  identity/history artifact ancestry, lack of live canonical SHADOW successor proof,
  and unresolved issue-comment compatibility.
- At the P4.3A capture, `current-sportybet-accumulator.yml` was mapped to the
  canonical MAIN request shape (`target_size` → `target_legs`, `days=today`, no
  total-odds objective, `bookie=sportybet`, `profile=main`) and was owner-review-
  required because no run history existed. P4.3B later performed that owner review
  and retired the YAML; the local compatibility command/code remains.
- The four Fresh Holdout collection, liveness, continuity, and release-receipt
  workflows remain protected research capabilities. P4.3A creates no backfill or
  reconstruction authority.
- Date-specific Saturday/campaign workflows are marked as date-hardcoded evidence or
  one-off surfaces, not as supported current runtime roots. The matrix's supported
  date-hardcoded list is explicit.
- Artifact and workflow-history references are recorded separately from documentation
  and test references so a mention is not mistaken for an executing consumer.

## Scope and next review

No workflow was edited, disabled, renamed, or deleted. No rollback tag was needed or
created. P4.3A does not claim workflow-count reduction, the P4.3 retirement exit gate,
or Architecture Checkpoint E completion. The complete matrix and history snapshot are
the evidence base for P4.3B, where an owner must select any retirement target from
reviewed evidence. Current Shadow is intentionally retained pending its capability
migration. P4.4 remains not started.

## P4.3B retirement delta

The P4.3A matrix and receipt remain byte-identical historical evidence of all
40 workflows before retirement. P4.3B owner-reviewed the no-run Current
SportyBet target-only workflow and proved, independently of the P4.3A mapping
hint, that `athena-run` preserves its bounded MAIN request and Phase-6
fail-closed outcome. Targets 1, 20, and 50, invalid bounds, the underlying
request payload, and the durable canonical artifact path are covered by an
offline proof. The live YAML is retired as the sole deletion, leaving 39 live
workflows; its exact bytes are preserved in a non-executable historical
fixture. The P4.2 historical audit now verifies that fixture rather than
requiring the deleted path to remain live.

This delta does not retroactively change any P4.3A
`equivalence_claimed=false` value. Current Shadow remains active with its
unmigrated responsibilities; Fresh Holdout workflows remain protected. No
other retirement or Architecture Checkpoint E completion is claimed. P4.4
has not started.

## P4.3C spent V1 evidence-workflow retirement

P4.3C retires exactly the spent V1 predecessor workflows for Feature Qualification
and the PR69 time-basis evidence campaign. Both had run history but no successful
run, so the owner reviewed these two paths specifically. The Feature V2 workflow
binds the V1 guard/permission failure, reconciliation comment, run and artifact
identity, and the explicit `V1_SPENT_GUARD_PERMISSION_FAILURE_NO_QUALIFICATION_EXECUTED_DO_NOT_REPLAY`
state. PR69 V2 binds its V1 run/artifact digest and the PR #128 / PR #129
reconciliation; the V1 campaign itself remained unqualified. Each V2 has its own
successful run and remains live and unchanged.

The two original YAML byte streams are retained as non-executable fixtures under
`tests/fixtures/architecture/retired_workflows/`; V1 contract tests now inspect those
fixtures, while V2 tests continue to inspect live workflows. The cumulative
`p4_3_workflow_retirement_ledger_v1.json` owns present-day tree accounting: it records
the P4.3B retirement plus these two P4.3C retirements and proves the 40-row P4.3A
baseline minus exactly three reviewed paths equals the 37 live workflows. Historical
P4.3A and P4.3B receipts remain immutable and keep their original 40-row and 40→39
claims, respectively. The ledger binds the P4.3C receipt body hash; that receipt
binds the final ledger hash, avoiding a circular self-reference.

Current Shadow remains active and unretired, all four Fresh Holdout workflows remain
protected, `athena-draft-ready-bridge.yml` remains pending owner review, and no broad
retirement or Architecture Checkpoint E completion is claimed. P4.4 has not started.

## P4.3D historical-audit extensibility

P4.3A remains the immutable 40-workflow census; P4.3B remains the immutable 40→39
retirement proof; and P4.3C remains the immutable 39→37 proof. The exact cumulative
ledger state used by P4.3C is frozen at
`artifacts/architecture/p4_3_retirement_ledger_snapshots/p4_3c_workflow_retirement_ledger_v1.json`.
P4.3C's ledger hash identifies that phase snapshot, not every future version of the
current cumulative ledger. The current ledger may only be extended by later reviewed
retirement evidence that preserves every existing entry and count invariant.

P4.3D retires zero workflows: the live set remains 37 and the cumulative retired set
remains 3. P4.3A derives its present-day tree check from the validated ledger while
retaining all 40 historical rows. P4.3C is verified as frozen historical evidence
against its phase snapshot rather than rebuilt from today's tree. Current Shadow
remains active, Fresh Holdout remains protected, and this audit-lifecycle fix does
not authorize a future retirement target. Architecture Checkpoint E is not fully
claimed; P4.4 has not started. If P4.3D merges, the source-review counter reaches
5/5 and the mandatory architecture/source reread must happen before further
remediation.

## P4.4A1 retained-workflow maintenance authority

P4.3A remains immutable historical evidence, and the P4.3 retirement ledger remains
the authority for removing its baseline paths. Ordinary evolution REVISE and
RETIRE remain limited to paths introduced by a reviewed ADD. P4.4A1 adds only
MAINTENANCE_REVISE: a path-preserving, zero-count-delta revision of a live,
non-retired P4.3A survivor. It must retain that row's original successor-family
classification and cannot grant trigger, permission, concurrency, provider,
model, pricing, selection, betting, or retirement authority.

Every maintenance revision binds the exact identity immediately before the change,
an exact source-controlled historical-before fixture, a fixed no-authority-change
contract, and its reviewed transition receipt/checkpoint. Each revision has its own
immutable fixture; chained revisions must use the immediately prior reviewed
identity. P4.3A historical bytes are independently resolved from the first
maintenance fixture, while current workflow bytes are checked against the
transition-derived identity. This also works when the original P4.3A commit is
unavailable in a shallow checkout.

P4.4A1 itself changes no workflow YAML and records zero real transitions. The
Fresh-Holdout release-visibility race hotfix is a later, separately reviewed step
and is not implemented here. P4.4B has not started; Architecture Checkpoint E and
P4.4 remain incomplete.

## P4.4B canonical ingest ADD

The frozen P4.3A census still has 40 historical rows. P4.4B appends one reviewed
`ATHENA_INGEST` ADD transition for `.github/workflows/athena-ingest.yml` after the
two Fresh-Holdout maintenance revisions. The current live workflow set grows from
37 to 38; the P4.3 retirement ledger remains at three reviewed retirements. No
baseline workflow changes or retires. The new workflow is manual only and its
immutable phase snapshot and receipt bind the exact new source identity. Provider
diagnostics and earlier ingest-like workflows remain live without successor
equivalence claims. P4.4C schedule and migration review has not begun; Checkpoint E
and P4.4 remain incomplete.

## P4.4A reviewed workflow evolution

The P4.3A 40-workflow census is historical evidence, not a permanent allowlist for
new canonical workflows. Current workflow-tree authority now composes the frozen
P4.3A source identities, the three reviewed P4.3 retirements, and the ordered
transitions in `p4_workflow_evolution_ledger_v1.json`. P4.4A commits that ledger
with zero transitions: 37 workflows remain live, the P4.3 retirement ledger is
unchanged, and no workflow YAML is added, revised, or retired.

A later ADD must name a previously absent path and exact source/blob identities,
phase, canonical family, and a source-controlled evidence receipt. REVISE and RETIRE
are confined to paths introduced by an earlier ADD in this ledger; frozen P4.3A
survivors cannot be changed through it. P4.4A freezes its zero-transition state at
`artifacts/architecture/p4_workflow_evolution_snapshots/p4_4a_workflow_evolution_ledger_v1.json`;
the P4.4A receipt binds that immutable snapshot path/hash and separately records the
mutable current-ledger path/hash as observed at its checkpoint. Future reviewed P4.3
retirements may extend the current retirement ledger while preserving the immutable
P4.3D checkpoint; they do not rewrite P4.4A history.

Each future evolution transition must name a source-controlled immutable cumulative
phase snapshot. Its receipt's `workflow_evolution_ledger_sha256` must equal that exact
snapshot's canonical SHA, and the snapshot must contain the exact transition prefix
through that phase. The transition binds the receipt evidence-body hash, excluding
only its final ledger backlink and self-hash; the snapshot records the transition
intent and evidence-body hash. This avoids a hash cycle while keeping older receipt
backlinks verifiable after later appends. An unrecorded `athena-ingest.yml` is
rejected. P4.4B is the separate implementation step; this PR creates no ingest
workflow and performs no acquisition. Legacy and provider-diagnostic workflows,
Current Shadow, and protected Fresh Holdout remain untouched. Architecture
Checkpoint E and P4.4 are incomplete.

## P4.4C scheduled ingest activation and capability migration review

P4.4B introduced the canonical FotMob ingest as manual-only. P4.4C revises that
existing workflow to add exactly one daily schedule, `0 8 * * *` UTC, while
preserving `workflow_dispatch`. A scheduled request resolves from an aware UTC clock
to exactly the current Gregorian date; it does not catch up or backfill. Manual
dispatch keeps its existing 1–7 strictly increasing exact-date contract. Provider
scope (FotMob), UTC/NGA, no-retry behavior, 900-second service budget, and 20-minute
job timeout remain unchanged. The new automatic acquisition is inactive on main
while this PR is open; implementation and review validation make zero provider
requests.

P4.4C reviewed exactly the five frozen P4.3A `ATHENA_INGEST_FUTURE` workflows.
`build-historical-warehouse.yml` remains the distinct multi-source historical
warehouse; `execute-fotmob-ordinary-ft-source-history-campaign.yml` remains an
owner-controlled source-history campaign; `execute-fotmob-prospective-player-context-campaign.yml`
remains the player-context research and continuation capability;
`issue-current-fotmob-reviewed-source.yml` remains pending an exact compatibility
adapter for its configurable request and fixture-bootstrap outputs; and
`prepare-canonical-drive-transfer.yml` remains the historical archive transfer
capability. Current source identities and read-only Actions history are bound in the
migration-review artifact. Its run-history objects mean latest observed at the
explicit `2026-09-24T01:53:50Z` capture cutoff, not a live pointer; later runs do not
rewrite or invalidate that snapshot. All five remain non-equivalent and not retirement-
authorized. P4.4C retires zero workflows and leaves the P4.3 retirement ledger
unchanged.

If merged, the daily schedule intentionally enables at most one FotMob request for
one current UTC date per run. This is a newly enabled provider-acquisition trigger
surface only; no provider family is added, manual authority does not change, and
non-ingest authority does not expand. It grants no backfill or model, pricing, routing,
portfolio, share-code, login, wallet, staking, betting, or wager authority. P4.4 and
Architecture Checkpoint E remain incomplete. The merge reaches source-review 5/5;
the mandatory architecture/source reread is required immediately afterward and
before another remediation mission.

## P4.4E canonical-ingest-backed issuer seam

P4.4E prepares an internal, unwired service that composes canonical ingest with
the P4.4D current-reviewed source adapter for exactly one FotMob date under fixed
UTC/NGA semantics. It preserves the exact acquired raw/manifest identity, calls
the shared ingest service as the sole provider-transport owner, and makes no
second request during the PR243 projection. The canonical ingest workflow and
legacy current-reviewed workflow remain byte-identical; no supported live caller
has migrated to the new seam. This does not claim full legacy workflow equivalence
or authorize retirement. Caller migration remains a later reviewed step; P4.4 and
Architecture Checkpoint E remain incomplete.

## P4.4F current-reviewed source lane

P4.4F performs a partial, capability-preserving caller migration for
`issue-current-fotmob-reviewed-source.yml`: exactly `UTC/NGA` uses the canonical
ingest-backed issuer, while all other currently supported timezone/ccode3 pairs
remain on the legacy lane. The workflow inputs and operational contract are
preserved. This closes only the proven one-date FotMob/UTC/NGA compatibility subset;
it does not claim full workflow equivalence or authorize retirement. The bounded
owner-authorized proof is now complete compositionally: one exact-main canonical
FotMob acquisition for 20260926, zero retries/dispatches, followed by zero-network
replay and P4.4D/PR243 projection of the same immutable source. The post-acquisition
Windows proof-environment `tzdata` interruption is retained explicitly rather than
rewritten as a single-process success. P4.4 and Architecture Checkpoint E remain
incomplete.

## P4.4G current-source canonical-only workflow boundary

P4.4G reviews the remaining live legacy branch inside
`issue-current-fotmob-reviewed-source.yml` rather than deleting the workflow.
The read-only GitHub Actions capture at `2026-09-24T22:28:53.032418Z` returned
12 total historical runs for workflow ID `343652927`; all 12 were manual
workflow dispatches and authenticated job logs show UTC/NGA for every run.
Eleven runs succeeded and one failed. No retained run used a noncanonical
request, but the receipt explicitly prevents that observation from becoming a
claim of future capability authority.

The workflow retains its date/timezone/ccode3 input surface and exact UTC/NGA
canonical-ingest-backed behavior. A non-UTC/NGA request is now an explicit
fail-closed unsupported-scope result with zero provider acquisition instead of
a legacy-provider branch. The legacy Python CLI remains source-controlled and
unchanged; this phase neither retires nor deletes it.

P4.4G is one `MAINTENANCE_REVISE` transition with zero workflow-count delta:
38 workflows remain live and the P4.3 retirement ledger remains at three
reviewed retirements. It performs no provider request and no workflow dispatch,
and it reuses the frozen P4.4F operational proof because the canonical lane is
unchanged. No additional workflow retirement, model/pricing/router/portfolio,
share-code, login, cookies, wallet, staking or wager authority is granted.
P4.4 and Architecture Checkpoint E remain incomplete. The source-review counter
is 3/5 while P4.4G is unmerged and becomes 4/5 only after an owner-authorized
merge.

## P4.4H Current Shadow canonical-run migration review

P4.4H adds only a source-controlled offline parity review. The Current Shadow
workflow remains live and unchanged; no caller migration, workflow retirement, or
live canonical SHADOW proof is authorized. The canonical SHADOW service delegates
to the existing reviewed Current Shadow supervisor, but the schedule is not
equivalent today: the legacy workflow schedules SHADOW at 09:00 UTC while the
canonical schedule resolves MAIN. Canonical relative dates also use
`Africa/Lagos`, unlike the legacy UTC fixture-date horizon; the 23:00 UTC boundary
therefore remains an exact migration blocker.

The review keeps notification/email as a separable post-core consumer and preserves
the current artifact/history ancestry dependencies, including the
`current-shadow-all-market-request` identity artifact consumed by canonical run
and P3.0 evidence paths. The `/athena-shadow` issue-comment grammar remains an
explicit compatibility wrapper candidate; it is not removed or silently mapped.
All five P4.3A Current Shadow blockers remain open pending later caller migration
and operational evidence. No workflow YAML or evolution transition changes in
P4.4H. P4.4 and Architecture Checkpoint E remain incomplete; the source-review
counter is 0/5 while unmerged and would become 1/5 if the owner merges, requiring
the prescribed reread before the next remediation mission.
