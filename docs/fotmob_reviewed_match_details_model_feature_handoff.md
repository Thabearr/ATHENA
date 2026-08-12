# Reviewed FotMob match-details model-feature handoff

## Purpose

PR #66 is the first reviewed FotMob match-details handoff into real PR #31
model features. It does not create new feature semantics. It preserves the
complete reviewed ancestry that would otherwise be lost if a naked generic
PR #30 snapshot were passed directly to PR #31.

```text
fully revalidated PR #52 through PR #65 wrapper
    -> exact rebuilt PR #65 nested FixtureIntelligenceSnapshot
    -> existing PR #31 build_model_feature_snapshot
    -> exact real FixtureModelFeatureSnapshot
    -> PR #66 reviewed-lineage wrapper
```

The wrapper dataset is
`athena-fotmob-reviewed-match-details-model-feature-handoff-v1`, with exact
integer schema version `1` and scope
`EXACT_REVALIDATED_PR65_SNAPSHOT_ONLY`.

## Exact construction

The legal PR #66 builder accepts the complete inputs required by the existing
PR #65 full-chain revalidator, the exact PR #65 artifact, and its immutable
canonical bytes. It does not accept a caller-supplied PR #30 snapshot, PR #31
snapshot, feature list, feature value, blocker, source-snapshot hash, `as_of`,
or readiness override.

The builder performs exactly:

1. replay the complete PR #52 through PR #65 reviewed chain;
2. obtain only the rebuilt PR #65 nested `FixtureIntelligenceSnapshot`;
3. call existing PR #31 `build_model_feature_snapshot` on that snapshot;
4. verify fixture, kickoff, `as_of`, source dataset/schema, and exact canonical
   PR #30 SHA linkage;
5. wrap the actual resulting `FixtureModelFeatureSnapshot` with exact PR #65,
   PR #30, and PR #31 byte-size and SHA-256 anchors.

PR #66 does not copy or reimplement PR #31 mappings, resolution ordering,
AVAILABLE/MISSING/BLOCKED rules, conflict behavior, stale or unverified
handling, numeric validation, source snapshot hashing, serialization, or
safety.

## Existing PR #31 results remain authoritative

PR #31 continues to map exactly:

- `home_form`;
- `away_form`;
- `home_elo`;
- `away_elo`;
- `fatigue`;
- `live_data_freshness`.

`AVAILABLE` means only that existing PR #31 resolved this exact feature from
the exact reviewed Fixture Intelligence snapshot. It is not a global
`MODEL_READY` decision and does not authorize probability inference.

`MISSING` and `BLOCKED` remain first-class outcomes. PR #66 supplies no
defaults, performs no normalization, and does not filter or infer absent
values. Differing supported observations remain blocked by existing PR #31
with `CONFLICTED_EVIDENCE`; no winner is chosen. Stale-only and
unverified-only evidence retain the existing PR #31 blockers.

Incomplete feature availability is valid handoff output. PR #66 makes no
claim that every market needs all six inputs, that a probability model is
calibrated, or that a price or value decision exists.

## Exact identity and replay

The wrapper records:

- SHA-256 and byte size of the exact canonical PR #65 artifact;
- fixture identifier, source-scoped match ID, kickoff, and exact PR #65
  `classified_at` as `as_of`;
- SHA-256 and byte size of the exact canonical PR #30 snapshot;
- the actual existing PR #31 `FixtureModelFeatureSnapshot`;
- SHA-256 and byte size of the exact existing PR #31 canonical bytes;
- downstream-only safety flags, all exact `false`.

Local canonicalization reconstructs every nested `ModelFeatureResolution` and
the nested PR #31 snapshot through existing PR #31 invariants. Full PR #66
revalidation reruns PR #52 through PR #65, rebuilds PR #31 from the rebuilt
PR #30 snapshot, rebuilds PR #66, and requires both the supplied object and
immutable bytes to equal exact rebuilt canonical bytes. A coordinated local
PR65/PR30/PR31/hash forgery cannot establish reviewed ancestry.

A naked generic PR #31 `FixtureModelFeatureSnapshot` demonstrates PR #31
structural validity. It does not independently prove the FotMob PR #52
through PR #65 reviewed chain. That ancestry is established only by the
fully revalidated PR #66 wrapper.

## Safety boundary

PR #66 ends at the exact PR #31 feature snapshot. It performs no network or
filesystem behavior, source-wide qualification, identity resolution,
conflict resolution, probability inference or adjustment, calibration,
pricing, market activation, selection, production approval, or betting.

The wrapper does not carry the misleading flag
`model_feature_authorized=false`, because model features have been
constructed. Instead, every downstream authority flag is exact `false`. The
nested PR #31 snapshot retains its own existing exact all-false safety
mapping.
