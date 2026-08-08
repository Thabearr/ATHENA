# Fixture Model Feature Mapping Contract

## Purpose and architecture

`FixtureModelFeatureSnapshot` is ATHENA's audited boundary between preserved
fixture intelligence and future probability models. It maps already
model-ready, supported numeric facts; it does not calculate or improve them.

```text
Fixture catalog
    -> Fixture intelligence evidence
    -> Verified model feature mapping (this contract)
    -> future feature engineering / model integration
    -> probability
    -> separate bookmaker pricing
    -> decision gates
```

The canonical dataset is
`athena-fixture-model-feature-snapshot-v1`, with exact integer schema version
`1`.

## Current feature registry

The v1 registry intentionally mirrors the current non-empty
`probability_inputs` in `domain/model_status.py`:

| Feature ID | Intelligence category | Exact source field |
| --- | --- | --- |
| `home_form` | `FORM` | `home_form` |
| `away_form` | `FORM` | `away_form` |
| `home_elo` | `PERFORMANCE` | `home_elo` |
| `away_elo` | `PERFORMANCE` | `away_elo` |
| `fatigue` | `SCHEDULE_LOAD` | `fatigue` |
| `live_data_freshness` | `FIXTURE_CONTEXT` | `live_data_freshness` |

`bookmaker_odds` is not a model feature. Pricing remains a separate evidence
and decision concern. Availability, lineup, xG, weather, and other upstream
context are not mapped until a later reviewed schema defines their feature
semantics.

This contract does not compute form from results, ELO from match history,
fatigue from rest days, or freshness from the clock. It does not normalize,
clamp, round, weight, or otherwise transform supplied numeric values. An
upstream reviewed adapter must first preserve an explicit finite numeric fact
under the exact binding.

## Resolution semantics

Every registered feature receives exactly one resolution:

- `AVAILABLE`: at least one non-conflicted `SUPPORTED` fact supplies one
  canonical finite `int` or `float` value. The value is stored as a `float`,
  while every matching evidence hash remains traceable.
- `MISSING`: no matching fact exists. The value is `null`, and there are no
  blockers or evidence hashes. Unknown remains unknown.
- `BLOCKED`: matching evidence exists but cannot safely become a model input.
  The value is `null`, with explicit blockers and preserved evidence hashes.

Stale-only and unverified-only evidence are blocked because they provide no
current supported value. Discovery/general-web material is upstream
`DISCOVERY_ONLY` evidence and therefore remains `UNVERIFIED`; it cannot
directly produce an available model feature. A current supported fact may
remain available alongside a stale or unverified record when the field is not
conflicted, but all matching evidence hashes remain in the audit trail.

Conflicted fields are always blocked. No official, FotMob, or other source is
silently selected as a winner, and this layer defines no source precedence.
An invalid supported value is also blocked, using
`INVALID_SUPPORTED_VALUE`, rather than being disguised as missing evidence.

## Source-snapshot anchor

Each output records the source fixture-intelligence dataset name, exact schema
version, and SHA-256 of the existing canonical
`FixtureIntelligenceSnapshot` bytes. The mapper reuses
`canonical_snapshot_bytes` and `sha256_bytes`; it does not duplicate upstream
canonicalization. This creates a cryptographic audit link from every feature
snapshot to the precise evidence snapshot used to build it.

Serialization is deterministic canonical UTF-8 JSON with sorted keys, compact
separators, UTC timestamps, no NaN values, and a final LF newline. Fact input
ordering cannot change the canonical output.

## No defaulting

This layer generates no zero, neutral value, average, or other fallback.
`MISSING` stays `MISSING`, and `BLOCKED` stays `BLOCKED`.

`MissingInputPolicy.DEFAULT_AND_DISCLOSE` in the current model-status registry
is a downstream legacy policy. PR #31 does **not** enact it. A future reviewed
model-integration change must explicitly decide how that policy interacts with
this trusted snapshot.

## Source roles and disconnected legacy paths

FotMob is intended to become ATHENA's primary football-context backbone after
separate source and acquisition review. This PR does not acquire FotMob data,
and legacy FotMob network/bypass workers remain disconnected.

SportyBet is a separate pricing candidate, not a source of model-feature
evidence. Odds cannot enter this feature registry.

The legacy `intelligence/prediction_engine.py` contextual overlay accepts
subjective impact scores and applies probability nudges. It is not imported,
called, reproduced, or connected by this contract.

## Safety boundary

The feature snapshot is immutable and inert. It contains the exact following
authorization flags, all fixed to `false`:

- network acquisition
- scraping
- browser automation
- probability inference
- probability adjustment
- pricing
- market activation
- selection
- production approval
- betting

PR #31 does not:

- acquire FotMob data;
- perform search;
- scrape;
- calculate model probabilities;
- calculate contextual probability nudges;
- produce odds;
- compare prices;
- calculate expected value;
- calculate Kelly stakes;
- activate a market;
- select a bet;
- build an accumulator; or
- place a bet.

The output is data only. Later feature engineering and model integration must
cross their own reviewed contracts before any probability, pricing, or
decision behavior can use it.
