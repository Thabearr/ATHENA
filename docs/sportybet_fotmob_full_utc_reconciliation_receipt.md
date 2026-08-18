# SportyBet ↔ FotMob full-UTC reconciliation receipt

## Purpose

PR #163 established the strict deterministic reconciliation itself: a provider-resolved SportyBet full-UTC fixture may match an admitted, source-replayed FotMob fixture only by exact case-sensitive home, away, competition and UTC kickoff equality. A unique exact match may authorize only fixture reconciliation; zero or multiple exact matches authorize nothing.

This boundary makes that result durable without weakening any trust requirement. It executes PR #163 again from the complete preserved source chain and stores only the exact canonical reconciliation bytes under an ignored research cache root.

This is **not** a market-mapping, pricing, model, selection, ACCA, booking-code, execution or BET boundary.

## Why a receipt is required

Before this boundary, a PR #163 result existed only as an in-memory object returned by the reconciliation builder. A later component must not be able to receive a hand-constructed object, a copied hash, or a stale result and treat it as proof that the real preserved sources reconciled.

A durable receipt therefore has two rules:

1. publication is possible only by executing the exact PR #163 builder from the complete source bundle; and
2. verification is always source-aware: ATHENA rebuilds the result from the original sources and requires exact byte equality with the stored receipt.

There is intentionally no public storage-only verifier.

## Complete source bundle

`FullUtcReconciliationSourceBundle` carries the exact inputs already required by PR #163:

- PR #162 kickoff promotion;
- PR #158 event-local GMT qualification;
- PR #153 SportyBet user-controlled event manifest;
- PR #154 native inventory;
- exact preserved SportyBet event HTML bytes;
- PR #157 Terms qualification;
- exact preserved Terms HTML bytes;
- PR #160 SportyBet → Sportradar event-ID bridge;
- PR #161 official Sportradar event metadata evidence;
- exact preserved Sportradar JSON response bytes;
- admitted reviewed FotMob fixture catalog; and
- exact raw FotMob `/api/data/matches` captures plus their manifests.

The receipt layer does not independently reinterpret any of these sources. It delegates the semantic and lineage proof to PR #163's exact builder, which in turn replays the upstream chains.

## Storage contract

Receipts are written only under:

`.cache/athena-research/sportybet-fotmob-full-utc-reconciliation-receipts`

Each receipt directory contains exactly one file:

`reconciliation.json`

The directory name is the first 24 hexadecimal characters of SHA-256 over the full canonical PR #163 reconciliation bytes. The full bytes, not the truncated directory identity, remain authoritative.

The root is repository-relative and exact. Traversal, alternate roots, symlinks, unexpected files and non-regular receipt files fail closed.

Publication is no-overwrite. Repeating the same source bundle is idempotent only after source replay proves the already stored canonical bytes are exact. A truncated-hash collision or any differing stored bytes fail closed and never overwrite the prior receipt.

Files and containing directories are durability-synchronised. A partial write must be removed before an error returns; cleanup failure is itself a hard error rather than a warning.

## Accepted outcomes

All three PR #163 outcomes can be recorded because a negative or ambiguous result is still valuable evidence:

- `UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED`
- `NO_EXACT_FULL_UTC_MATCH`
- `AMBIGUOUS_EXACT_FULL_UTC_MATCH`

Persistence never changes the authority carried by the PR #163 result.

A unique receipt preserves only the exact `fixture_reconciliation_authorized = true` already earned by PR #163. A no-match or ambiguous receipt preserves `fixture_reconciliation_authorized = false`.

## What remains blocked

The receipt grants no new downstream capability. In particular it does not authorize:

- automated SportyBet, Sportradar or FotMob acquisition;
- provider alias inference or fuzzy matching;
- SportyBet canonical market mapping;
- bookmaker market equivalence;
- provider quote timestamp or snapshot identity;
- fresh-price authority;
- pricing or value;
- model integration;
- selection;
- ACCA/slip construction;
- booking-code generation;
- SportyBet execution; or
- BET.

ATHENA's core rule remains unchanged: **no exact fresh same-source bookmaker price, no BET**. The project vision requires evidence integrity, fail-closed handling, and an auditable chain from source through fixture identity, model capability and price before a bet can exist.

## Next boundary

Only a **real source-replayed receipt** with `UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED` may feed the next SportyBet boundary: exact canonical market and selection mapping for that reconciled fixture.

If the real receipt is `NO_EXACT_FULL_UTC_MATCH`, the next work must diagnose the exact literal mismatch or establish a separately reviewed explicit alias contract. If it is ambiguous, ATHENA must preserve the ambiguity and choose no fixture.
