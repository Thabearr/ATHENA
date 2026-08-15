# Reviewed FotMob ordinary-FT finished-score adapter

## Purpose

This boundary implements the smallest missing prerequisite identified by PR #94:

```text
BUILD_REVIEWED_FOTMOB_DATA_MATCHES_ORDINARY_FT_FINISHED_SCORE_ADAPTER
```

The adapter is prospective and reusable. It accepts two caller-supplied reviewed
`/api/data/matches` captures and emits only source-reported finished scores that
reproduce the exact ordinary-FT gate already reviewed by PR83/PR90/PR92.

It is **not** a source-capability registration and it creates no source-history,
model, probability, pricing, selection, production, or betting authority.

## Exact base

```text
main c973dabcc43103a9c939706067ca23294f6870ad
```

Adapter identity:

```text
dataset athena-fotmob-data-matches-ordinary-ft-finished-score-adapter-v1
scope   REUSABLE_REVIEWED_PROSPECTIVE_ORDINARY_FT_FINISHED_SCORE_PAIR_GATE_ONLY
state   IMPLEMENTED_REUSABLE_PROSPECTIVE_GATE_NO_CAPABILITY_REGISTRATION
```

## Pair-level admission

Before any fixture can be emitted, the adapter requires both inputs to be exact
PR38 `FotMobDataMatchesCaptureManifest` captures with matching raw bytes and sizes.
Both manifests must represent actual reviewed network captures rather than internal
projections.

The pair must also satisfy all of the following:

- exact same `request_date`, `timezone`, and `ccode3`;
- distinct raw SHA-256 lineages;
- distinct capture-manifest SHA-256 lineages;
- second observation strictly later than the first;
- separation of at least 300 seconds;
- both full payloads independently pass the reviewed PR89 structural chain.

Any failure at this level blocks the pair before fixture-level score output.

## Fixture-level gate

The adapter considers source fixtures that are post-kickoff and report:

```text
status.finished  true
status.started   true
status.cancelled false
```

For each fixture across the two captures, the adapter then fails closed unless:

1. both captures contain a qualifying terminal observation;
2. fixture id, league id, home id, away id, and kickoff are identical;
3. both home and away scores are exact non-negative integers;
4. the home/away score pair is stable across the two observations;
5. the four-field `status.reason` tuple is identical across observations;
6. that tuple is exactly:

```json
{"short":"FT","shortKey":"fulltime_short","long":"Full-Time","longKey":"finished"}
```

7. `status.awarded` is absent or exact `false` in both observations;
8. `penScore` is absent from both teams in both observations.

Only then is the fixture emitted as:

```text
QUALIFIED_ORDINARY_FT_SOURCE_REPORTED_FINISHED_SCORE
```

## Explicit blockers

The adapter records fixture-level fail-closed dispositions for:

- insufficient repeat observations;
- fixture identity drift;
- invalid score scalars;
- post-finish score instability;
- reason-tuple mismatch or partial mismatch;
- missing/unreviewed reason tuples;
- awarded results;
- any team `penScore` presence;
- the exact reviewed penalty reason tuple.

The exact penalty reason remains blocked:

```json
{"short":"Pen","shortKey":"penalties_short","long":"After penalties","longKey":"afterpenalties"}
```

No penalty score meaning is inferred.

## Semantic scope

A qualified adapter record means only the frozen PR83 semantic scope:

```text
SOURCE_REPORTED_FINISHED_SCORE_ONLY_NOT_REGULATION_TIME_EXTRA_TIME_PENALTIES_OR_SETTLEMENT_SEMANTICS_BEYOND_THE_SOURCE_FIELDS
```

The adapter does not claim that the emitted score is specifically a regulation-
time score, an extra-time-inclusive score, a penalty-shootout result, or a bookmaker
settlement score.

## Preserved lineage

Every emitted score preserves:

- fixture, league, home-team and away-team source ids;
- kickoff UTC;
- home and away score;
- the exact reviewed ordinary-FT reason tuple;
- first and second observation timestamps;
- both raw SHA-256 values;
- both capture-manifest SHA-256 values.

The pair result also preserves canonical hashes of both PR89 structural assessments.

## Exact PR85 regression evidence

The committed PR85 capture pair remains the main regression fixture for this
implementation. The adapter must reproduce the prior reviewed result:

```text
ordinary FT qualified scores  28
penalty fixture excluded        1
penalty fixture id        5844873
```

The ordinary fixture used for mutation tests is fixture `5186581`, whose preserved
source score is `3-1`.

Adversarial regression tests additionally require fail-closed handling of reason
changes, reason mismatch, `awarded=true`, `penScore` presence, score instability,
identity drift, insufficient repeat observation, raw/manifest mismatch, duplicate
capture lineage, and reversed observation order.

## Registry consequence

The parent capability remains unchanged:

```text
fotmob_data_matches_reviewed_catalog
full_time_score           NOT_CAPTURED
reliable_fixture_identity CONFIRMED
historical_coverage       UNKNOWN
```

The future derived key remains only a later registration candidate:

```text
fotmob_data_matches_reviewed_ordinary_ft_finished_score
```

This adapter never inserts or updates that key.

## Next boundary

```text
EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_ORDINARY_FT_FINISHED_SCORE_ADAPTER_VALIDATION
```

That later boundary should execute this reusable adapter against the exact preserved
PR85 evidence, freeze the deterministic result/lineage in a receipt, and only then
return to the separately reviewed capability-promotion decision. Historical coverage
and all downstream authority remain out of scope.
