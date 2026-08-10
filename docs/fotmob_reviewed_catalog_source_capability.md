# FotMob reviewed-catalog source capability

## Purpose

PR #44 records the narrow capability that ATHENA has now demonstrated through
the reviewed `/api/data/matches` path completed by PR #43.

It does **not** upgrade the existing `fotmob_unofficial` raw wrapper. That entry
remains `UNKNOWN` because a raw undocumented response is not equivalent to the
reviewed capture/schema/candidate/review/handoff/compiler chain.

The new adapter-scoped registry key is:

```text
fotmob_data_matches_reviewed_catalog
```

## Confirmed capability

Only one capability is `CONFIRMED`:

```text
reliable_fixture_identity = CONFIRMED
```

For this adapter, that means an individually approved candidate can reach the
PR #29 Fixture Catalog with a deterministic source-scoped identity:

```text
FOTMOB:<source match id>
```

The identity is accepted only after the existing reviewed chain has preserved
and revalidated the exact source capture ancestry, candidate SHA-256, explicit
review decision, conflict blockers, reviewed catalog-input bytes, and PR #29
compiler normalization.

This is **not** a claim that a FotMob team ID is a global ATHENA team identity.
It is also not a completeness claim about FotMob fixtures or competitions.

## Capabilities that remain unavailable or unknown

The reviewed catalog output intentionally carries no score or event-timeline
meaning, so these capabilities are `NOT_CAPTURED`:

```text
full_time_score
half_time_score
event_timestamps
freshness_metadata
```

`freshness_metadata` refers to source-provided freshness. ATHENA acquisition
and review timestamps remain provenance and audit metadata; they are not
silently reclassified as FotMob source freshness.

Historical/completeness coverage remains:

```text
historical_coverage = UNKNOWN
```

The four preserved `/api/data/matches` captures and the reviewed compiler path
do not prove season-wide, competition-wide, or provider-wide completeness.

## Evidence boundary

The registry entry is anchored only to repository-reviewed components:

- `domain/fotmob_data_matches_schema.py` — strict structure, types, fixture ID,
  team/competition linkage and kickoff consistency.
- `domain/fotmob_fixture_candidate_review.py` — exact candidate review keys,
  explicit APPROVED decisions and conflict blockers.
- `domain/fotmob_fixture_catalog_handoff.py` — exact upstream rebuild before
  catalog-input bytes are exposed.
- `scripts/manage_fotmob_reviewed_fixture_catalog.py` — reviewed handoff
  preflight and hardened PR #29 compilation.

## Safety boundary

This capability registration performs no network acquisition, raw recapture,
automatic review, fixture promotion or downstream registration. It does not
authorize Fixture Intelligence, model features, probability generation,
pricing, selection or betting.

A later PR must define and review any actual Fixture Catalog admission/promotion
boundary separately. `CONFIRMED` here means only that this reviewed adapter can
produce a reliable source-scoped fixture identity under its existing gates.
