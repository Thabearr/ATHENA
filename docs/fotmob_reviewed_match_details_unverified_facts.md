# Reviewed FotMob match-details UNVERIFIED fact adapter

## Purpose

PR #57 is a narrow status-preserving adapter after merged PR #55.

It converts exact PR #55 reviewed extraction candidates into existing PR #30 `FixtureIntelligenceFact` objects while keeping every fact at `UNVERIFIED`.

```text
PR #52 exact persisted match-details evidence
→ PR #53 strict structural assessment
→ PR #54 explicit human scalar semantics
→ PR #55 exact scalar extraction candidates, still UNVERIFIED
→ PR #57 PR #30 fact representation, still UNVERIFIED
```

PR #57 is not source qualification and is not a `SUPPORTED`-fact promotion boundary.

## Full-chain revalidation

`build_reviewed_match_details_unverified_fact_bundle(...)` requires the complete exact PR #52→#55 chain:

- PR #52 verified persisted evidence and exact receipt bytes;
- exact `manifest.json` and `response.json` bytes;
- PR #53 structural assessment and exact canonical bytes;
- PR #54 field-semantics review and exact canonical bytes;
- PR #55 candidate bundle and exact canonical bytes.

The builder reruns the PR #55 builder, which reruns the earlier trust chain. The supplied PR #55 object, exact semantic rebuild, and caller-presented PR #55 bytes must agree exactly.

Changing an extracted scalar while keeping a structurally valid candidate therefore does not survive PR #57 admission: the candidate value is compared against the exact re-extraction from the original raw bytes.

## Exact fact mapping

For every PR #55 candidate, PR #57 creates exactly one `FixtureIntelligenceFact` with:

- the same category;
- the same field;
- the same scalar value;
- `status = UNVERIFIED`;
- the same source provider;
- the same `PRIMARY_FOOTBALL_CONTEXT` source role;
- the same source-scoped reference;
- the same observation timestamp;
- the same raw-evidence SHA-256;
- `notes = None`.

There is no defaulting, coercion, normalization of football meaning, aliasing, fuzzy matching, conflict resolution, freshness promotion, or status upgrade.

## Evidence file path

PR #30 facts require a relative `evidence_file_path`.

PR #57 does not accept a caller-selected path. It derives the exact logical raw-evidence path from the already verified PR #50 durable-capture identity:

```text
.cache/athena-research/fotmob-reviewed-match-details-captures/
  <source_match_id>--<observed_at>--<raw_sha256>/response.json
```

The timestamp formatting and identifier construction match PR #50's durable writer contract. The path therefore points to the exact raw bytes whose SHA-256 is already anchored through PR #52→#55.

## Self-validation

`ReviewedMatchDetailsUnverifiedFactBundle` embeds the exact PR #55 candidate bundle plus the mapped PR #30 facts.

On construction and canonicalization it:

- reconstructs the embedded PR #55 candidate bundle through its own invariants;
- verifies candidate-bundle canonical size and SHA-256;
- recomputes the exact PR #50 evidence path;
- reconstructs every nested PR #30 fact;
- regenerates the expected facts from the embedded candidates;
- requires exact one-to-one semantic equality;
- requires all safety flags to remain exact `false`.

The canonical representation is deterministic UTF-8 JSON with sorted keys, compact separators, `allow_nan=False`, and a final newline.

Canonical bundle bytes are an auditable deterministic representation, not an independent source-qualification certificate. Any later trust boundary that consumes PR #57 output must continue to preserve/revalidate upstream lineage rather than treating serialized facts as automatically trusted.

## Model behavior remains blocked

PR #31 already blocks mapped model inputs when matching evidence is only `UNVERIFIED`.

A PR #57 fact for a model-bound field therefore resolves to `BLOCKED` with `UNVERIFIED_EVIDENCE_PRESENT` and `NO_SUPPORTED_EVIDENCE`, not `AVAILABLE`.

This is intentional. PR #57 makes reviewed evidence representable inside the PR #30 fact contract; it does not make that evidence model-ready.

## Explicit non-authorizations

PR #57 does not authorize:

- network acquisition;
- source qualification;
- `SUPPORTED` status;
- Fixture Intelligence snapshot creation;
- model feature availability;
- probability inference;
- pricing;
- selection;
- betting.

Every adapter safety flag remains exact `false`.

## Next boundary

A later PR may decide whether and under what independently reviewed conditions an UNVERIFIED fact can become `SUPPORTED`, `STALE`, or `CONFLICTED` and enter a Fixture Intelligence snapshot. That future boundary must preserve conflict/freshness/unknown semantics and must not silently upgrade source trust.
