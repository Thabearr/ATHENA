# Reviewed Fixture Intelligence bootstrap artifact verification

## Purpose

PR #48 adds a read-only verification boundary after PR #47's reviewed Fixture Intelligence identity bootstrap.

The reviewed fixture path is now:

```text
verified PR #38 raw capture
→ PR #39 schema assessment
→ PR #40 UNREVIEWED fixture candidates
→ PR #41 explicit candidate review
→ PR #42 reviewed catalog handoff
→ PR #43 controlled PR #29 compiler workflow
→ PR #44 reviewed identity-only source capability
→ PR #45 explicit catalog admission
→ PR #46 exact admission-artifact verification
→ PR #47 reviewed Fixture Intelligence identity bootstrap
→ PR #48 exact bootstrap-artifact verification
→ later separately reviewed source-surface probe/capture boundaries
```

PR #48 proves that operator-presented bootstrap bytes are exactly the canonical bytes of an exact, currently revalidatable PR #47 bootstrap. It does not fetch any football data and does not make bootstrap identity into Fixture Intelligence evidence.

## Why another byte boundary is required

PR #47 is an in-memory typed boundary with deterministic canonical bytes. A later acquisition workflow should not be allowed to accept a copied `FOTMOB:<id>`, a merely type-shaped Python object, or bytes that only approximately describe the bootstrap.

Before a richer source surface is probed, ATHENA needs a receipt proving that the exact bootstrap object still satisfies the full PR #47 trust chain and that the exact bytes presented to the verifier equal its canonical representation byte-for-byte.

That is the only job of PR #48.

## Accepted input

`verify_reviewed_fixture_intelligence_bootstrap_artifact(...)` accepts:

1. an exact `ReviewedFixtureIntelligenceBootstrap` from PR #47;
2. exact immutable `bytes` claimed to be that bootstrap's canonical artifact;
3. an explicit UTC `verified_at` timestamp.

The verifier reconstructs the bootstrap with `dataclasses.replace(...)`. That reruns PR #47's complete validation, which in turn reruns the PR #46 verified-admission receipt and nested PR #45/current-capability checks.

It then requires:

- supplied PR #47 canonical object bytes = rebuilt PR #47 canonical object bytes;
- caller-presented artifact bytes = rebuilt canonical PR #47 bytes exactly;
- bootstrap SHA-256 = SHA-256 of those exact canonical bytes;
- all detached ancestry fields = the exact rebuilt PR #47 values;
- every and only PR #47 fixture identity is retained;
- `verified_at` is exact UTC and does not predate the upstream PR #46 artifact verification time;
- every safety flag remains exact `false`.

Changed whitespace, an extra newline, a missing newline, a mutated bootstrap field, a mutated nested PR #46 object, changed capability state, changed ancestry, or changed fixture set fails closed.

## Verification receipt

The receipt is `VerifiedReviewedFixtureIntelligenceBootstrapArtifact`.

It records detached audit fields only:

- PR #47 bootstrap dataset identity;
- exact PR #47 bootstrap SHA-256 and artifact byte size;
- upstream PR #46 verification-receipt SHA-256;
- PR #45 admission SHA-256;
- PR #44 reviewed source-capability key and SHA-256;
- PR #40 candidate-bundle SHA-256;
- PR #41 review-bundle SHA-256;
- PR #42 handoff SHA-256;
- PR #29 catalog and manifest SHA-256 values;
- catalog-admission review timestamp;
- upstream PR #46 artifact-verification timestamp;
- PR #48 verification timestamp;
- every and only exact PR #47 source-scoped fixture identity + kickoff;
- all-false safety mapping.

`canonical_verified_bootstrap_artifact_receipt_bytes(...)` serializes this receipt as compact sorted-key UTF-8 JSON with `allow_nan=False` and exactly one final newline. `sha256_verified_bootstrap_artifact_receipt(...)` hashes those exact receipt bytes.

## Historical determinism

The receipt deliberately serializes detached scalar/timestamp/fixture fields. It does not consult the nested PR #47 bootstrap during `to_dict()`.

Therefore a later forced mutation of a nested bootstrap or live capability-registry change cannot mutate an already-created verification receipt's canonical bytes. A new verification from the mutated or capability-revoked bootstrap still fails closed.

This separates historical auditability from current-use eligibility.

## Timing semantics

PR #48 is an artifact verifier, not a network-use authorization.

For that reason it may verify a historically valid PR #47 artifact after a fixture kickoff for audit purposes. Such a receipt still has:

`match_detail_probe_authorized = false`

A later source probe must use its own real observation time and independently require the target fixture to remain eligible/prospective for that acquisition boundary. PR #48 must not be interpreted as permission to make a network request.

## Safety boundary

Every authorization flag is immutable exact `false`, including:

- network acquisition;
- raw capture;
- artifact write;
- automatic review;
- global identity resolution;
- match-detail probing;
- Fixture Intelligence fact creation;
- Fixture Intelligence snapshot creation;
- model features;
- probabilities;
- pricing;
- selection;
- betting.

The production module imports neither `domain.fixture_intelligence` nor `domain.fixture_model_features`. It performs no HTTP request, browser operation, file write, catalog compile, runtime registration, fact construction, pricing operation, or betting operation.

## Important interpretation

**A verified bootstrap artifact proves fixture identity ancestry, not football facts.**

It does not prove form, availability, injuries, lineups, performance, xG, fatigue, weather, venue, news, scores, event timelines, or source freshness. Those require separately acquired and qualified evidence.

The raw `fotmob_unofficial` adapter remains separate and untrusted by this boundary.

## Next safe boundary

A later narrow PR may define one transparent diagnostic probe for a single richer FotMob route, using one exact fixture identity from a revalidated PR #48 receipt.

That probe should:

- use only the fixed reviewed host/path/query contract;
- make at most one explicitly authorized transparent request;
- use no cookies, browser impersonation, application signature reproduction, proxy evasion, or bypass client;
- preserve only bounded diagnostic response metadata/sample until the route itself is reviewed;
- compare its actual observation time with the fixture kickoff as part of its own current-use gate;
- keep all football semantics and Fixture Intelligence fact authorization false.

Only after preserved raw evidence and an independent schema/semantic review should any field from that richer surface be considered for PR #30 `SUPPORTED` facts.
