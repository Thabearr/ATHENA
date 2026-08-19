# FotMob UTC-native xG fresh-holdout Actions lineage audit

## Status

`READ_ONLY_GITHUB_EVIDENCE_OBSERVABILITY_NOT_MODEL_APPROVAL`

PR #170 adds a narrow observability boundary for the real prospective FotMob UTC-native expected-goals holdout. The scheduled collection workflow remains the evidence producer. This audit only reads GitHub metadata and bytes that the reviewed campaign already emitted.

The audit does **not** contact FotMob, SportyBet, Sportradar, or any football provider. It does not rerun a collection job, backfill a missed slot, repair a Release, refit or approve a model, authorize a price, choose a selection, build a slip, or issue a BET.

## Why this boundary exists

The reviewed campaign runs on the exact UTC `:07/:37` lattice and preserves cumulative evidence in GitHub Actions plus long-lived Releases. Some review clients cannot enumerate scheduled Actions runs directly. That visibility limitation must not be solved by guessing run IDs or by treating nominal cron time as proof that a run existed.

PR #170 therefore lets the repository owner explicitly request a **read-only GitHub audit after this PR is merged**. The workflow runs inside GitHub, where it can enumerate the scheduled workflow, verify existing artifacts, inspect cumulative control lineage, and post a compact result back to PR #170.

The PR comment is an operational presentation surface only. It is not an independent source of truth. The underlying Actions metadata, independent artifact digest, canonical archive/receipt bytes, Release bytes, and cumulative durable control journal remain the evidence.

## Frozen dependencies

The audit pins and revalidates:

- PR151 activation runner Git blob: `901ab137d6601a3485eac30da7e6bad7eeefa397`
- PR168 Release receipt mirror Git blob: `ddabb6ae83cbe6c81c9264119a121a54715df960`
- scheduled collection workflow Git blob: `2310d2253b00b8ddd995d7a28e0d67e6ea9381dd`

The post-merge control workflow also pins the exact reviewed PR #170 audit-script Git blob. If that implementation drifts after review, the owner-triggered audit refuses to execute.

The existing PR168 `verify_actions_artifact_zip_digest(...)` and `verify_actions_artifact_bundle(...)` functions remain the artifact/receipt cryptographic boundary. The existing PR151 `verify_and_extract_durable_state_archive(...)` remains the archive member/extraction boundary.

## Evidence flow

For each observed scheduled run after the campaign origin, the audit:

1. verifies current `main` exactly equals the owner-authorized SHA;
2. enumerates the scheduled collection workflow with pagination;
3. requires the reviewed workflow name, `schedule` event, `main` branch, and reviewed workflow path;
4. never treats queued/in-progress runs as completed evidence;
5. for a completed run, requires exactly one unexpired canonical `success-*` or `failure-*` evidence artifact;
6. binds downloaded ZIP bytes to GitHub's independent artifact `digest`;
7. verifies exact archive + canonical tick receipt using PR168;
8. verifies the matching long-lived Release archive byte-for-byte;
9. verifies the mirrored `.receipt.json` sidecar when present, or reports it missing without repairing it;
10. extracts durable state only into an isolated temporary root through PR151;
11. validates append-only control lineage and reconstructs scheduled-slot state.

No provider URL is requested anywhere in this flow.

## Success versus failure receipts

The reviewed collection workflow deliberately has two receipt shapes on its failure path.

A successful tick has the rich receipt produced by the PR151 runner. PR #170 therefore requires a successful artifact to bind all of the following before it can become verified lineage:

- exact runner/schema identity;
- `scheduled_for_utc == nominal_scheduled_for_utc`;
- exact `:07` or `:37` cron expression;
- exact downstream safety vocabulary with every authority false;
- zero-exit / `tick_committed: true` semantics already re-proved by PR168;
- a matching durable `TICK_COMMITTED` row for the exact nominal slot;
- the commit row's Release tag and durable asset name must equal the receipt/artifact identity.

A failed tick may terminate before the runner can write that richer receipt. The packaging step still creates a canonical workflow-level failure receipt containing the exact run ID, nominal slot, cron identity, durable archive commitment, non-zero exit, `tick_committed: false`, and failure-lineage reconcile outcome. PR #170 accepts that reviewed minimal failure shape as evidence of a **verified uncommitted workflow attempt**. If richer runner/schema/safety fields are present on a failure receipt, they must still agree exactly with the reviewed implementation.

An early first-slot failure may legitimately have no control journal yet. Its verified failure receipt can therefore establish `FIRST_SLOT_VERIFIED_UNCOMMITTED_ATTEMPT`. A later cumulative archive may subsequently establish that slot as durable prospective missingness through `SCHEDULER_GAP_RANGE`.

## Slot semantics

Campaign origin:

- holdout start: `2026-08-19T00:00:00Z`
- first nominal slot: `2026-08-19T00:07:00Z`
- cadence: every 30 minutes on UTC `:07` and `:37`

The audit exposes exactly these slot states:

- `COMMITTED`
- `DURABLY_RECORDED_MISSING`
- `VERIFIED_UNCOMMITTED_ATTEMPT`
- `UNRESOLVED`

The first nominal slot is summarized as one of:

- `FIRST_SLOT_COMMITTED`
- `FIRST_SLOT_DURABLY_RECORDED_MISSING`
- `FIRST_SLOT_VERIFIED_UNCOMMITTED_ATTEMPT`
- `FIRST_SLOT_UNRESOLVED`

A later cumulative `SCHEDULER_GAP_RANGE` is allowed to prove that an earlier nominal slot became legitimate prospective missingness. Such a gap must retain `backfill_authorized: false`. The audit never retrofills it.

A slot may never be both committed and durably missing. A later commit inside an already recorded gap is a lineage contradiction and fails closed. Consecutive failed ticks may legitimately append expanding gap ranges that repeat already-known missing slots, for example `00:07..00:07` followed by `00:07..00:37`; the audit accepts that producer-compatible cumulative form only when detection advances and the range remains consistent with the last committed anchor.

A later verified run may not silently leap over an unexplained earlier slot. Before a run at slot `n` becomes verified, its cumulative durable state must account for every earlier slot as either committed or durably missing.

## Failure evidence

A `failure-*` archive is not classified from its filename alone. PR168 must first prove the canonical archive/receipt bundle, including non-zero tick exit and `tick_committed: false`. The cumulative state, when present, must not contain `TICK_COMMITTED` for that nominal slot.

If a later cumulative archive records the failed slot inside a valid scheduler gap, the current slot state becomes `DURABLY_RECORDED_MISSING`; the historical failed run remains visible in the run audit.

## Release durability

Release states are explicit:

- `RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED`
- `RELEASE_ARCHIVE_VERIFIED_RECEIPT_MISSING`
- `RELEASE_DURABILITY_UNVERIFIED`

A missing sidecar is reported. PR #170 never uploads or repairs it.

## Owner-triggered audit

After PR #170 is merged and closed, the repository owner may post exactly:

```text
/athena-audit-fresh-holdout-lineage
main-sha: <current lowercase 40-hex main SHA>
confirm: READ_ONLY_ACTIONS_LINEAGE_AUDIT
```

The command is bound to PR #170, the repository owner, exact current `main`, and exact three-line framing. Normal unrelated PR comments do nothing.

The workflow has only:

- `actions: read`
- `contents: read`
- `pull-requests: read`
- `issues: write`

The only write is the compact audit-result PR comment plus the normal Actions audit artifact. It has no Actions write permission and contains no rerun command.

## CLI

```bash
python scripts/audit_fotmob_fresh_holdout_actions_lineage.py \
  --repository Thabearr/ATHENA \
  --expected-main-sha <CURRENT_MAIN_SHA> \
  --output fresh-holdout-actions-lineage-audit.json
```

The output path is no-overwrite. The result is canonical compact sorted-key JSON with a terminating newline.

## Audit states

- `VERIFIED_COMPLETE_TO_LATEST_OBSERVED_RUN`
- `PARTIAL_UNVERIFIED_GITHUB_LINEAGE`
- `NO_COMPLETED_CAMPAIGN_EVIDENCE`

Partial transport or Release durability is never promoted to complete. An observed scheduled run that is still queued or in progress is reported through `incomplete_run_count` and keeps the audit in `PARTIAL_UNVERIFIED_GITHUB_LINEAGE`; it is never interpreted as committed evidence.

## Explicit non-authorities

Every result keeps these false:

- provider network acquisition authorization
- provider network acquisition performed by the audit
- backfill authorization
- model approval
- production approval
- pricing authorization
- selection authorization
- BET authorization

## Next boundary

`REVIEW_VERIFIED_LIVE_FRESH_HOLDOUT_ACTIONS_LINEAGE`

That review may establish what the real campaign has durably observed. It does not itself approve the xG successor.
