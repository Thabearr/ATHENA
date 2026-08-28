# SportyBet current event discovery and exact FotMob reconciliation

## Purpose

This boundary implements the next dependency declared by the direct-provider Portfolio Optimizer v2:

`SPORTYBET_CURRENT_EVENT_DISCOVERY_AND_FIXTURE_RECONCILIATION_REQUIRED`

Until this boundary, ATHENA's reviewed live SportyBet quote path started from an already-known `sr:match:<id>`. That is sufficient to refresh the price for a known event, but it is not sufficient for autonomous daily operation. ATHENA also needs a reviewed way to discover current SportyBet football event IDs and bind them to the exact reviewed FotMob fixtures that supply its football-state identity.

This PR adds that source/provenance boundary without modifying the frozen Price-all, Router, Portfolio Optimizer, legacy reconciliation, or live-event quote contracts.

## Source scope

The source is one anonymous read-only SportyBet Nigeria FactsCenter request:

`GET /api/ng/factsCenter/wapConfigurableUpcomingEvents?sportId=sr%3Asport%3A1`

Request scope is deliberately narrow and explicit:

- football only: `sr:sport:1`;
- no login;
- no cookies;
- no wallet;
- no account token;
- no share-code request;
- no staking;
- no wager.

The endpoint was identified from current public SportyBet WAP usage evidence. Runtime authority does **not** come from that third-party discovery material: authority comes only from the exact SportyBet response captured by ATHENA, its immutable raw SHA-256, its response-completion observation time, and deterministic replay.

The contract calls this the **current configurable upcoming-event feed**. It does not claim that the response is a mathematically complete enumeration of every SportyBet football event or every market. A successful empty response is represented as an explicit zero-event inventory rather than being filled from another source.

## Frozen contract

`athena-sportybet-current-event-fixture-reconciliation-v1`

Contract SHA-256:

`9f65195b3fad2398dae7c8f4a78f426c519bb11156e1217793ac25c57f47dc7f`

The contract pins:

- the existing direct SportyBet event-read contract SHA `b888cebab6447cd4072d823dab67b56f1f75f72eb72d67b692d47a4378b27555`;
- the reviewed FotMob fixture-catalog handoff dataset/schema;
- SportyBet origin and OperId identity;
- football sport ID;
- current configurable-upcoming endpoint;
- response-completion observation semantics;
- maximum source age 900 seconds;
- minimum kickoff lead 120 seconds;
- exact reconciliation semantics;
- the next reviewed boundary.

## Durable provider evidence

Live acquisition stores exactly two files beneath:

`.cache/athena-research/sportybet-current-upcoming-event-discovery/<capture-id>/`

- `upcoming.raw.json`
- `manifest.json`

The manifest records the exact request target and headers, HTTP/bizCode success, response-completion observation time, raw SHA-256, raw byte size, and authority flags. Capture identifiers bind request target, observation time and raw SHA.

The JSON parser rejects:

- invalid UTF-8;
- duplicate object keys;
- NaN/Infinity constants;
- oversized payloads;
- malformed event IDs;
- non-football events escaping the request scope;
- conflicting duplicate copies of the same SportyBet event ID.

Identical repeated copies of one event in grouped provider JSON may be deterministically deduplicated. Conflicting copies fail closed.

## Observation time is not provider time

`observed_at` means ATHENA completed the direct provider response.

It is explicitly:

`ATHENA_DIRECT_PROVIDER_RESPONSE_COMPLETION_NOT_PROVIDER_EVENT_TIMESTAMP`

The boundary does not invent a provider event-update timestamp or provider snapshot identifier:

- `provider_event_timestamp = None`
- `provider_snapshot_id = None`

`estimateStartTime` is interpreted only as the provider's fixture kickoff timestamp. It is not relabeled as quote time or snapshot time.

## Current event inventory

Each parsed SportyBet event preserves, where supplied:

- exact `sr:match:<positive integer>` event ID;
- football sport ID;
- exact home team name;
- exact away team name;
- exact tournament/competition display name;
- category/tournament provider IDs where present;
- full UTC kickoff from `estimateStartTime`;
- booking status;
- event status;
- match status;
- pre-match/bookability state.

Competition identity may come from the event itself or from the provider tournament container that owns the event. If the response does not supply a usable competition/tournament label, the event remains explicitly `COMPETITION_IDENTITY_UNAVAILABLE` and cannot receive fixture-reconciliation authority.

## FotMob input authority

The other side of the comparison is an exact `FotMobFixtureCatalogHandoff` built from reviewed FotMob candidate and review bundles.

Before any SportyBet/FotMob comparison, ATHENA rebuilds that handoff from its retained candidate/review inputs and requires deterministic equality. The reconciliation retains the exact handoff SHA-256 plus, for a successful row, the matched FotMob fixture ID, candidate SHA and source capture-manifest SHA.

This PR does not silently turn arbitrary caller team strings into FotMob authority.

## Exact reconciliation only

The matching basis is frozen as:

`EXACT_HOME_AWAY_COMPETITION_FULL_UTC_NO_FUZZY_NO_ALIAS_NO_REVERSAL_NO_ROUNDING_NO_TOLERANCE`

A provider event can become `UNIQUE_EXACT_MATCH_RECONCILED` only when exactly one reviewed FotMob input has all four equalities:

1. SportyBet home name == FotMob home name;
2. SportyBet away name == FotMob away name;
3. SportyBet competition name == FotMob competition name;
4. SportyBet full UTC kickoff == FotMob full UTC kickoff.

There is no case folding, nickname map, team reversal, edit distance, kickoff tolerance or minute rounding.

This is intentionally conservative. Real provider-name drift will remain unresolved until a separate reviewed identity/alias source proves an equivalence. This boundary never guesses merely to increase fixture coverage.

## Ambiguity and blocked states

Each provider event receives one explicit disposition:

- `UNIQUE_EXACT_MATCH_RECONCILED`;
- `NO_EXACT_MATCH`;
- `AMBIGUOUS_FOTMOB_MATCH`;
- `AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE`;
- `COMPETITION_IDENTITY_UNAVAILABLE`;
- `PROVIDER_EVENT_NOT_PREMATCH_BOOKABLE`;
- `PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF`.

If one SportyBet event exactly matches multiple reviewed FotMob fixture IDs, no fixture is chosen.

If multiple different SportyBet event IDs would all map to one FotMob fixture, none receives reconciliation authority. This prevents duplicate provider listings from silently becoming two betting opportunities for one football fixture.

## Freshness and kickoff gates

A preserved source response may be replayed only at an explicit timezone-aware evaluation time. The evaluation time cannot predate response completion, and source age must remain at or below 900 seconds.

Live-current issuance does not accept a caller-controlled clock. It captures the provider response and evaluates currentness against ATHENA's current UTC time.

Kickoff lead is checked event by event. An event at or below the frozen 120-second minimum remains auditable but cannot receive fixture-reconciliation authority.

These checks do not make the response permanently current.

## Builder-only reconstruction

`SportyBetCurrentEventFixtureReconciliation` is builder-only.

`verify_current_event_fixture_reconciliation()` reconstructs it from:

- exact preserved raw SportyBet bytes and canonical manifest;
- exact evaluation time and proof mode;
- exact retained reviewed FotMob handoff.

Any public-field mutation, raw evidence mutation, manifest mutation, handoff mutation, duplicate conflict or identity drift fails closed.

## Authority

This boundary grants only the capabilities it proves:

- anonymous direct-provider network acquisition;
- current SportyBet football event discovery;
- exact source provenance;
- exact fixture reconciliation against reviewed FotMob inputs.

It does **not** grant:

- provider event timestamp/snapshot identity;
- canonical SportyBet market mapping for newly discovered events;
- Price-all;
- Market Router;
- Portfolio Optimizer;
- slip construction;
- SportyBet execution;
- staking;
- BET authority.

`wager_placed` is always false.

## Why canonical market mapping is still separate

The existing reviewed SportyBet canonical market mapping is event-specific: its mapping rows bind an exact provider event ID, provider market ID, specifier, provider outcome ID and human-readable semantics. Discovering a new event ID does not authorize ATHENA to copy an older event's mapping object across to it.

Therefore this PR's next boundary is deliberately:

`SPORTYBET_CURRENT_EVENT_CANONICAL_MARKET_MAPPING_REBIND_REQUIRED`

That future boundary must prove how reviewed provider market semantics are safely rebound to a newly discovered and reconciled current event before PR246's live quote bundle can feed the Price-all v2 lane autonomously.

## Test scope

Tests use synthetic provider JSON and mock the network function. They cover exact matching, case/competition/kickoff mismatch, home/away reversal, missing competition, non-bookable events, kickoff lead, source staleness, future-dated evaluation, duplicate provider identities, provider-to-fixture ambiguity, FotMob ambiguity, empty successful responses, builder-only issuance, exact reconstruction and raw evidence tamper detection.

No test performs a live SportyBet network call, generates a booking code, stakes, or wagers.
