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

## Fixture identity binding

The existing PR #30 `FixtureIntelligenceFact` type does **not** contain a fixture identifier or kickoff. Therefore the naked `facts` tuple is not an independently fixture-bound handoff.

The legal PR #57 handoff is the **whole** `ReviewedMatchDetailsUnverifiedFactBundle`. It embeds the exact PR #55 candidate bundle and exposes these identities only as derived read-only properties:

- `fixture_identifier`;
- `source_match_id`;
- `kickoff`;
- `observed_at`;
- `raw_sha256`.

Those same derived identities are emitted at the top level of canonical PR #57 JSON and must agree with the embedded PR #55 bundle by construction.

A future Fixture Intelligence snapshot boundary must consume/revalidate the whole PR #57 bundle and take fixture identity and kickoff from that bundle. It must not accept a caller-selected fixture identity for these facts and must not treat the facts as reusable across fixtures.

## Evidence file path

PR #30 facts require a relative `evidence_file_path`.

PR #57 does not accept a caller-selected path. It derives the exact logical raw-evidence path used by PR #51 durable publication from the already verified PR #50 capture identity:

```text
.cache/athena-research/fotmob-reviewed-match-details-captures/
  <source_match_id>--<UTC observation timestamp>--<raw_sha256>/response.json
```

The timestamp formatting and identifier construction match the PR #50 capture identifier and the PR #51 durable writer contract. PR #52 then verifies the exact persisted `response.json`/`manifest.json` bytes from that historical publication before PR #53→#55 consume them.

## Self-validation

`ReviewedMatchDetailsUnverifiedFactBundle` embeds the exact PR #55 candidate bundle plus the mapped PR #30 facts.

On construction and canonicalization it:

- reconstructs the embedded PR #55 candidate bundle through its own invariants;
- verifies candidate-bundle canonical size and SHA-256;
- derives fixture/source/kickoff/observation/raw identity from the embedded PR #55 bundle;
- recomputes the exact PR #51 logical evidence path;
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

A later PR must first define the reviewed field/source qualification, freshness and conflict policy required to classify these facts as `SUPPORTED`, `STALE`, or `CONFLICTED`. Only after that may a bundle-aware snapshot boundary admit the resulting facts. Unknown, stale and conflicting evidence must remain explicit; no future step may silently upgrade trust.
