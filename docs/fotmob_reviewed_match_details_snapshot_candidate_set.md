# Reviewed FotMob match-details snapshot candidate set

## Purpose

PR #63 combines an explicit non-empty set of exact PR #62 fact-status
materializations for one FotMob fixture at one exact prospective
classification time.  It is a lossless candidate-set boundary, not Fixture
Intelligence snapshot admission.

```text
PR #52 persisted evidence -> ... -> PR #61 prospective evaluation
    -> PR #62 status-only PR #30 facts
    -> PR #63 explicit revalidated candidate set
    -> later reviewed snapshot-admission decision
```

The dataset is
`athena-fotmob-reviewed-match-details-snapshot-candidate-set-v1`, schema
version exact integer `1`, with scope
`EXPLICIT_REVALIDATED_MATERIALIZATION_SET_ONLY`.

## Exact input and replay

Each execution-only input wrapper carries the full arguments needed by
`revalidate_reviewed_match_details_fact_status_materialization(...)`.  It is
not itself a detached trust artifact: the PR #52→PR #62 chain is replayed for
every member before aggregation.

The resulting candidate set records each exact PR #62 canonical SHA-256 and
byte size, PR #57 fact-bundle SHA-256, PR #61 evaluation SHA-256, fixture and
classification anchors, status counts, and complete materialized-fact hashes.
It also records deterministic per-fact lineage containing the PR #62 member
SHA, original PR #57 fact SHA, complete materialized fact SHA, category,
field, source reference, and exact status.

Full PR #63 revalidation reconstructs every member from the PR #52→PR #62
chain, rebuilds the candidate set, and requires both the supplied object and
supplied immutable bytes to equal rebuilt canonical bytes.  A local hash or a
detached PR #62 object is not authority.

## Shared classification moment

Every member must agree exactly on:

- `fixture_identifier`;
- `source_match_id`;
- `kickoff`;
- `classified_at`.

`classified_at` remains strictly before kickoff.  Mixing classifications made
at different times is rejected: `SUPPORTED` and `STALE` are PR #61
prospective outcomes, so combining different freshness moments would falsely
create one snapshot moment.  PR #63 neither chooses the earliest/latest time
nor reevaluates freshness.

## Lossless facts, no conflict decision

Every materialized PR #30 fact is flattened into the candidate set.  No fact
is selected, deduplicated, normalized, transformed, or reconciled.  Distinct
materializations remain distinct even where values happen to be equal.

If two fresh observations have different `SUPPORTED` values for one
category/field, both remain.  PR #63 does not assign `CONFLICTED`; the future
PR #30 snapshot boundary must include the explicit candidate set before PR
#30 can derive conflicts.  This avoids an arbitrary subset becoming model
input merely because it omits a conflicting observation.

The status carried by each fact remains exactly as PR #62 materialized it:

| PR #61 disposition | Preserved PR #30 status |
| --- | --- |
| `FRESH_QUALIFIED` | `SUPPORTED` |
| `STALE_QUALIFIED` | `STALE` |
| `BLOCKED_BY_QUALIFICATION` | `UNVERIFIED` |

## Explicit non-authorizations

PR #63 does not claim the candidate set is complete across captures, sources,
or football evidence.  It does not qualify FotMob globally or make an
observation model-ready.  It does not construct or import
`FixtureIntelligenceSnapshot`, `build_snapshot`,
`build_model_feature_snapshot`, or a model-feature snapshot.

All safety flags remain exact `false`, including network acquisition,
source-wide qualification, source identity resolution, snapshot admission,
snapshot creation, conflict resolution, model features, probability, pricing,
selection, production approval, and betting.

The candidate set has no filesystem or network behavior.  It preserves
observations only; it creates no catalog records, probabilities, prices,
selections, or bets.  `fotmob_unofficial` remains `UNKNOWN` in the source
capability registry.

## Canonicalization and mutation resistance

Canonical bytes are compact sorted-key UTF-8 JSON with `allow_nan=False` and
exactly one trailing newline.  Canonicalization reconstructs nested facts,
member records, and fact-lineage records.  It verifies that every flattened
fact hashes both to its recorded complete materialized fact hash and, after
only status is projected back to `UNVERIFIED`, to its recorded original PR #57
fact hash.

Therefore forced changes to a fact value, status, evidence SHA, source
reference, category, or field fail local validation.  Coordinated mutations
to an upstream PR #62 artifact and the local candidate artifact still fail
the full PR #52→PR #63 replay.
