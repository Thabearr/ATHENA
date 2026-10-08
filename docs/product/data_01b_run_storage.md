# D4 / DATA-01B durable run storage

## Boundary

This is an offline control-plane storage seam, not executor authority.
`DurableRunRepository` is never installed into supported API or desktop
admission. `POST /api/v1/runs` remains typed 503
`DURABLE_RUN_STORE_UNAVAILABLE`; desktop retains its unavailable admission port.
No repository method launches, signals, kills, or transports work.

Only `WritableRoots.data_root/athena-app.sqlite3` is owned. Migration 0002
adds exactly `app_runs`, `app_run_attempts`, `app_run_events`,
`app_external_operations`, and `app_run_artifacts`: fourteen tables including
the v1 ledger. Migration 0001 remains byte-identical. Legacy football/history
migrations are not part of the explicit app migration allowlist. D5 tables
and backup/export products are out of scope.

## Integrity and migration

Connections are short-lived and owned by their calling thread. Every operation
checks runtime migration resources, ledger identities and complete schema
structure. Writes use WAL, synchronous FULL, foreign keys ON and one
`BEGIN IMMEDIATE` transaction. Reads use a verified read-only snapshot.
Missing, newer, partial or drifted schemas fail closed.

Each pending migration retains its own truthful pre-state manifest. Fresh v2
installation retains the absent v1 pre-state and the committed nine-table v1
snapshot before v2. A v1 upgrade retains its existing pre-state once. No-op
restart produces no new migration evidence. Retained evidence uses RESTRICT
foreign keys, never cascading deletion.

## Admission and state

`local-default` is the only presentation profile; MAIN/SHADOW authority remains
in the exact persisted ExecutionEnvelope. Admission compares canonical request,
envelope, source, authority, release and expiry identities with D3 evidence.
The idempotency key is owned per presentation profile and a preview is consumed
once. Exact committed replay wins before expiry; new commits check the UTC
clock inside the serialized transaction. Admission creates no worker.

Genesis is a QUEUED row at state_version 0 and a RUN_QUEUED event at sequence 1,
state_version 0. State CAS and its canonical, SHA-bound event are atomic.
Allowed states are QUEUED, RUNNING, CANCEL_REQUESTED, TERMINAL, CANCELLED and
INTERRUPTED. No transition returns automatically to QUEUED. Queued cancellation
becomes CANCELLED; running cancellation becomes CANCEL_REQUESTED. Repeated
cancellation adds no event and does not signal a process.

Attempts have monotonic per-run numbers and globally unique lease tokens.
Only the unfinished latest attempt can write, and its run and token must match.
An unfinished attempt prevents another claim. Process locators admit only
`{"kind":"OFFLINE_TEST","label":"safe-identity"}`; arbitrary executable,
credential and filesystem locators are forbidden.

## External operations

Only TESTING_SYNTHETIC is accepted. PREPARED may become SENT or FAILED;
SENT may become CONFIRMED, FAILED or OUTCOME_UNKNOWN. OUTCOME_UNKNOWN is final,
not retry or resend authority. Explicit offline recovery marks SENT operations
unknown and interrupts the run. No production provider, delivery, share-code,
login, cookie, wallet, stake or wager integration exists.

## Receipt-first terminal projection

The offline caller supplies canonical RunReceipt bytes. The storage wrapper
binds them to run, request, envelope, release, expected state version and attempt
lease identities. Request and authority must match and delivery results are
rejected. The wrapper is atomically published through fsynced temporary bytes
and a no-overwrite hard link under `data_root/run-receipts/<sha256>.json` before
any terminal database projection. Publication may leave an unprojected receipt
after a crash; this is intentional.

`project_terminal_receipt` verifies bytes and bindings, fences the attempt, then
atomically records retained artifact metadata, the artifact role, TERMINAL CAS
and its event. `reconcile_receipt_projection` is an explicit offline seam using
the same verification; the exact already-projected receipt is a no-op. There is
no automatic startup worker or receipt discovery scan.

## Review gates

Focused offline proofs cover admission replay/conflict/expiry, two-thread and
two-process races, attempt fencing, event sequencing, cancellation, synthetic
operation uncertainty, receipt-first crash reconciliation, v1 upgrade and
no-op migration evidence. D3 regression tests remain required. Hosted exact-head
Tests and PORT-02C CASE 5 plus independent review are separate final gates;
local success does not establish review readiness. Never merge this D4 PR.
