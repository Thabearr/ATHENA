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

The offline caller supplies canonical RunReceipt bytes. Receipt producer commit
must equal the independently verified GIT_COMMIT source and original development
provenance. Receipt evidence must explicitly bind run_id, release_id and
execution_envelope_sha256. Installed hash-pinned manifests have no source commit:
their receipts fail closed as unsupported producer lineage, without inventing a
Git commit, signature, or E2 execution evidence. Named future dependency
E2/PACKAGING_AUTHENTICATED_INSTALLED_PRODUCER_PROVENANCE (authenticated
installed-release receipt producer provenance from packaging/E2) remains
OPEN. The storage wrapper
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

Frozen D3 historical projections authenticate changed source paths through the
D4 receipt and retained exact D3 source snapshots. Each retained blob must match
the immutable D3 receipt's source hash. This bounded projection works in shallow
offline CI without ancestor fetches; it does not relax unrelated source checks
or rewrite the D3 receipt or A2 V1–V68. A native resource regression requires both
app migrations in the closed bundle allowlist and triggers native CI naturally.

## Independent-review trust corrections

CONFIRMED requires a retained EXTERNAL_RESPONSE artifact of the same run and
role, safely contained and verified against exact raw SHA and byte count.
Missing, cross-run, wrong-role or corrupted responses cannot change SENT.
Explicit recovery changes a crashed SENT operation to OUTCOME_UNKNOWN, never
resends it. Response-free FAILED requires a reviewed synthetic failure code
(`SYNTHETIC_LOCAL_FAILURE` or `SYNTHETIC_CONFIRMED_FAILURE`); it is not confirmation.

PREPARED to SENT requires RUNNING inside the same BEGIN IMMEDIATE transaction as
the transition. If cancellation owns the writer lock first, the send is denied.
If SENT commits first, later cancellation permits only proven settlement or
explicit uncertainty/recovery under the original fencing token.

Historical reads and exact committed replay authenticate original request,
envelope, capability report and retained release provenance, not the current
release identity. Installed history verifies canonical retained manifest bytes,
their original envelope pin, and all provenance metadata, with no signature or
source-commit claim. Development history additionally requires its original
local Git commit object; missing evidence is explicitly unavailable. Current
admission and all active mutations still require the fresh current source and
source-controlled authority, so a release-B installation cannot resume A's run.

Admission reauthenticates the exact D3 capability report BLOB/digest, canonical
ExecutionPreview, profile, release and expiry, and the D1 authority engine inside
the admission transaction. Blocked, stale or tampered capability evidence creates
no run or genesis event. Verified committed replay remains available before TTL
reevaluation and does not authorize work.

This correction preserves A2 V1–V69 and app migration 0002. New proof source is
bound by the append-only V70 successor, with V69 as its exact unrevised predecessor.

## Terminal read provenance integrity

Authoritative reads authenticate projected terminal evidence in full before
reporting TERMINAL or a RUN_TERMINAL event. The bounded historical terminal
verifier runs from the common run identity path for every run, and proves: the deterministic
`receipt-<sha256>` artifact identity and `run-receipts/<sha256>.json` locator;
exactly one same-run retained RUN_RECEIPT linkage with retained_root ownership;
artifact kind, role, policy, byte count, byte SHA and canonical SHA; canonical
wrapper serialization with its exact reviewed field set and policy binding run,
request SHA, envelope SHA, release, expected state version and attempt lease
identity; canonical RunReceipt parsing with matching request and authority
manifest and the original release-mode producer/release evidence; and exactly
one canonical RUN_TERMINAL event at the terminal state version carrying the
exact receipt SHA. The database status can never float free of this evidence.

The invariant is bidirectional. TERMINAL requires exactly one same-run
RUN_RECEIPT linkage referencing its deterministic pointer; an additional
same-run receipt-role linkage to another artifact is rejected, as are missing
or cross-run linkages. No event may follow the terminal event.
Non-TERMINAL requires a NULL receipt pointer, no RUN_TERMINAL event at any
sequence, and no RUN_RECEIPT linkage. Bounded SQLite existence queries inside
the existing verified transaction enforce this before snapshots, paginated
events, exact replay or mutation authority. Synthetic resurrection and forged
terminal evidence fail closed without deleting, rewriting or repairing records.
A standalone published receipt file is not a committed projection.
Missing, corrupt,
wrong-run, wrong-role or unverified evidence raises the typed safe
`TerminalEvidenceUnavailable` error; no read surface ever reports a clean
TERMINAL projection or authenticated RUN_TERMINAL event when proof fails.
Durable original records are never altered and no substitute evidence is
manufactured. Honest QUEUED, RUNNING, CANCEL_REQUESTED, CANCELLED and
INTERRUPTED states and honest pre-projection published receipts remain
readable as nonterminal; explicit idempotent reconciliation keeps its exact
receipt-first behavior. Historical reads never depend on current-release
eligibility and never invent producer Git provenance; installed receipts
without independently authenticated producer identity remain fail-closed
(E2/PACKAGING_AUTHENTICATED_INSTALLED_PRODUCER_PROVENANCE stays OPEN). There
is no scanning worker and no startup reconciliation.

This correction preserves A2 V1-V73 and app migrations 0001/0002. New proof
source is bound by the append-only V74 successor, with V73 as its exact
unrevised predecessor.
