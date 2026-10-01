# Scheduled SHADOW ownership: architecture projection, policy blocked

Base main: `24aed845e24396d813a91552a70703a76c52ef71`; predecessor #430.
This is **not a deployed schedule migration**. The two production YAML files,
request adapters, restore transport/resolver, manifest builder, service, model,
provider and notification implementation remain unchanged. No live proof occurs.

## Delivery and email decisions still required

AUTH-01's `CAP-SHADOW-DELIVERY-COMPATIBILITY` requires explicit intent and separate
external authorization. The legacy schedule omits `--create-share-code` and
therefore retains `LEGACY_CREATE_SHARE_CODE_DEFAULT=true`. A new no-delivery
schedule is not byte/intent parity with it. Neither preservation of that implicit
scheduled delivery nor its deprecation has explicit new owner-policy disposition
in the reviewed governing evidence.

Delivery: **SCHEDULE_DELIVERY_POLICY_DECISION_REQUIRED** (option C).
Notification: **SCHEDULE_NOTIFICATION_DISPOSITION_REQUIRED**.
The owner must explicitly choose preserved scheduled delivery or intentional
no-delivery deprecation, and either a reviewed post-core secondary email consumer
or explicit scheduled-email retirement. No desktop email. Ordinary SMTP failure
must remain a warning, integrity/security failure fail-closed, business receipt
unchanged. Manual/comment compatibility must retain its existing email behavior.

## Tested proposal — not another workflow/execution authority

`scripts/audit_core_01d_scheduled_shadow_ownership.py` rederives exact bounded
changes to **copies of five existing seams**, in memory. It never writes those
copies to production paths or runs any business/provider executor. The normal
production adapter still defaults scheduled resolution to MAIN only. Reviewers
can export the text-only proposal with `--export-proposal <new external path>`.

- One `canonical-run` job definition in `athena-run.yml`; schedule matrix
  `main,shadow`; manual matrix exactly the explicit `inputs.profile`.
- Matrix `fail-fast=false`: one lane's failure cannot cancel the other lane.
- Job concurrency: MAIN `athena-run-main`; SHADOW `current-shadow-all-market`;
  `cancel-in-progress=false`. The retained legacy manual/comment workflow uses
  the same repository-wide SHADOW group. Jobs have independent hosted workspaces.
- Explicit `--schedule-lane` reaches the existing pure request adapter. MAIN
  requests remain byte-identical; manual requests/metadata remain unchanged.
- SHADOW first freezes UTC today to a concrete ISO date, then delegates to the
  canonical Lagos parser. 09:00Z and 22:59Z map exactly; 23:00Z rejects before
  request persistence/provider work. No clock-derived profile or date repair.
- Delivery is an independent exact bool, required for scheduled SHADOW. No bool
  is inferred from the lane. Both choices are tested offline; neither is selected
  as production policy. The proposed YAML deliberately leaves this input empty
  and fails closed. It is **not a deployable cutover bundle** until policy is set.
- Existing manual MAIN/SHADOW and scheduled MAIN upload
  `athena-run-<run_id>`; only new scheduled SHADOW uses
  `athena-run-<run_id>-scheduled-shadow`.
- Discovery returns at most one canonical candidate per run. Schedule prefers
  the unique live suffix. Old name fallback is allowed only if the suffix is
  absent. A present-but-expired/bad-bound suffix cannot downgrade to MAIN.
  Duplicates and manual suffix/event mismatch fail closed.
- Candidate naming is a closed vocabulary, not `athena-run-*`. Trusted repository,
  canonical workflow, main branch, completed/success and exact IDs remain required.
- V1 manifest producer schema remains unchanged. Transport identity + event +
  request SHA distinguish the lane; independent successful SHADOW receipt and
  exact delivery-success vocabulary still decide restore eligibility.
  The builder's internal old-name candidate remains valid for the same schedule
  run/request/event; no artifact-name field or schema bump is necessary.

## Deployment gate and history

**Canonical scheduled SHADOW is not active. Legacy schedule is not removed.**
There is no dual-live SHADOW schedule. Manual/comment grammars, #276/owner guards,
UTC dates and email remain unchanged. MAIN schedule remains unchanged.

Before a future atomic cutover, resolve delivery/email policy, apply reviewed
seam changes, remove only legacy `schedule`, append exactly one ownership
transition/new snapshot and pass all fourteen cutover checks and exact-head CI.
Do not paste this incomplete proposal into Actions.

The current eleven-transition evolution prefix and every historical receipt/
snapshot remain byte-identical. No production naming/concurrency/ownership change
requires a transition in this design-only PR. The merged C4 audit has only an
exact, source-bounded forward to authenticate this one additive receipt before
the old remediation auditor excludes it from its historical artifact inventory.
Its pre-forward source is preserved as a fixture; neither old receipt is rewritten.

The accepted LG-A archive 36860297707 remains independently verifiable; failed
36846297806 remains permanently failed, non-retryable and restore-ineligible.
No claim is made about CORE-01D blocker 2, which remains untouched.

P4.4 and Checkpoint E: **INCOMPLETE**. Source review counter **1/5 while open**,
2/5 only if the owner later merges; mandatory reread is not due. **DO NOT MERGE.**
