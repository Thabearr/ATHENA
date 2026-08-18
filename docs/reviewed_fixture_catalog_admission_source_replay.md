# Reviewed Fixture Catalog Admission Source Replay

## Purpose

This boundary makes the existing reviewed FotMob `ReviewedFixtureCatalogAdmission`
reconstructible from durable, user-controlled evidence instead of requiring an
already-live Python object.

It is the missing prerequisite between the durable PR #164 SportyBet/FotMob
reconciliation receipt layer and a real offline reconciliation execution command.

The boundary performs **no network acquisition** and grants no bookmaker,
pricing, selection, slip, booking-code, execution, or BET authority.

## Source chain

A source-replayed admission requires the exact existing reviewed FotMob chain:

1. one or more verified PR #38 `/api/data/matches` capture directories;
2. the exact explicit fixture-review decision ledger;
3. the exact checked reviewed Fixture Catalog JSON;
4. the exact checked reviewed Fixture Catalog manifest;
5. one explicit catalog-admission review decision.

The operator command replays
`scripts.manage_fotmob_reviewed_fixture_catalog.run(...)` in `CHECK` mode.
The checked manifest supplies the exact historical `as_of`,
`minimum_lead_seconds`, generator commit, and clean-worktree claim used for the
replay. The rebuilt handoff and compiler result must reproduce the checked
catalog and manifest before admission review is considered.

## Explicit catalog-admission review decision

The admission decision is a canonical UTF-8/LF JSON object with exact schema
`athena-reviewed-fixture-catalog-admission-source-replay-decision-v1`.

Its hashes are not free-form authority. They are all cross-checked against the
source-replayed handoff and compiler result by the existing
`ReviewedFixtureCatalogAdmission` constructor:

- candidate bundle SHA-256;
- review bundle SHA-256;
- handoff SHA-256;
- catalog SHA-256;
- manifest SHA-256;
- reviewed source capability and current capability SHA-256;
- exact `ADMITTED` or `REJECTED` disposition;
- review timestamp, reviewer reference, and notes.

The command deliberately separates `prepare-decision` from `store`.
`prepare-decision` replays all sources and emits the exact canonical decision
bytes for human review. `store` replays all sources again and accepts only an
exact canonical decision file.

## Durable artifact

Successful `store` writes only beneath:

```text
.cache/athena-research/reviewed-fixture-catalog-admission-source-replay
```

Each deterministic admission directory contains exactly:

```text
admission-decision.json
admission.json
```

The directory identity is the first 24 hexadecimal characters of SHA-256 of the
exact canonical `ReviewedFixtureCatalogAdmission` bytes.

There is deliberately **no public storage-only authority path**. The domain
module contains an internal semantic directory check used only after a trusted
caller has already rebuilt the exact handoff and compiler result. Downstream
consumption must instead call the public operator-layer
`revalidate_stored_admission_from_sources(...)` path. That function first
replays the raw FotMob capture directories, fixture-review decision ledger,
checked catalog, and checked manifest, then reparses the stored canonical
catalog-admission decision, rebuilds the complete admission, and requires
byte-for-byte equality with the stored artifact.

A caller therefore cannot obtain catalog-admission authority merely by loading
`admission.json`, by constructing a hash-shaped Python object, or by supplying a
previously valid handoff/compiler object without replaying its raw reviewed
source chain.

## Failure policy

The boundary fails closed on, among other conditions:

- duplicate/non-finite/noncanonical decision JSON;
- hash-shaped lineage that does not match source replay;
- stale or tampered catalog/manifest;
- source capability drift;
- unexpected artifact-directory entries;
- symlinks, traversal, or alternate output roots;
- admission/decision tampering;
- identity collisions;
- partial writes;
- cleanup failure.

A senior-review concurrency rule is explicit: cleanup is attempted only after
the current invocation itself successfully created the target directory. If a
competing writer wins the `mkdir()` race, this invocation must fail without
deleting the competing directory.

## Authority

An `ADMITTED` replay proves only the already-reviewed FotMob Fixture Catalog
admission semantics.

A `REJECTED` replay is preserved as rejection evidence and exposes no admitted
fixtures.

This boundary does **not** authorize:

- SportyBet/FotMob fixture reconciliation by itself;
- bookmaker equivalence;
- SportyBet canonical market mapping;
- fresh-price authority;
- pricing/value/model integration;
- selection;
- ACCA/slip construction;
- SportyBet booking-code generation;
- SportyBet execution;
- BET.

## Operator examples

Prepare a canonical catalog-admission review decision:

```bash
python scripts/replay_reviewed_fixture_catalog_admission.py prepare-decision \
  --capture-directory <capture-1> \
  --capture-directory <capture-2> \
  --fixture-review-decision-ledger <fixture-review.json> \
  --check-catalog <reviewed-catalog.json> \
  --check-manifest <reviewed-catalog.manifest.json> \
  --disposition ADMITTED \
  --reviewed-at 2026-08-18T20:00:00.000000Z \
  --reviewer-reference operator:catalog-admission \
  > admission-decision.json
```

After explicit review of those bytes, replay again and store the admission:

```bash
python scripts/replay_reviewed_fixture_catalog_admission.py store \
  --capture-directory <capture-1> \
  --capture-directory <capture-2> \
  --fixture-review-decision-ledger <fixture-review.json> \
  --check-catalog <reviewed-catalog.json> \
  --check-manifest <reviewed-catalog.manifest.json> \
  --admission-decision admission-decision.json
```

A later consumer must source-revalidate the stored admission rather than read it
as standalone authority:

```python
from scripts.replay_reviewed_fixture_catalog_admission import (
    revalidate_stored_admission_from_sources,
)
```

## Next boundary

A later offline executor may consume only a source-replayed `ADMITTED`
catalog artifact through the public raw-source revalidation path above, re-open
the required SportyBet, Terms, Sportradar, and FotMob source evidence, assemble
PR #164's `FullUtcReconciliationSourceBundle`, and execute/store the real
reconciliation receipt.

Only a resulting `UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED` receipt may advance
to SportyBet canonical market/selection mapping.
