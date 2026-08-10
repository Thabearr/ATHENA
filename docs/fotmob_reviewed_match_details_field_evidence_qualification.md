# Reviewed FotMob match-details field-evidence qualification

## Purpose

PR #58 is the next trust boundary after merged PR #57.

It records an explicit human qualification decision for **each exact PR #57 UNVERIFIED fact observation** after replaying the complete preserved evidence chain.

```text
PR #52 exact persisted match-details evidence
→ PR #53 strict structural assessment
→ PR #54 explicit scalar semantics review
→ PR #55 exact scalar extraction candidates, UNVERIFIED
→ PR #57 PR #30 fact representation, still UNVERIFIED
→ PR #58 exact-observation field-evidence qualification
```

PR #58 deliberately does **not** change fact status.

A `QUALIFIED` decision means only:

> this exact reviewed observation is eligible to enter a later, separately reviewed status-classification boundary.

It does not mean that FotMob is globally qualified for that field, that future responses are automatically trusted, or that the fact is currently `SUPPORTED`.

## Why the scope is exact-observation only

The current reviewed match-details work is based on exact preserved captures and explicit human field review. That is not enough evidence to make a provider-wide statement such as "this FotMob path is always reliable for every fixture and time."

PR #58 therefore freezes the scope string:

```text
EXACT_OBSERVATION_ONLY
```

The global `SOURCE_CAPABILITY_REGISTRY` is not modified or imported by this boundary.

A future source-wide capability would require its own reviewed protocol and evidence. It must not be inferred from PR #58 records.

## Full-chain input

`build_reviewed_match_details_field_evidence_qualification(...)` requires the same complete chain used to trust PR #57:

- PR #52 verified persisted evidence and exact receipt bytes;
- exact historical `manifest.json` and `response.json` bytes;
- PR #53 structural assessment and exact canonical bytes;
- PR #54 field-semantics review and exact canonical bytes;
- PR #57 UNVERIFIED fact bundle and exact canonical bytes.

The builder calls PR #57's full-chain revalidator before any qualification decision is recorded.

Changing a scalar, source reference, evidence SHA, fixture identity, raw bytes, review decision, or PR #57 canonical bytes therefore fails before PR #58 can be rebuilt.

## Explicit reviewer decisions

Every exact PR #57 fact must have exactly one review decision.

The decision key is:

```text
(category, field, source_reference)
```

Allowed dispositions are:

- `QUALIFIED`
- `REJECTED`

There is no implicit default.

Omitting a fact, supplying an extra invented fact, duplicating a decision, or changing decision ordering fails closed.

Every decision requires a non-empty reviewer rationale.

The PR #58 artifact records a SHA-256 of each exact canonical PR #30 fact payload so the decision is tied to the exact scalar, status, provider, role, source reference, observation time, evidence path, evidence SHA and notes present in PR #57.

## Prospective chronology

PR #58 depends on both the raw observation and PR #54's semantic review, so its timestamps must preserve that ancestry.

The exact chronology is:

```text
observed_at
≤ semantic_reviewed_at
≤ qualification reviewed_at
< kickoff
```

All three timestamps must already use exact `datetime.timezone.utc`.

The PR #54 `reviewed_at` is carried into the detached PR #58 artifact as `semantic_reviewed_at`. A qualification record cannot claim to predate the semantic review it depends on, and a review at or after kickoff cannot be used prospectively.

## Detached qualification artifact

`ReviewedMatchDetailsFieldEvidenceQualification` stores detached identities only:

- PR #57 bundle SHA-256 and byte size;
- source-scoped fixture identity;
- source match ID;
- kickoff;
- observation timestamp;
- PR #54 semantic-review timestamp;
- raw response SHA-256;
- exact logical `response.json` evidence path;
- source provider and `PRIMARY_FOOTBALL_CONTEXT` role;
- PR #58 review timestamp and reviewer reference;
- one recorded decision per exact PR #57 fact;
- qualified and rejected counts;
- all safety flags exact `false`.

The artifact does not embed or create new Fixture Intelligence facts.

The logical evidence path is recomputed from the detached source match ID, exact UTC observation timestamp and raw SHA-256 using the same PR #51 durable-capture identity:

```text
.cache/athena-research/fotmob-reviewed-match-details-captures/
  <source_match_id>--<UTC observed_at>--<raw_sha256>/response.json
```

A detached path mutation therefore fails local canonicalization even before full-chain replay. Recorded source references are likewise required to remain scoped to the exact source match ID.

Historical canonical bytes are deterministic UTF-8 JSON using sorted keys, compact separators, `allow_nan=False`, and exactly one trailing newline.

## Full-chain revalidation

Local artifact invariants prove that a PR #58 object is structurally self-consistent. They do not independently prove that a changed in-memory decision still corresponds to the original raw evidence.

`revalidate_reviewed_match_details_field_evidence_qualification(...)` is therefore the legal consumption boundary.

It requires:

- the exact PR #52→#57 inputs;
- the supplied PR #58 object;
- the exact caller-presented canonical PR #58 bytes.

The revalidator rebuilds PR #58 from the full evidence chain and requires:

```text
supplied PR #58 canonical bytes
== exact full-chain rebuild bytes
== caller-presented PR #58 bytes
```

A PR #58 record cannot be reused for a different raw observation, even if the fixture/path/category/field look similar.

## Status remains UNVERIFIED

PR #58 does not construct a replacement fact and does not mutate PR #57.

All input facts remain:

```text
status = UNVERIFIED
```

A later PR may define exact status-classification rules using a successfully revalidated PR #58 record. That later boundary must independently decide freshness, conflicts and the resulting `SUPPORTED`, `STALE`, `CONFLICTED` or remaining `UNVERIFIED` state.

PR #58 itself cannot make a PR #31 model feature AVAILABLE.

## Explicit non-authorizations

PR #58 authorizes none of the following:

- source-wide qualification;
- automatic status classification;
- `SUPPORTED` status;
- Fixture Intelligence snapshot creation;
- model feature availability;
- probability inference;
- pricing;
- selection;
- betting;
- network acquisition.

All safety flags are immutable exact `false`.

## Next boundary

The next safe step is a **status-classification policy** that consumes the whole exact PR #58 handoff and preserves fixture identity, freshness and conflict semantics.

That future boundary must fail closed when qualification is rejected, evidence is stale, supported values conflict, or the exact upstream chain cannot be replayed. It must not silently turn a `QUALIFIED` review decision into a blanket provider capability.
