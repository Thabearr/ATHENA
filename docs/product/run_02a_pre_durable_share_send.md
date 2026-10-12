# RUN-02A prerequisite — durable anonymous CREATE evidence

This prerequisite adds transport evidence, not delivery authority. Base main is
4125624948deb314278004df5f13a627d31f8fd2 (merged PR #458). The product worker
rejects create_share_code=true until a future reviewed durable context is integrated.
Standalone historical proof callers retain their compatibility wrapper and authority.

`DurableShareCodeTransport` requires explicit POST/GET dependencies and exact
run/attempt/lease context. The repository reauthenticates the durable request,
envelope, capability evidence and release. Anonymous share-code generation must
be explicitly requested and allowed; login, cookies, wallet, staking and wager
must all be false. Caller digests never upgrade authority.

The only new operation kind is SPORTYBET_SHARE_CODE_CREATE_V1. Canonical input
evidence binds selections, POST origin/path/body bytes and digest, run, admitted
request/envelope/release and authority digest. PREPARED commits before SENT.
SENT commits with SQLite synchronous FULL before the POST callback is invoked.
SENT means this exact request may have reached the provider. It is conservative
write-ahead evidence, including a crash before the first network byte.

There is one POST maximum. BEGIN IMMEDIATE serializes same-run/kind/intent
admission across independent connections. No operation in any state can be
replaced for the same intent by changing an idempotency key or attempt. Repeated
service calls inspect existing evidence and never resume PREPARED or SENT.
OUTCOME_UNKNOWN is terminal for the action and never retry authority.
The low-level private opener refuses automatic redirects and excludes ambient
global authentication/cookie handlers. Redirect response bytes are retained as
ambiguous evidence; they cannot initiate an implicit GET or substitute an origin.

Exact HTTP response bytes are encoded losslessly in an immutable server-owned
evidence document, including raw SHA-256/byte count and HTTP status. The document
binds run, operation, intent, method and provider origin/path. Publication precedes
artifact linkage; linkage and an independent retained-byte reread precede known
outcome projection. Missing, tampered, cross-run and linked/traversing evidence
cannot prove CONFIRMED. Storage/fencing gaps preserve SENT or OUTCOME_UNKNOWN.

| Evidence | CREATE state / delivery outcome |
| --- | --- |
| Locally blocked before SENT; POST never invoked | PREPARED -> FAILED / LOCAL_PRE_SEND_BLOCKED with SHARE_CREATE_NEVER_SENT |
| Retained HTTP 200, bizCode 10000, recognized code | CONFIRMED / CREATE_CONFIRMED_RELOAD_UNVERIFIED |
| Timeout, reset, exception, empty/malformed/unexpected/non-success response after SENT | OUTCOME_UNKNOWN / CREATE_OUTCOME_UNKNOWN |
| Proven no-create provider rejection | Unsupported: no reviewed contract or fixture exists |
| Exact retained GET roundtrip succeeds | CREATE stays CONFIRMED / CREATE_CONFIRMED_RELOAD_VERIFIED |
| GET fails or mismatches | CREATE stays CONFIRMED / CREATE_CONFIRMED_RELOAD_UNVERIFIED |

Every explicit reload authenticates CONFIRMED and rereads the exact retained
CREATE response to obtain the code. GET never calls POST. Its exact evidence is
retained independently. A repeated CREATE call does not automatically reload;
`reload(operation_id)` is the explicit read-only verification seam.

Owner ruling: no post-SENT response may become FAILED without a future separately
reviewed provider no-create contract. The mandatory provider-proven FAILED
acceptance item remains blocked. This document does not claim review-ready.

No migration is needed: all supported writers serialize the intent check and row
insertion inside the existing repository transaction. TESTING_SYNTHETIC retains
its original transition vocabulary and tests.

A2 successors are append-only from immutable V142; RUN-01A/RUN-01B receipts and
PR #457 policy/evidence remain unchanged. Historical E2 audits reconstruct V142
from byte-pinned source evidence while separately authenticating current A2.
Final commit identity is recorded in the PR/hosted run attestation rather than
embedded self-referentially in its own evidence commit. Evidence binds the exact
source hashes and the source commit immediately preceding its publication.

All validation uses injected synthetic transports or local filesystem evidence.
Provider acquisition, live Current Shadow, Fresh Holdout, real share-code CREATE,
delivery, login/cookies/wallet/stake/wager/email and manual workflow actions are
zero. RUN-02A is BLOCKED/UNSTARTED until this prerequisite is merged and independently
accepted. E4/E5 are UNSTARTED. SOURCE_REVIEW_COUNTER remains 3/5 while unmerged.

DO NOT MERGE.
