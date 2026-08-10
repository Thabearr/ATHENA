# FotMob reviewed fixture-catalog handoff

## Purpose

PR #42 adds the next narrow offline trust boundary after PR #41.

PR #40 produces provenance-backed `UNREVIEWED` FotMob candidates. PR #41 requires explicit review decisions before any candidate can be projected into the strict PR #29 Fixture Catalog input schema. PR #42 does **not** compile or publish that catalog. It proves that the supplied PR #41 review bundle still derives exactly from the supplied PR #40 candidate bundle and its explicit decisions before exposing deterministic PR #29-compatible JSONL bytes.

The chain is now:

```text
verified PR #38 capture
    -> PR #39 schema assessment
    -> PR #40 UNREVIEWED candidate bundle
    -> PR #41 explicit per-candidate review gate
    -> PR #42 self-validating reviewed catalog handoff   <-- this boundary
    -> later explicit PR #29 compiler invocation
    -> later catalog publication/promotion boundary
```

## Why this extra boundary exists

A frozen dataclass prevents ordinary field assignment, but it does not by itself prove that a derived object still matches its upstream evidence. A caller can construct or replace a structurally valid review bundle while altering derived catalog fields or the claimed upstream candidate-bundle hash.

PR #42 closes that handoff gap by requiring both immutable objects:

- the exact PR #40 `FotMobFixtureCandidateBundle`;
- the exact PR #41 `FotMobFixtureCandidateReviewBundle`.

The handoff recomputes the PR #40 candidate-bundle SHA-256 and requires it to equal the review bundle's claimed `candidate_bundle_sha256`. It then rebuilds the entire PR #41 review bundle from the candidate bundle plus the review bundle's explicit decision tuple and compares canonical review-bundle bytes exactly.

If any approved team name, competition, kickoff, evidence SHA-256, evidence path, review metadata, blocker result, count, source ancestry, or other serialized review result no longer matches what PR #41 deterministically derives, handoff fails closed.

## Explicit approvals only

A catalog handoff requires at least one explicit approved PR #41 catalog input.

- zero decisions cannot create a handoff;
- rejected-only decisions cannot create a handoff;
- blocked candidates still cannot be approved because PR #41 remains the review gate;
- an unreviewed candidate is never silently converted to approved;
- a partial review remains visibly partial through the candidate, decision, approved, rejected, unreviewed, and blocked counts recorded in the handoff summary.

PR #42 does not introduce an `approve all` operation, confidence threshold, fuzzy matching rule, preferred source variant, or automatic conflict resolution.

## PR #29-compatible input bytes

For each exact PR #41 approved input, PR #42 calls its existing `to_catalog_input_dict()` projection and requires the key set to remain exactly PR #29's `INPUT_RECORD_KEYS`.

The emitted JSONL uses PR #29's canonical JSON-line serializer:

- UTF-8;
- sorted keys;
- compact separators;
- no NaN or Infinity;
- exactly one final newline per record.

Duplicate `source_fixture_identifier` values fail closed at the handoff even though PR #41 already blocks repeated source match IDs. This is deliberate defense in depth before the later PR #29 compiler repeats its own duplicate checks.

The handoff summary records:

- candidate-bundle SHA-256;
- review-bundle SHA-256;
- source capture count;
- candidate count;
- decision count;
- approved count;
- rejected count;
- unreviewed count;
- blocked candidate count;
- emitted catalog-input count;
- exact catalog-input byte size;
- exact catalog-input SHA-256;
- the exact PR #29-compatible catalog-input records;
- an all-false downstream safety map.

## What PR #42 does not do

PR #42 deliberately does **not**:

- make any network request;
- recapture or modify FotMob raw evidence;
- parse new FotMob football semantics;
- qualify FotMob globally;
- resolve the known source-team ID `394121` conflict;
- canonicalize team or competition identity;
- call `compile_fixture_catalog()`;
- write a Fixture Catalog;
- publish or promote a Fixture Catalog;
- authorize Fixture Intelligence;
- create model features;
- run probability models;
- obtain bookmaker prices;
- select bets or accumulators;
- authorize a `BET` decision.

The handoff operation only produces deterministic in-memory PR #29 input bytes and an auditable canonical handoff representation.

## Safety contract

All downstream authorization fields are exact boolean `false`, including:

- source qualification;
- team, competition, and fixture identity resolution;
- Fixture Catalog compilation;
- Fixture Catalog writes;
- Fixture Catalog promotion;
- Fixture Intelligence;
- model features;
- probabilities;
- pricing;
- selection;
- betting.

The safety mapping is detached and immutable.

## Next boundary

A later PR may add the operator-facing offline workflow that reads an explicit review-decision artifact, rebuilds the candidate and review bundles from preserved local captures, creates this handoff, and invokes the already-hardened PR #29 compiler against the exact handoff JSONL bytes.

That later workflow must preserve the candidate-bundle SHA-256, review-bundle SHA-256, handoff SHA-256, PR #29 normalized-input SHA-256, exact raw evidence ancestry, and the same fail-closed path/output protections. It must remain separately reviewed and must not imply Fixture Catalog promotion, Fixture Intelligence readiness, model readiness, pricing readiness, or betting authorization.
