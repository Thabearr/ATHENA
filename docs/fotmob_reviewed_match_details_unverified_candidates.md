# Reviewed FotMob match-details UNVERIFIED extraction candidates

## Purpose

PR #55 is the first exact-value extraction boundary for reviewed `/api/matchDetails` evidence.

It does **not** create `FixtureIntelligenceFact` objects. It converts only explicit PR #54-approved, non-wildcard scalar mappings into provenance-backed candidates whose status is fixed to `UNVERIFIED`.

```text
PR #52 exact persisted bytes
→ PR #53 strict structure
→ PR #54 explicit human scalar semantics
→ PR #55 exact scalar extraction as UNVERIFIED candidates
```

## Full-chain revalidation

`build_reviewed_match_details_unverified_candidates(...)` receives the complete exact chain:

- PR #52 verified evidence + exact receipt bytes;
- exact `manifest.json` + `response.json` bytes;
- PR #53 structural assessment + exact canonical bytes;
- PR #54 human field-semantics review + exact canonical bytes.

PR #55 reruns the PR #54 builder, which reruns PR #53 and its PR #52 evidence verification. The supplied review object, rebuilt review, and caller-presented review bytes must be byte-identical after canonicalization.

A stale, mutated, reserialized, or raw-byte-mismatched review therefore cannot authorize extraction.

## Extraction rules

Only PR #54 `APPROVED` decisions are considered. PR #54 already restricts approval to:

- one exact non-root structural path;
- no array wildcard;
- exactly one observed kind;
- STRING, INTEGER, NUMBER or BOOLEAN only;
- a unique Fixture Intelligence category/field semantic target.

PR #55 reparses the exact raw bytes using strict UTF-8 finite JSON rules, rejects duplicate keys and non-finite constants, decodes the PR #53 JSON-pointer contract (`~0`, `~1`, and literal-star `~2`), traverses object keys exactly, and requires the extracted raw value kind to equal the PR #54-approved kind.

There is no defaulting, coercion, clamping, fuzzy path lookup, aliasing, array flattening, or fallback.

A review containing only REJECTED decisions does not produce an empty candidate artifact; extraction fails explicitly because no field was approved.

## Candidate semantics

Each `UnverifiedMatchDetailsCandidate` records:

- exact Fixture Intelligence category and logical field approved in PR #54;
- exact scalar value and JSON kind;
- exact structural JSON pointer;
- `status = UNVERIFIED`;
- source provider `fotmob_match_details_reviewed`;
- source role `PRIMARY_FOOTBALL_CONTEXT`;
- source-scoped reference containing the FotMob match ID and exact pointer;
- original evidence observation time;
- exact raw-evidence SHA-256.

The containing bundle also anchors PR #54 review SHA-256, PR #53 structure SHA-256, PR #52 receipt SHA-256, manifest/raw hashes, fixture identity, source match ID, observation time and kickoff.

## What UNVERIFIED means here

A human-reviewed path meaning plus exact extraction is **not yet factual support**.

PR #55 does not establish:

- broad source qualification;
- current-value freshness beyond the captured observation timestamp;
- corroboration;
- conflict resolution;
- `SUPPORTED` status;
- Fixture Intelligence snapshot admission;
- model-feature readiness.

A later boundary must decide whether a candidate can become a PR #30 fact and must preserve STALE/CONFLICTED/UNVERIFIED outcomes rather than silently upgrading it.

## Safety

PR #55 cannot authorize source qualification, `SUPPORTED` status, Fixture Intelligence fact promotion/snapshot creation, model features, probabilities, pricing, selection or betting. Every safety flag remains exact `false`.
