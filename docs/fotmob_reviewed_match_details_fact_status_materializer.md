# Reviewed FotMob match-details fact-status materializer

## Purpose

PR #62 is the first reviewed boundary in the FotMob match-details chain that
may create a PR #30 `FixtureIntelligenceFact` with `SUPPORTED` or `STALE`
status. It consumes one exact, fully revalidated PR #61 evaluation and the
complete PR #52→PR #61 ancestry, then creates new PR #30 facts whose only
changed payload field is `status`.

This is exact-observation promotion, not source qualification. A supported
observation does not qualify FotMob globally, another fixture, another field,
another capture, or another endpoint.

```text
exact PR #52 persisted evidence
    -> PR #53 structure
    -> PR #54 semantic review
    -> PR #55 UNVERIFIED candidates
    -> PR #57 UNVERIFIED PR #30 facts
    -> PR #58 exact fact qualification
    -> PR #60 freshness/conflict policy
    -> PR #61 prospective evaluation
    -> PR #62 status-only new PR #30 facts
```

PR #62 creates no `FixtureIntelligenceSnapshot`, invokes no PR #31 model
feature builder, and performs no network, filesystem, catalog, probability,
pricing, selection, or betting behavior.

## Exact input and replay

The materializer accepts the complete argument set required by the merged PR
#61 revalidator, including the exact evaluation object and its exact immutable
canonical bytes. It calls
`revalidate_reviewed_match_details_status_evaluation(...)`, which replays the
PR #52→PR #61 chain and rejects a detached or locally forged decision.

It also independently calls the merged PR #57 fact-bundle revalidator. This
recovers the legal whole PR #57 bundle rather than treating naked PR #30 facts
as sufficient authority. The exact canonical PR #57 and PR #61 byte lengths
and SHA-256 values are stored in the PR #62 artifact.

Each PR #61 decision must cover exactly one original PR #57 fact. Binding uses
the SHA-256 of the complete canonical original fact payload, including its
`UNVERIFIED` status. Category, field, and source reference must also match the
fact selected by that hash. Matching by category/field alone, source reference
alone, position, or similarity is forbidden. Decisions must cover every and
only PR #57 fact.

## Status mapping

The mapping is closed and exact:

| PR #61 evaluation disposition | New PR #30 fact status |
| --- | --- |
| `FRESH_QUALIFIED` | `SUPPORTED` |
| `STALE_QUALIFIED` | `STALE` |
| `BLOCKED_BY_QUALIFICATION` | `UNVERIFIED` |

The original PR #57 object is never mutated. A new `FixtureIntelligenceFact`
is constructed while preserving exactly:

- category;
- field;
- scalar value, without conversion, trimming, rounding, normalization, or
  coercion;
- source provider and source role;
- source reference;
- observation timestamp;
- evidence path and SHA-256;
- notes.

Only status may differ, and only according to the table. PR #62 never assigns
`CONFLICTED`. Conflicts are not an individual-observation status decision.

## Conflict preservation

PR #62 materializes observations independently. It does not aggregate, choose
a winner, prefer the latest observation, or collapse equal/different values.
If two exact fresh evaluations produce differing `SUPPORTED` values for the
same category and field, both facts remain present.

The existing PR #30 snapshot derives that field as conflicted. The existing PR
#31 resolver then returns `BLOCKED` with `CONFLICTED_EVIDENCE`. A focused PR #62
integration regression proves this behavior without adding snapshot or model
logic to production PR #62 code.

## Detached artifact

Dataset:

`athena-fotmob-reviewed-match-details-fact-status-materialization-v1`

Schema version: exact integer `1`.

The immutable artifact records:

- exact materialization scope;
- source-scoped fixture identifier and source match ID;
- kickoff and explicit PR #61 classification time;
- exact PR #57 fact-bundle canonical size and SHA-256;
- exact PR #61 evaluation canonical size and SHA-256;
- every newly materialized PR #30 fact;
- one lineage record per fact containing the original PR #57 fact SHA-256,
  PR #61 disposition, and resulting PR #30 status;
- detached safety flags, all exact `false`.

For local mutation resistance, artifact validation reconstructs an
`UNVERIFIED` projection of every materialized fact and requires its canonical
SHA-256 to equal the recorded original PR #57 fact SHA-256. Consequently,
forced changes to status, value, evidence SHA, source reference, category, or
field fail local canonicalization. Full revalidation then independently
rebuilds PR #52→PR #62 and rejects coordinated upstream/local mutation even
when an attacker recomputes local PR #62 bytes.

Canonical bytes use sorted-key compact UTF-8 JSON, `allow_nan=False`, and one
trailing newline. Canonicalization rebuilds nested PR #30 facts and lineage
objects rather than trusting frozen instances. The SHA-256 helper hashes those
exact canonical bytes.

## Safety and exclusions

The artifact safety mapping keeps the following exact `false`:

- network acquisition;
- future fact-status materialization authority;
- source-wide qualification;
- source identity resolution;
- conflict resolution;
- intelligence snapshot creation;
- model feature creation;
- probability calculation;
- pricing;
- selection;
- betting.

The merged `SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]` remains entirely
`UNKNOWN`. Green CI or one supported exact observation does not change that.

PR #62 deliberately does not:

- create or mutate a Fixture Intelligence snapshot;
- call `build_snapshot(...)` or `build_model_feature_snapshot(...)`;
- modify PR #30 or PR #31;
- assign `CONFLICTED` directly;
- resolve differing observations;
- normalize or reinterpret values;
- write files or contact a network;
- integrate with catalog, model, probability, pricing, selection, or betting
  code.

A later separately reviewed boundary may decide how materialized facts enter a
snapshot. Until then, PR #62 is only a deterministic, exact-lineage status
materialization artifact.
