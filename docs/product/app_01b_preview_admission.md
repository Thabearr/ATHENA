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
authority or source identity. Admission applies these checks in order after
C5 session, exact Host and same-Origin middleware:

1. Validate the strict DTO and resolve the opaque preview ID.
2. Require an existing unexpired preview. Unknown and expired IDs share the
   same safe response.
3. Match the echoed envelope digest and canonically reparse the stored exact
   request and envelope bytes.
4. Revalidate the bound source/release identity and recompute current
   `AuthorityManifest` for the exact stored `RunRequest`.
5. Re-evaluate the stored envelope and reject requested-operation blockers.
6. Validate the bounded ASCII idempotency key.
7. Call the injected atomic admission repository port.

The repository port receives the preview ID, exact request/envelope bytes and
hashes, idempotency key, and current authority/source identity hashes. Its
atomic contract is: the same key and same exact identity return the same
`run_id`; the same key with changed identity conflicts; and one preview cannot
be committed under two different keys. A successful HTTP 202 may be returned
only after that durable commit completes. There is no worker, executor,
background task, provider, Current Shadow or delivery call after commit in D1.

`request_sha256` identifies canonical user intent. It is not `run_id`: a run
identity also binds an admitted preview, exact execution envelope, current
authority/source identity and caller idempotency key. Likewise,
`AthenaRunService`'s deterministic request-hash evidence directory stores
request/receipt evidence; it is not a per-intent app-run or idempotency-key
repository.

## Supported backend and sequencing

The preview store is bounded, process-local memory attached to one app
instance, uses cryptographically random opaque IDs and retains the exact
canonical request/envelope/preview bytes until expiry. Restart invalidates
previews. There is no durability claim or app database table. If the store is
at capacity, new preview requests fail safely rather than evicting an unexpired
preview.

The installed `LocalBackend` injects `UnavailableAdmissionRepository`. After
all admission checks, it returns `DURABLE_RUN_STORE_UNAVAILABLE` with HTTP 503,
no `run_id`, and no external work. A deterministic atomic fake repository is
used only in tests to prove 202 and idempotency semantics. D3 owns app preview
and identity/capability persistence; D4 owns durable runs, attempts, ordered
events, external-operation ledger and the transactional repository; E1 owns
job/worker launch. D1 creates none of those tables or services. In particular,
`run_admission_authority` remains false.

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

- HTTP 422: `INVALID_INTENT`, `TARGET_TOTAL_ODDS_NOT_SUPPORTED`,
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
V18 source inventory. D1 appends A2 V19 through V27 to preserve the
implementation and bounded historical projection updates; V1 through V26
remain the append-only predecessor chain. The historical CORE-01A
schedule-date audit preserves its original envelope source through an exact
pre-D1 projection fixture without changing its receipt or source identities.
The workflow YAML diff is zero. Tests inject the only successful repository and
prove zero provider sockets, executor calls, worker launches, Current Shadow,
share-code, login, cookie, wallet, stake and wager actions. This does not claim
completed persistence, run admission in the supported shell, provider
acquisition authority, model/market promotion, installer signing/release, or
Linux GUI qualification.
