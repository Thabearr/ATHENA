# Fresh-holdout audit campaign-origin consistency repair

## Observed live boundary

After PR #183 merged at exact main `416eab8388a94901b796797b282584a7bce8670c`, owner-triggered read-only audit run `32280322167` advanced past the repaired GitHub binary transport and failed inside lineage interpretation with:

`verified cumulative state leaves earlier nominal slots unresolved`

The already-preserved canonical failure artifact from scheduled run `32256052482` binds nominal slot `2026-08-19T12:07:00Z`, `tick_committed: false`, and an empty durable control journal. That run failed during PR119 bootstrap materialization before the reviewed collection tick entered provider acquisition. No missed observation is reconstructed by this repair.

## Consistency problem

The producer-side campaign-origin recovery from PR #174 / PR #178 already has a narrow GitHub-job-metadata proof for zero-artifact pre-acquisition failures. It allows a later ordinary scheduled run to establish legitimate Genesis, after which the existing producer can durably record elapsed schedule opportunities as `SCHEDULER_GAP_RANGE` with `backfill_authorized: false`.

The PR #170 audit predates that recovery. It currently does two incompatible things:

1. every completed zero-artifact collection run is counted as unverified even when the exact producer-side pre-acquisition predicate can prove that collection and reconciliation were never entered; and
2. every canonical run at slot `n`, including an exact failure artifact, is rejected immediately when its archive has not yet durably accounted for all earlier slots.

That makes the audit abort on the first canonical post-recovery failure before it can inspect a later cumulative archive that may legitimately record those earlier opportunities as missing.

## Narrow repair

The audit should reuse the exact pinned producer-side pre-acquisition proof rather than inventing a second policy. A zero-artifact completed run may be classified as `VERIFIED_PREACQUISITION_CONTROL_FAILURE` only when that existing predicate succeeds against GitHub job metadata.

A canonical failure artifact remains evidence of an exact uncommitted attempt even when earlier slots are still unresolved. It does not make those earlier slots missing. Any unresolved slot keeps the overall audit `PARTIAL_UNVERIFIED_GITHUB_LINEAGE` until a later cumulative archive durably accounts for it.

A successful canonical tick is still forbidden from silently leaping over an unresolved earlier slot. The existing success binding, append-only journal validation, Release verification, exact timestamps, no-backfill semantics, and all downstream false-authority gates remain unchanged.

## Implementation sequencing

The implementation head is intentionally advanced before the reviewed patch is applied so earlier queued Patch Bridge commands become stale and fail closed instead of competing to mutate the branch. Only the single SHA-bound patch issued for the new exact head is eligible to proceed.

## Explicit non-authorities

This repair performs no provider request, workflow rerun, observation replay, backfill, retrofill, Release repair, model approval, production promotion, bookmaker pricing, selection, execution, or `BET` authorization.

## Validation and next boundary

Hosted GitHub Actions remains authoritative. After merge, trigger only the existing read-only owner audit against the exact new main and inspect the real cumulative evidence. Do not manually rerun a collection slot.
