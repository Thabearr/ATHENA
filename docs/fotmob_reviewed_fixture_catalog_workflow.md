# FotMob reviewed Fixture Catalog workflow

## Purpose

PR #43 adds the operator-facing offline workflow that connects the already-reviewed trust boundaries without skipping any of them.

The chain is now:

```text
verified PR #38 capture
    -> PR #39 offline schema assessment
    -> PR #40 UNREVIEWED candidate bundle
    -> PR #41 explicit candidate review
    -> PR #42 self-validating reviewed handoff
    -> PR #43 explicit offline PR #29 compiler invocation   <-- this boundary
    -> later catalog promotion / trusted downstream use
```

PR #43 is the first boundary in this chain that is allowed to **compile and, when explicitly requested, write** a Fixture Catalog plus its provenance manifest. Compilation is not promotion. The resulting files remain research/audit outputs until a later separately reviewed boundary authorizes trusted downstream use.

## Inputs

The workflow requires:

1. one or more preserved PR #38 `/api/data/matches` capture directories beneath the fixed ignored research root;
2. one explicit review-decision ledger;
3. an `as_of` timestamp and optional minimum lead-time requirement for PR #29;
4. either generation destinations for both catalog and manifest, or check paths for both existing outputs.

No network acquisition occurs in this workflow.

## Explicit decision ledger

The decision ledger is strict JSON with exactly four top-level keys:

```json
{
  "schema_version": 1,
  "dataset_name": "athena-fotmob-fixture-review-decision-ledger-v1",
  "candidate_bundle_sha256": "<64 lowercase hex>",
  "decisions": []
}
```

Every item in `decisions` has exactly the fields already defined by PR #41:

- `source_capture_manifest_sha256`
- `source_match_id`
- `candidate_sha256`
- `disposition`
- `reviewed_at`
- `reviewer_reference`
- `notes`

`disposition` is only `APPROVED` or `REJECTED`.

The ledger is deliberately not an approve-all mechanism. Every reviewed candidate is named by exact capture manifest SHA-256, exact source match ID, and exact candidate SHA-256. The ledger also anchors the SHA-256 of the complete rebuilt PR #40 candidate bundle. If the preserved captures rebuild to a different candidate bundle, the ledger fails closed before PR #41 review state is constructed.

The parser rejects duplicate JSON keys, non-finite JSON constants, schema drift, invalid types, malformed timestamps, noncanonical hashes, symlinks, concurrent file changes while reading, and oversized ledgers.

## Rebuild sequence

PR #43 never trusts a serialized derived review or handoff object supplied by the operator.

For every invocation it:

1. verifies the supplied local capture directories using the existing PR #38 capture verifier;
2. independently reads and hashes the exact raw response bytes;
3. reruns the PR #39 schema assessment through the PR #40 candidate builder;
4. rebuilds the complete deterministic PR #40 candidate bundle;
5. requires the decision ledger's `candidate_bundle_sha256` to equal that exact rebuilt bundle;
6. reconstructs PR #41 review decisions as typed domain objects;
7. reruns the PR #41 explicit review gate, including all duplicate/conflict/catalog-string blockers;
8. rebuilds the PR #42 handoff and reruns its exact candidate/review self-validation;
9. materializes only the exact PR #42 catalog-input JSONL bytes into a temporary ignored research file;
10. invokes the already-hardened PR #29 Fixture Catalog compiler against those exact bytes and the preserved capture root;
11. verifies the PR #29 normalized records still match every reviewed PR #42 input field;
12. removes the temporary handoff input after success or failure.

No review bundle, handoff bundle, catalog row, or evidence hash is accepted merely because it is structurally valid.

## PR #29 remains authoritative

PR #43 does not weaken or duplicate away the PR #29 gates.

The existing compiler still independently enforces:

- exact input keys and source `FOTMOB`;
- strict UTF-8 JSON Lines;
- duplicate rejection;
- exact evidence-file existence beneath the evidence root;
- evidence SHA-256 equality;
- `reviewed_at <= as_of`;
- minimum lead time before kickoff;
- full Git generator SHA;
- clean tracked worktree;
- deterministic normalized input, catalog, and manifest bytes.

The existing `scripts/manage_fixture_catalog.py` output protections also remain authoritative for generation/check mode, tracked-file refusal, output-root restrictions inside the repository, symlink rejection, no-overwrite behavior, atomic writes, durability, rollback, and preserved manual-recovery artifacts when rollback cannot be proven.

## Workflow receipt

A successful invocation emits one canonical JSON summary to stdout. It records:

- exact decision-ledger SHA-256;
- exact PR #40 candidate-bundle SHA-256;
- exact PR #41 review-bundle SHA-256;
- exact PR #42 handoff SHA-256;
- exact PR #42 catalog-input SHA-256;
- exact PR #29 normalized-input SHA-256;
- final catalog SHA-256;
- final manifest SHA-256;
- source/candidate/review/block/fixture counts;
- `as_of` and minimum lead time;
- generation versus check mode.

The receipt distinguishes facts about this explicit operation from authorization semantics. It records that catalog compilation occurred and whether output writes occurred, while source qualification, identity resolution, catalog promotion, Fixture Intelligence, model features, probabilities, pricing, selection, and betting all remain false.

## Generate mode

Example shape:

```text
python scripts/manage_fotmob_reviewed_fixture_catalog.py \
  --capture-directory .cache/athena-research/fotmob-data-matches-captures/<date>/<capture> \
  --decision-ledger .cache/athena-research/fotmob-review-decisions/review.json \
  --as-of 2026-08-10T03:00:00Z \
  --catalog-output .cache/athena-research/fixture-catalog/catalog.json \
  --manifest-output .cache/athena-research/fixture-catalog/manifest.json
```

Additional `--capture-directory` arguments may be repeated. `--force` retains PR #29 semantics and may replace only destinations that PR #29 already permits replacing.

## Check mode

The same evidence and decision ledger can verify previously generated bytes without writing new outputs:

```text
python scripts/manage_fotmob_reviewed_fixture_catalog.py \
  --capture-directory <capture> \
  --decision-ledger <review.json> \
  --as-of 2026-08-10T03:00:00Z \
  --check-catalog <catalog.json> \
  --check-manifest <manifest.json>
```

Generation and check modes are mutually exclusive through the existing PR #29 workflow contract, and both catalog/manifest paths are required for the selected mode.

## What PR #43 explicitly does not do

PR #43 does **not**:

- make a network request;
- recapture FotMob data;
- fabricate or automatically create review decisions;
- resolve the known source-team ID `394121` conflict;
- normalize, alias, or fuzzy-match team identities;
- canonicalize competition identities;
- qualify FotMob as a trusted global source;
- promote the compiled catalog into trusted Fixture Intelligence;
- populate model features;
- run probability models;
- obtain or reconcile SportyBet prices;
- choose markets, bets, or accumulators;
- authorize `BET`.

A compiled Fixture Catalog is therefore an auditable reviewed research artifact, not downstream authority.

## Next boundary

After PR #43, the fixture-backbone work has a complete explicit evidence-to-compiled-catalog path. The next PR should remain narrow and separately decide how a compiled catalog is **promoted/registered for trusted Fixture Catalog use** while preserving its catalog/manifest hashes, exact reviewed ancestry, source capability state, and conflict visibility.

That promotion boundary must not automatically authorize Fixture Intelligence facts, model-ready features, probabilities, bookmaker pricing, or betting. Those remain later independent trust boundaries.
