# APP-01B: local preview and fail-closed admission

APP-01B adds a versioned, same-origin HTTP surface to the verified C5 local
shell. It constructs a read-only request preview and defines the boundary for
idempotent durable admission. The supported desktop shell does not have the
reviewed D3/D4 transactional app-run store, so its admission repository is
intentionally unavailable and `/api/v1/runs` returns typed HTTP 503 after all
preview, source, authority, blocker and idempotency checks pass. This work does
not grant execution authority.

## Canonical domain contracts

The API reuses `domain.run_contracts.RunRequest` and
`canonical_json_bytes`, plus `RequestedOperationIntent`, `ExecutionEnvelope`,
`ExecutionPreview`, `AdmissionBlocker`, and
`evaluate_execution_envelope` from `domain.execution_envelope`. HTTP/Pydantic
models are strict transport DTOs only. The router owns no football, pricing,
probability, fixture-reconciliation, Router, Portfolio, or provider semantics.
Preview construction calls the public
`AthenaRunService.authority_manifest_for(request)` mapping, but never calls
`AthenaRunService.run()`.

The preview DTO is exact and rejects extra fields:

```json
{
  "dates": ["2030-01-01"],
  "target_legs": 3,
  "target_total_odds": null,
  "bookie": "sportybet",
  "profile": "main",
  "acquire_sources": false,
  "create_share_code": false
}
```

`dates` must contain one through seven unique canonical `YYYY-MM-DD` strings.
The existing explicit request parser applies the Lagos today-through-six-day
horizon at preview time. Relative words, weekdays, CLI shorthand ranges and
arbitrary modes are not accepted by HTTP. Dates are resolved once and then
remain frozen in the canonical request and envelope through admission, even
across Lagos midnight. `target_legs` is an exact integer from 1 through 50;
`target_total_odds` must be null. Only the exact `sportybet` adapter and
`main`/`shadow` profile vocabulary are accepted. Acquisition and share-code
delivery intent are separate required booleans. Neither is inferred from the
profile. Wager intent is always false and no wager field exists in the DTO.

The service constructs one exact `RunRequest` and one
`RequestedOperationIntent`, checks that their delivery intent matches, gets
the current canonical authority manifest, and evaluates the exact envelope.
Preview reports include request, envelope and preview SHA-256 identities,
operation decisions, safe blockers, concrete dates, a 30-minute expiry and a
safe source identity projection. An allowed operation is only the result of
the canonical capability intersection. A preview remains local computation;
it performs zero provider/network requests, process or worker launches,
share-code creation, run creation or executor calls.

## Source identity

ExecutionEnvelope V2 and its replay bytes retain their original schema and
policy IDs. D1 adds a versioned V3 envelope/preview/source-identity contract
because V2 cannot truthfully encode the installed runtime's trust mode.
Development previews bind the exact Git commit. Installed previews use
`PINNED_RELEASE_MANIFEST`, binding the trusted manifest SHA-256, release ID,
build ID, platform, architecture, manifest schema/policy and
`TRUSTED_MANIFEST_SHA256_V1` trust mode. This out-of-band hash pin is not
release signing and is never labeled `SIGNED_RELEASE`.

The source adapter revalidates the exact `ResourceResolver` identity. For an
installed release it verifies the same release root against the original
trusted manifest SHA-256 and checks the canonical release fields again. For a
development checkout it verifies the exact repository HEAD. The API never
returns an absolute resource or writable-root path.

## Admission DTO and ordering

The only accepted admission body is:

```json
{
  "preview_id": "opaque-process-local-id",
  "execution_envelope_sha256": "<exact preview envelope SHA-256>",
  "idempotency_key": "caller-key-1"
}
```

The caller cannot replace dates, target legs, profile, operation intent,
authority or source identity. After C5 session, exact Host and same-Origin
middleware, admission uses this ordering:

1. Validate the strict DTO, including a lowercase 64-hex envelope digest and
   bounded ASCII idempotency key. Malformed values are invalid input (422).
2. Probe the repository by the exact tuple `(idempotency_key, preview_id,
   execution_envelope_sha256)`, before requiring process-local preview bytes.
   An already committed exact tuple returns its original `run_id` as
   `idempotent_replay`; the same key with a different preview ID or digest is
   `IDEMPOTENCY_CONFLICT` (409). This replay path does not re-run source,
   authority, provider, executor or delivery work.
3. Only when the repository confirms no commit for that key, require an existing
   unexpired process-local preview. Unknown and expired IDs share the same safe
   response. If the repository is unavailable and the local preview is gone,
   the service returns `DURABLE_RUN_STORE_UNAVAILABLE` rather than asserting
   that no prior commit exists.
4. Match the syntactically valid echoed digest against the stored envelope and
   canonically reparse the exact request, envelope and preview bytes. A valid
   lowercase digest that does not match is `PREVIEW_DIGEST_MISMATCH` (409).
5. Revalidate the bound source/release identity, recompute current
   `AuthorityManifest` for the exact stored `RunRequest`, re-evaluate the
   envelope and reject requested-operation blockers.
6. Pass the exact immutable candidate, including the typed envelope
   `expires_at`, to the repository's atomic admission operation.

The repository port exposes an authoritative read-only replay lookup and an
atomic commit. The atomic operation owns, in one transaction/critical section,
commit-time UTC expiry comparison, idempotency-key ownership, one-preview/one-run
consumption and creation of exactly one run identity. A matching commit found
inside that section is replayed before expiry is considered; a new candidate
whose `preview_expires_at` has passed receives the typed `preview_expired`
disposition, mapped to `PREVIEW_EXPIRED` (409). Thus an early process-local
expiry check is only a fast rejection and is not treated as commit-time proof.
A successful HTTP 202 may be returned only after an atomic commit or exact
idempotent replay. There is no worker, executor, background task, provider,
Current Shadow or delivery call after either path in D1.

`request_sha256` identifies canonical user intent. It is not `run_id`: a run
identity also binds an admitted preview, exact execution envelope, current
authority/source identity and caller idempotency key. Likewise,
`AthenaRunService`'s deterministic request-hash evidence directory stores
request/receipt evidence; it is not a per-intent app-run or idempotency-key
repository.

## Supported backend and sequencing

Unadmitted previews are bounded, process-local memory attached to one app
instance. They use cryptographically random opaque IDs and retain exact
canonical request/envelope/preview bytes only until expiry; restart invalidates
those unadmitted preview records. A committed admission is different: an
available repository can recover its exact key + preview ID + envelope digest
identity after preview expiry or process restart and return the existing run
ID without new work. If the store is at capacity, new preview requests fail
safely rather than evicting an unexpired preview.

The installed `LocalBackend` injects `UnavailableAdmissionRepository`. Its
replay lookup fails as unavailable; it does not fabricate a prior run or claim
that the key is absent. An active, otherwise-valid new admission continues to
the unavailable atomic commit and returns `DURABLE_RUN_STORE_UNAVAILABLE`
(HTTP 503) with no `run_id` or external work. If a prior commit cannot be
looked up because the backend is unavailable and the process-local preview is
gone, the result is also 503, not a false expiry/absence claim. A deterministic
atomic fake repository is used only in tests to prove expiry, replay and
single-consumption semantics. D3 owns app preview and identity/capability
persistence; D4 owns durable runs, attempts, ordered events, external-operation
ledger and the transactional repository; E1 owns job/worker launch. D1 creates
none of those tables or services. In particular, `run_admission_authority`
remains false and durable admission remains unavailable in the supported shell
until the later data/job missions.

The capability snapshot reports `run_preview=available` only while the
verified source identity supports preview. It describes preview as read-only
and grants no execution authority. A separate `run_admission` row remains
`blocked_implementation` pending durable storage and the later job service.
Provider authority and model/market readiness remain unproven or blocked.

## Safe errors

All route-level errors are typed DTOs with `code`, `safe_message`, finite
`retry_class` (`never`, `after_refresh` or `after_delay`) and optional
`run_id`, `stage` and `diagnostic_id`. They never serialize raw exceptions,
tracebacks, credentials, environment values or filesystem paths. The machine
codes are:

- HTTP 422: `INVALID_INTENT` (including missing or malformed
  `execution_envelope_sha256`), `TARGET_TOTAL_ODDS_NOT_SUPPORTED`,
  `UNSUPPORTED_BOOKIE`, `INVALID_DATE`, `INVALID_IDEMPOTENCY_KEY`.
- HTTP 409: `PREVIEW_EXPIRED`, `PREVIEW_DIGEST_MISMATCH`,
  `PREVIEW_STALE_AUTHORITY`, `PREVIEW_BLOCKED`, `IDEMPOTENCY_CONFLICT`,
  `PREVIEW_ALREADY_CONSUMED_CONFLICT`.
- HTTP 503: `PREVIEW_SOURCE_IDENTITY_UNAVAILABLE`,
  `DURABLE_RUN_STORE_UNAVAILABLE`, `CURRENT_AUTHORITY_UNAVAILABLE` and
  `PREVIEW_STORE_UNAVAILABLE`.

C5's exact Host, in-memory session credential and exact Origin checks remain
the only local route security boundary. The routes add no alternate auth,
credential URL, CORS permission or Python bridge. Stale/blocked/mismatched
previews reach neither the repository nor an executor/provider. There is no
external work to roll back; expiration and process restart simply make a
preview unavailable.

## Evidence and limits

The APP-01A receipt is unchanged and remains authenticated against its exact
V18 source inventory. D1 appends A2 V19 through V29 to preserve the
implementation and bounded historical projection updates; V1 through V28
remain the append-only predecessor chain. A2 V29 canonical SHA-256 is `9ef0aa423204ccab1090a7059e821de4cf0e8cf1ad531040ce60c448d140f2a2`. V29 names V28 (`3e20bf8828fd211b22d129f0e3d1d8139c62861c1c4414dac9caecc93c2047a9`) as its unrevised predecessor. The historical CORE-01A
schedule-date audit preserves its original envelope source through an exact
pre-D1 projection fixture without changing its receipt or source identities.
The workflow YAML diff is zero. Tests inject the only successful repository and
prove zero provider sockets, executor calls, worker launches, Current Shadow,
share-code, login, cookie, wallet, stake and wager actions. This does not claim
completed persistence, run admission in the supported shell, provider
acquisition authority, model/market promotion, installer signing/release, or
Linux GUI qualification.
