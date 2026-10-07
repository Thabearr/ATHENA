# APP-01C Versioned Read API

APP-01C adds authenticated, provider-free v1 read, cooperative cancel-intent,
and export-identity routes to the supported desktop API. It defines application
ports for later data owners; it does not add app persistence or execution.

## Routes

| Method | Route | Contract |
| --- | --- | --- |
| GET | `/api/v1/runs/{run_id}` | Proven run snapshot |
| GET | `/api/v1/runs/{run_id}/events` | Bounded ordered event page |
| GET | `/api/v1/runs/{run_id}/receipt` | Canonically verified terminal receipt projection |
| POST | `/api/v1/runs/{run_id}/cancel` | Cooperative cancel intent only |
| GET | `/api/v1/runs` | Bounded local run history page |
| GET | `/api/v1/fixtures` | Retained indexed fixture page only |
| POST | `/api/v1/exports` | Create an allowlisted export record |
| GET | `/api/v1/exports/{export_id}` | Retrieve immutable export metadata |

All routes pass through the supported app factory and its exact Host, local
session, same-origin mutation, CSP, and response-header controls. Reads perform
no provider acquisition. A read timeout or retry never starts or restarts a
worker.

## DTO and cursor rules

Run IDs are opaque local identifiers matching the existing run-contract
vocabulary; filesystem paths are invalid. Snapshot fields are drawn only from
proven state. Unknown timestamps, counts, stage, delivery, and release identity
remain null or absent; the API does not derive progress percentages or zero
counts.

Event pages use `after_sequence` (default `0`) and `limit` (default `50`, maximum
`200`). Sequences are exact nonnegative integers. The response cursor is the
last returned proven sequence, or null for an empty page. Event records are
strictly increasing, include their observed time and optional state version,
and do not wait for future events. A gap is preserved as a gap.

Run and fixture history use opaque bounded cursors and limits from `1` to
`100`. Run history accepts only exact `state` and `profile` filters. Fixture
filters accept the `club` or `international` scope and a paired canonical date
range of at most 31 days. Invalid cursors, limits, and filters return typed
422 errors.

## Receipts and business outcomes

The read service accepts only canonical receipt bytes supplied by the run
repository and verifies them with `RunReceipt.from_json_bytes`. It returns a
safe projection with the canonical digest, status, request identity, target
legs, selected-leg count, exact shortfall, delivery state, and
`wager_placed: false`. Raw evidence, share-code values, paths, and parser
exceptions are not returned.

A verified `NO_BET` or `SHORTFALL` receipt is a successful `200` read. A run
without a terminal receipt returns `409 RECEIPT_NOT_PRODUCED`; corrupt bytes
return `409 RECEIPT_INTEGRITY_BLOCKED`; an unknown run returns `404`; and an
unavailable run store returns `503 RUN_STORE_UNAVAILABLE`.

## Cancel intent and exports

Cancel records cooperative intent only. It does not kill or launch processes,
retry external work, or create a replacement run. Repeated intent is
idempotent, and terminal state is returned as an already-terminal disposition.

Export requests identify exactly one retained run ID or receipt SHA-256 and
select from `run_summary_json` or `verified_receipt_json`; redaction is either
`standard` or `strict`. The server owns opaque `exp_…` IDs and logical paths
such as `exports/{export_id}/run-summary.json`. HTTP accepts no path, filename,
directory, URL, command, destination, or arbitrary format handler. The API
returns immutable metadata only.

## Current backend availability

The supported desktop wiring injects unavailable read, cancel, retained
fixture, and export ports. Until the owning storage missions exist, the
corresponding routes return typed `503` responses rather than empty history,
fabricated runs, fixtures, receipts, or export IDs. Health and capability
inspection remain provider-free. Route existence does not imply stored data.

The API service ports express these later ownership boundaries:

- D3 owns the schema migration framework and preview/identity/artifact/capability tables.
- D4 owns durable runs, attempts, ordered events, operation ledger, and run artifact links.
- D5 owns fixture and run projections, app exports, backups, audit events, and rebuild.
- E1 owns durable job service and worker claim/launch.

APP-01C adds no tables, migrations, permanent repository, job queue, worker,
projection builder, backup/restore service, or permanent export store.

## Legacy generation

The development compatibility `POST /api/generate` URL remains available only
as a blocked response (`410 LEGACY_GENERATE_BLOCKED`). It performs no
AccaBuilder construction and does not forward work to the run service or a
worker. Callers are directed to the versioned preview/admission contract.
Legacy `/api/fixtures` and `/api/leagues` remain development compatibility
routes and are not mounted in the supported C5 app. The legacy UI continues to
be unsupported; it is not an execution fallback.

## Rollback

Disable or remove the v1 router mounts and service injection if the new API
needs to be rolled back. No database migration or persisted app data needs
rollback. Preserve the `410` legacy generate quarantine during any rollback;
reverting code that restores synchronous AccaBuilder reachability is not a
safe rollback by itself.
