# Reviewed FotMob match-details UNVERIFIED fact candidates

## Purpose

PR #55 is the first boundary in the reviewed `/api/matchDetails` chain that may construct `FixtureIntelligenceFact` objects. It is intentionally limited to **UNVERIFIED** candidates.

The chain is:

```text
PR #51 exact durable raw evidence
→ PR #52 persisted evidence verification
→ PR #53 strict structural assessment
→ PR #54 explicit human field-semantics review
→ PR #55 exact scalar resolution → UNVERIFIED FixtureIntelligenceFact candidates
```

PR #55 does not qualify FotMob semantic capabilities and can never emit `SUPPORTED` facts.

## Exact ancestry

`build_reviewed_match_details_fact_candidates(...)` requires the complete byte/object chain:

- exact PR #52 evidence object;
- exact PR #52 canonical receipt bytes;
- exact persisted manifest bytes;
- exact persisted raw response bytes;
- exact PR #53 structure object;
- exact PR #53 canonical bytes;
- exact PR #54 field-review object;
- exact PR #54 canonical bytes.

The builder reconstructs PR #54 from the underlying PR #52/PR #53 inputs and requires both the supplied PR #54 object and supplied PR #54 bytes to match the exact rebuild. A mutated or detached semantic review cannot silently reach extraction.

## Extraction rules

Only PR #54 decisions with disposition `APPROVED` are eligible. At least one approved decision is required.

The exact raw response body is parsed again with the same strict safety posture:

- strict UTF-8 JSON object;
- duplicate keys rejected;
- NaN/Infinity constants rejected;
- non-finite numeric values rejected.

Each approved path is resolved literally through object keys only. There are no aliases, defaults, fuzzy matches, fallbacks, value coercions, or missing-value inference.

PR #53 structural escaping is decoded exactly:

- `~0` → literal `~`;
- `~1` → literal `/`;
- `~2` → literal `*`;
- the reserved wildcard segment `*` is rejected.

The runtime value must be the exact scalar kind approved in PR #54: STRING, INTEGER, NUMBER, or BOOLEAN. Null, arrays, objects, missing paths, and type drift fail closed.

## Fixture Intelligence candidate

Every extracted value becomes one `FixtureIntelligenceFact` with:

- the exact PR #54 `IntelligenceCategory` and field name;
- status **`UNVERIFIED`**;
- exact scalar value from the preserved raw bytes;
- `source_provider = "fotmob_match_details_reviewed"`;
- `source_role = PRIMARY_FOOTBALL_CONTEXT`;
- source reference `/api/matchDetails?matchId=<source id>#<reviewed structural path>`;
- `observed_at` equal to the PR #52 evidence observation time;
- exact PR #51 `response.json` logical evidence path;
- evidence SHA-256 equal to the exact preserved raw response SHA-256;
- notes explicitly stating that source semantic capability remains unqualified and the value remains UNVERIFIED.

`PRIMARY_FOOTBALL_CONTEXT` identifies the intended source role only. It does not imply that the field is source-qualified or supported.

## Detached bundle hardening

`ReviewedMatchDetailsFactCandidates` also locks its internal historical identity:

- source-scoped `FOTMOB:<id>` must match `source_match_id`;
- kickoff, evidence observation time, and human review time use exact UTC;
- observation and review remain strictly pre-kickoff;
- review cannot predate evidence observation;
- the PR #51 evidence path must exactly match `<source id>--<observation timestamp>--<raw SHA>/response.json` under the reviewed research-cache root;
- every fact must share the exact observation time, evidence path, and raw SHA;
- every fact value must remain an exact finite non-null scalar;
- every source reference must remain on the exact reviewed match-details ID and contain no array wildcard;
- semantic category/field targets are unique;
- every fact status must remain exactly `UNVERIFIED`.

The bundle has deterministic canonical JSON bytes and SHA-256. A future consumer that wants to trust the bundle must still replay this PR #55 builder from the exact upstream artifacts; the detached bundle is not a substitute for ancestry verification.

## What PR #55 does not authorize

All downstream authorization remains false. In particular PR #55 does **not** authorize:

- `SUPPORTED` Fixture Intelligence facts;
- source-capability confirmation for any match-details semantic field;
- Fixture Intelligence snapshot admission;
- model features;
- probability generation;
- pricing;
- selection;
- betting.

Real FotMob fields must first be captured in actual PR #51 evidence and explicitly reviewed under PR #54. Synthetic test mappings such as `/alpha/value` exist only to test the contract and confer no football meaning.

## Next safe step after PR #55

The next semantic milestone should be based on **actual preserved match-details captures**, not synthetic assumptions: run the reviewed capture workflow on admitted prospective fixtures, assess their real PR #53 structure, and create explicit human PR #54 review decisions. Only after repeated real evidence supports a narrow semantic capability should ATHENA consider a separate source-capability qualification boundary that could eventually allow selected facts to advance beyond `UNVERIFIED`.
