# Reviewed match-details probability-model readiness

PR #67 is an offline assessment boundary. It does not perform probability
inference.

The input is one exact PR #66 model-feature handoff plus every upstream value
needed to replay the complete PR #52 through PR #66 chain. The builder uses the
fully rebuilt PR #31 `FixtureModelFeatureSnapshot`; it does not accept a naked
feature snapshot, a feature dictionary, a selected market, a readiness
override, expected goals, probability values, or bookmaker odds.

## What the assessment answers

For every canonical `MarketId`, the artifact records:

1. whether the live `MODEL_STATUS_REGISTRY` declares a probability method;
2. whether every exact declared PR #31 input is `AVAILABLE`;
3. whether another reviewed transformation still blocks execution of that
   method.

Every market is evaluated. Callers cannot cherry-pick one favorable market.
The market records are sorted by the canonical market ID value.

The artifact also anchors a deterministic canonical view of the exact live
model-status registry. That view is generated mechanically from the existing
`MarketModelStatus` objects; it is an identity receipt, not a second registry.

## Missing inputs remain missing

The reviewed missing-input policy is exactly:

`REJECT_NON_AVAILABLE`

Only PR #31 `AVAILABLE` satisfies a declared probability input. `MISSING` and
`BLOCKED` never satisfy it. The existing registry's legacy
`DEFAULT_AND_DISCLOSE` value remains visible for audit, but it grants no
substitution authority here.

**Legacy DEFAULT_AND_DISCLOSE does not authorize substitution inside the
reviewed PR52→PR67 chain.**

No form, Elo, fatigue, freshness, expected-goals, probability, or pricing
default is introduced.

## Declared inputs versus execution readiness

Declared input satisfaction and reviewed execution readiness are distinct.

- A non-available declared feature produces `BLOCKED_FEATURE_INPUTS` for an
  active or experimental market.
- A disabled or unsupported market produces `BLOCKED_MODEL_STATUS`, regardless
  of feature availability.
- An active market with every declared feature available produces
  `BLOCKED_UNREVIEWED_TRANSFORM`.
- An experimental market with every declared feature available produces
  `RESEARCH_ONLY_UNREVIEWED_TRANSFORM`.

There is deliberately no production-ready state in V1.

All six PR #31 features being `AVAILABLE` still does not prove that normalized
Poisson execution is ready. The existing score matrix consumes reviewed
`home_expected_goals` and `away_expected_goals`, while PR #52 through PR #67
has not established a reviewed transformation from the six PR #31 features to
those inputs. PR #67 records that gap; it does not invent the transform.

`ACTIVE` does not mean executable. `EXPERIMENTAL` does not mean
production-ready. `AVAILABLE` does not mean probability-authorized.

Pricing inputs such as `bookmaker_odds` are retained only as registry audit
metadata. They do not participate in probability declared-input satisfaction.

## Feature audit and ancestry

For each required feature the market record preserves its exact PR #31:

- feature ID;
- `AVAILABLE`, `MISSING`, or `BLOCKED` status;
- blockers;
- evidence SHA-256 identities.

The assessment does not serialize or transform the available numeric value.
PR #31 remains the authority for feature resolution semantics.

The PR #67 wrapper binds:

- exact PR #66 canonical SHA-256 and byte size;
- exact nested PR #31 canonical SHA-256 and byte size;
- fixture identifier, source match ID, kickoff, and `as_of`;
- exact canonical model-status registry SHA-256 and byte size;
- exactly one readiness record per canonical market.

Legal revalidation replays PR #52 through PR #66, rebuilds the PR #31 state,
rebuilds the registry view and every readiness record, and compares the exact
canonical PR #67 bytes. A locally coherent mutation is not authority.

## Explicit non-capabilities

PR #67 does not:

- construct expected goals;
- call `build_score_matrix`;
- execute probability or calibration code;
- load legacy prediction defaults or models;
- acquire or use bookmaker prices;
- activate markets;
- select bets;
- access the network;
- write files.

Every downstream safety flag is exact `false`. The next separately reviewed
boundary may assess or establish the missing feature-to-probability-intermediate
transformation. Until then, ATHENA must say blocked.
