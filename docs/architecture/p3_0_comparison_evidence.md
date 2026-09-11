# P3.0 prospective legacy/canonical comparison evidence

## Purpose

P3.0-E1 establishes the immutable evidence boundary needed before P3.0 can
compare the supported legacy application with the SHADOW canonical
Price-All -> Router path. It is capture only: it does not compare decision
quality, select a market, alter an accumulator, or grant MAIN authority.

The recovery audit concluded `P3_0_CORPUS_BLOCKED_BY_MISSING_LINEAGE`: no
preserved row proved the same fixture and meaningful as-of state for both the
supported legacy output and canonical pricing/routing evidence. Canonical-only
receipts exist, but captured legacy `AnalysisPipeline` inputs/results and an
exact temporal join do not.

## Boundaries observed

The supported application path is:

`AccaBuilder -> AnalysisPipeline.run_pipeline_snapshot ->
MatchAnalyst.compile_master_fixture_prediction -> AccaFilter / Accumulator`.

`PredictionService -> MarketSelector.select` remains separately reachable
legacy behavior. It is not the primary `build_acca` path and is not sufficient
as the prospective P3.0 corpus by itself.

The research path remains the source-controlled SHADOW canonical core, then
canonical MarketProbabilityBundle, Price-All, and Router. P3.0-E1 records
their immutable identities when an approved caller supplies them; it does not
resolve a replacement registry, call private test helpers, or authorize MAIN.
The authority projection requires the exact five reviewed responsibilities:
provider-market semantics, Price-All, Router, Portfolio, and share-code
transport. Recording the delivery component's identity never invokes delivery.

## Explicit, default-off capture

`AnalysisPipeline.run_pipeline_snapshot(..., evidence_observer=...)` has an
optional observer seam. Normal calls omit it. When supplied, the observer sees
deep copies after the authorized legacy result and exported row are complete;
it receives the pre-gate analysis as well as the authorized result and exported
row. Its return value is ignored and an observer exception is contained. It
cannot replace a legacy result, mutate a legacy object, or change user-visible
output.

`domain.p3_0_comparison_evidence.LegacyEvidenceObserver` is an explicit,
memory-only projection for that seam. The offline
`scripts/capture_p3_0_comparison_evidence.py` packager accepts a caller-made
observation document and writes a new artifact directory. It imports no
provider, Current Shadow, delivery, authentication, wallet, or wager boundary.

No workflow is added here. A live prospective collection is a separately
authorized, post-merge bounded operation; it must reuse reviewed acquisition
boundaries and feed their already-observed non-sensitive projections into this
capture contract. It must not trigger share-code delivery or email.

## Evidence contract

Policy ID: `ATHENA_P3_0_COMPARISON_EVIDENCE_V1`, schema version 1.
The pinned schema-contract SHA-256 is
`33367636297cee01a3386923a7e5a2c1be414272c83af560eb819adf8cf3de7a`.

Canonical JSON uses UTF-8, sorted keys, compact separators, one LF, and
SHA-256. Duplicate keys, NaN, Infinity, unknown identity/timing keys, duplicate
fixture capture IDs, and tampered artifact file digests fail closed.

Each fixture stores separate legacy and canonical identity projections,
independent evidence/evaluation/quote/router times, an exact join receipt, and
a completeness receipt. Exact joins require equal fixture identity and policy;
there is no fuzzy team matching or invented kickoff tolerance. Mismatched or
unproved identities remain unresolved. A common as-of point is recorded only
when actually proven.

The bundle can preserve:

- legacy structured input plus authorized analysis/exported output;
- canonical fixture state, probability bundle, provider-semantic projection,
  quote snapshot, Price-All output, and Router output;
- canonical-core, manifest, registry, component-contract, and artifact IDs;
- source artifact references and SHA-256 values.

Rows are only `P3_0_CAPTURE_COMPLETE`, `P3_0_CAPTURE_PARTIAL`, or
`P3_0_CAPTURE_UNUSABLE`. Reasons such as `MISSING_LEGACY_CONTEXT`,
`MISSING_MARKET_PROBABILITY_BUNDLE`, `MISSING_QUOTE_OBSERVED_AT`, and
`COMMON_AS_OF_UNPROVEN` remain explicit. The contract does not emit P3.0
decision-match, severity, or "better" classifications.

## Artifact layout and safety

An artifact contains `manifest.json`, `capture-receipt.json`, `bundle.json`,
and per-fixture join/completeness/available evidence files. The manifest hashes
every emitted file. Missing inputs are not represented as invented data.

The explicit serializer accepts only plain JSON values and rejects key classes
that could carry credentials, browser/session data, authorization headers,
cookies, wallet/account values, stake/wager amounts, or share-code values. It
never serializes arbitrary object `__dict__` values.

Pre-merge tests are entirely offline. The packager performs no provider
acquisition, Current Shadow execution, fresh-holdout operation, share-code
create/reload, login, cookies, wallet activity, stake, or wager.

## Prospective-only and authority status

P3.0-E1 does not backdate, reconstruct missed historical evidence, replace a
legacy price with a later quote, or fabricate probabilities. The five canonical
component records and component authority registry remain unchanged. MAIN is
unchanged; SHADOW remains research-only.

A successful P3.0-E1 implementation does **not** satisfy P3.0. P3.0 remains
blocked until separately authorized post-merge captures create and qualify a
sufficient real corpus with exact fixture and same-as-of lineage. P3.1 has not
started.
