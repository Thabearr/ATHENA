# Admitted FotMob match-details Fixture Intelligence snapshot

## Purpose

PR #65 is the first FotMob match-details boundary that creates a real PR #30
`FixtureIntelligenceSnapshot`. It does so only after exact full replay of an
`ADMITTED` PR #64 whole candidate-set decision.

```text
PR #52 persisted evidence -> ... -> PR #63 whole candidate set
    -> PR #64 human ADMITTED decision
    -> PR #65 exact PR #30 build_snapshot
    -> later separately reviewed PR31 handoff
```

The wrapper dataset is
`athena-fotmob-reviewed-match-details-fixture-intelligence-snapshot-v1`, with
schema version exact integer `1`.

## Exact mechanical construction

The legal constructor first revalidates PR #63 through the complete PR
#52→PR #63 chain. It then revalidates PR #64 against that rebuilt candidate
and its exact canonical bytes. A `REJECTED` decision fails closed and creates
no empty, partial, placeholder, or fallback snapshot.

For an exact `ADMITTED` decision carrying the already-enforced
`NO_KNOWN_OMITTED_REVIEWED_MATERIALIZATIONS` reviewer attestation, PR #65 calls
the existing PR #30 constructor with exactly:

```text
build_snapshot(
    fixture_identifier = rebuilt_candidate.fixture_identifier,
    kickoff = rebuilt_candidate.kickoff,
    as_of = rebuilt_candidate.classified_at,
    raw_facts = every and only rebuilt_candidate.facts,
)
```

There is no caller-supplied `as_of` and no filtering API. PR #65 never uses
admission `reviewed_at`, current time, observation extrema, or a newly
evaluated freshness time as snapshot time.

The snapshot therefore represents the reviewed evidence state exactly **as
of PR #63/64 `classified_at`**, not as of the later human admission review.

## Preservation and PR #30 semantics

Every candidate fact enters PR #30 unchanged. `SUPPORTED`, `STALE`, and
`UNVERIFIED` statuses are preserved exactly. PR #65 adds no football meaning,
normalization, conversion, preference, deduplication, or reclassification.

If two facts contain differing `SUPPORTED` values for the same category and
field, both remain individually `SUPPORTED`. PR #30 mechanically derives the
field in `conflicted_fields`; PR #65 does not assign `CONFLICTED` to either
fact and does not choose a winner. PR #30 also owns fact ordering,
`CategoryCoverage`, `conflicted_fields`, `unverified_fields`, time validation,
snapshot safety, and canonical snapshot serialization.

Incomplete model-field coverage does not block snapshot construction. This is
Fixture Intelligence packaging, not a model-input filter.

## Exact ancestry wrapper

The PR #65 wrapper records:

- exact canonical PR #64 admission SHA-256 and byte size;
- exact canonical PR #63 candidate SHA-256 and byte size;
- fixture identifier, source match ID, kickoff, classified-at time, and
  admission reviewed-at provenance;
- member/fact counts;
- every materialization SHA identity and the complete ordered multiset of
  materialized-fact SHA identities;
- the actual existing PR #30 `FixtureIntelligenceSnapshot`;
- SHA-256 and byte size of `canonical_snapshot_bytes(snapshot)`;
- downstream safety flags, all exact `false`.

The source match ID remains in the wrapper because PR #30's generic snapshot
does not carry source-scoped match identity.

Local validation reconstructs nested facts and the snapshot through the
existing PR #30 invariants. Full PR #65 revalidation reruns PR #52→PR #63,
reruns PR #64 admission, rebuilds PR #30 with the exact candidate facts, and
requires both supplied wrapper object and immutable bytes to equal rebuilt
canonical bytes. A coordinated candidate/snapshot/hash mutation therefore
cannot establish reviewed ancestry.

## Model-feature boundary and safety

A naked PR #30 snapshot demonstrates PR #30 validity, but the reviewed FotMob
match-details ancestry is established only by the fully revalidated PR #65
wrapper. Existing generic PR #31 code can technically consume a valid PR #30
snapshot; a later reviewed boundary must full-revalidate this wrapper before
performing that handoff.

Production PR #65 does not invoke model-feature construction. Tests confirm
existing PR #31 behavior only: one supported mapped scalar may be available;
differing supported values are blocked as `CONFLICTED_EVIDENCE`; stale and
unverified evidence remain blocked.

The wrapper omits a misleading `snapshot_creation_authorized` flag because a
snapshot has in fact been constructed. All downstream authority remains exact
`false`, including network acquisition, source-wide qualification, source
identity resolution, conflict resolution, model features, probability,
pricing, selection, production approval, and betting.

PR #65 makes no source-wide completeness claim, performs no network or
filesystem behavior, changes no PR #30/31 code, resolves no conflict, and
authorizes no model, price, selection, or bet.
