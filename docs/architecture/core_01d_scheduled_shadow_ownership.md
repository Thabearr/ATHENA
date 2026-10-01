# Scheduled SHADOW: authorized source cutover, unmerged PR #431

Base main: `24aed845e24396d813a91552a70703a76c52ef71`.
**Source cutover implemented on an unmerged PR; not deployed on main.**
No live validation, provider acquisition, share-code, email or account action
was performed. Merge would activate the changed schedule ownership on main.
**DO NOT MERGE until independent owner review.**

## Explicit owner policy

- `LEGACY_SCHEDULED_DELIVERY_DEPRECATED_BY_EXPLICIT_OWNER_POLICY`:
  canonical scheduled SHADOW explicitly passes `create_share_code=false`.
  This is intentional delivery deprecation, **not legacy byte/intention parity**.
- `LEGACY_SCHEDULE_EMAIL_EXPLICITLY_RETIRED_BY_OWNER_POLICY`:
  only the legacy scheduled email path is retired. Its declared schedule trigger
  is removed; manual dispatch and issue comments retain delivery/email behavior.
- No canonical email subsystem or hidden delivery default is introduced.

## Atomic source ownership

One `canonical-run` job in `athena-run.yml` runs schedule lanes `main,shadow`;
manual dispatch has exactly one lane, the explicit input profile. Matrix
fail-fast is false. Cron remains 09:00Z. MAIN canonical request bytes remain
unchanged: MAIN/main_application, Lagos today, target 20, SportyBet, no odds
objective, no delivery and no wager.

SHADOW freezes UTC today before canonical Lagos validation: 09:00Z and 22:59Z
are exact; 23:00Z rejects before request persistence/provider work. No date
shift or substitution with Lagos today. SHADOW/research_shadow, target 20,
SportyBet, no odds objective, explicit no-delivery and no-wager.

Job-level concurrency remains repository-wide: MAIN `athena-run-main`, SHADOW
`current-shadow-all-market`, cancellation false. Retained legacy manual/comment
SHADOW uses the same exclusion group. Jobs have isolated runner workspaces.

Existing manual and scheduled MAIN artifacts retain `athena-run-<run_id>`.
Only scheduled SHADOW uses `athena-run-<run_id>-scheduled-shadow`. Discovery
selects a unique live exact suffix first. A present expired/bad-bound suffix
never downgrades to MAIN. Only an absent suffix permits historical exact-name
fallback. Ambiguity and manual suffixes fail closed. Filename is transport
identity, not restore authority: successful SHADOW receipt, request, manifest
and role checks remain independently mandatory. Manifest V1 is unchanged.

`current-shadow-all-market.yml` loses only its declared schedule trigger.
Dispatch inputs, #276/owner guard, both command grammars, UTC validation,
legacy delivery intent, optional secondary email, artifact name and concurrency
remain unchanged. No workflow is deleted.

## Evolution and immutable history

The first eleven transitions are unchanged. Two retained survivor revisions
require **two ordered MAINTENANCE_REVISE transitions**, not the prior design's
one-transition proposal:

12. `CORE01D_ATHENA_RUN_SCHEDULED_SHADOW_CUTOVER_V1`
13. `CORE01D_CURRENT_SHADOW_SCHEDULE_RETIRE_V1`

Each has a distinct exact before-fixture, a single-transition evidence receipt
and cumulative prefix snapshot. Live workflows remain 39, P4.3 retirements 3.

The existing PORT-02C replay successor is not changed and receives **no new
transition**. Explicit owner authorization adds one fourth exact closed context:

- workflow tree: `9060b6fb263febc45332a7cf9c9da8448284b471`
- evolution ledger: `b582a5ba8a31ddfba94324f8869dd253460dcc01102ef356327a3337275b8335`

The before/after identities and three predecessor contexts stay exact. No
wildcard, runtime learning, phase or transition-count authority is allowed.

Merged Checkpoint-E V1 files remain byte-identical. Authenticated frozen source
evaluates V1 as history; V2 records current 39-workflow/57-trigger source.
Scheduled MAIN+SHADOW are two lanes of one schedule event, not two trigger kinds.
The prior design receipt SHA remains recorded in the advanced same-PR receipt.
Accepted LG-A `36860297707` remains valid; failed `36846297806` remains immutable,
failed, non-retryable and restore-ineligible. Historical receipts are not rewritten.

P4.4 and Checkpoint E remain **INCOMPLETE**. Blocker 2—retained-family authority,
dynamic reachability and durable retention—is untouched and requires a separate
review. Source review counter is **1/5 while open**, **2/5 if later owner-merged**;
mandatory reread is not due. **DO NOT MERGE.**
