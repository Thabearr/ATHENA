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
top level. Successor-family labels are capability mapping hints, not retirement
decisions.

## Retention decisions recorded

- `athena-run.yml` is the canonical run surface; `tests.yml` remains the canonical
  hosted test gate.
- `current-shadow-all-market.yml` remains active and is not retirement-eligible. Its
  blockers include unmigrated scheduled SHADOW ownership, notification/email,
  identity/history artifact ancestry, lack of live canonical SHADOW successor proof,
  and unresolved issue-comment compatibility.
- `current-sportybet-accumulator.yml` is mapped to the canonical MAIN request shape
  (`target_size` → `target_legs`, `days=today`, no total-odds objective,
  `bookie=sportybet`, `profile=main`) but remains owner-review-required because no run
  history exists. The local compatibility command/code is not removed.
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
