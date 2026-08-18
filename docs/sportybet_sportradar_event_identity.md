# SportyBet ↔ Sportradar event-identifier bridge

## Purpose

PR #159 deliberately leaves the SportyBet year unresolved. The next safe step is not to infer that year from FotMob, the current date, or calendar proximity. Instead, this boundary freezes a separate provider-native resolver key already present in the reviewed SportyBet event URL.

The SportyBet event-detail evidence carries an `eventId` such as `sr:match:123` and football `sportId=sr:sport:1`. ATHENA first re-derives the exact PR #156 machine event-header candidate from the preserved PR #153 manifest, PR #154 native inventory, and exact raw event HTML. Only after that evidence chain succeeds does this boundary inspect the event-ID namespace.

## Reviewed official documentation semantics

On 2026-08-18 the implementation review checked two official Sportradar developer-documentation pages:

- the Soccer v3 → v4 migration guide;
- the Soccer ID Handling guide.

The frozen documentation contract records only the semantics needed for this boundary:

- legacy soccer sport-event IDs use the `sr:match:<positive integer>` form;
- the current v4 sport-event prefix is `sr:sport_event:`;
- the numeric identifier is preserved when moving from the legacy prefix to the current prefix;
- soccer matches are documented as having their own sport-event identifier;
- soccer is `sr:sport:1` in the reviewed documentation examples.

The canonical documentation contract SHA-256 is:

`ea3417948148b5ae2aa7c1aac4f5795437bfe913b67c6212d31267d8cd36d902`

This is a versioned documentation-semantics contract. It is not a live Sportradar API response and it is not football fixture evidence.

## Exact bridge rule

For a re-derived SportyBet football event with exact event ID:

`sr:match:N`

where `N` is a canonical positive decimal integer, ATHENA may construct the documentation-backed current Sportradar resolver key:

`sr:sport_event:N`

The numeric payload must be byte-for-byte the same decimal representation. Leading zeroes, zero, negative IDs, alternative prefixes, or a non-football `sportId` fail closed.

The resulting artifact records both forms plus the exact SportyBet evidence lineage. `sportradar_namespace_qualified=true` means only that the exact SportyBet event-ID string conforms to the reviewed Sportradar sport-event identifier semantics.

## What this does not prove

This bridge does **not** resolve the sport event. In particular it does not prove or populate:

- kickoff year;
- full kickoff UTC;
- competition identity;
- team identity beyond the already-reviewed SportyBet visible header candidate;
- a SportyBet ↔ FotMob fixture equivalence;
- current odds or a provider quote timestamp;
- any market mapping or value calculation.

`event_metadata_resolved=false`, `fixture_identity_proven=false`, `sportybet_kickoff_year=null`, and `sportybet_kickoff_utc=null` remain mandatory.

## Network and betting authority

No SportyBet or Sportradar network request is introduced. The bridge does not contain credentials, API keys, browser automation, scraping, or an API client.

All safety authorities remain exact `false`, including `sportradar_metadata_resolution_authorized`, fixture reconciliation, fresh pricing, model/value integration, selection, ACCA/slip construction, booking-code generation, execution, and `BET`.

## Next boundary

The documented current resolver key gives ATHENA a non-circular way to request or ingest authoritative Sportradar event metadata later. The next narrow boundary should define a user-controlled/offline official Sportradar sport-event response contract keyed to this exact ID. If such evidence supplies an exact scheduled/start time and event identity, ATHENA can review whether it proves the missing SportyBet year without using the FotMob candidate as proof.
