# SportyBet event-local time-basis qualification

## Purpose

PR #156 can derive an exact provider-native event/header candidate from preserved user-controlled SportyBet event-detail HTML, but deliberately leaves the displayed clock's timezone and year unknown. PR #157 separately qualifies the official SportyBet Nigeria global rule that website times relate to GMT **unless stated otherwise**.

This boundary combines those two reviewed evidence chains without weakening either one. It can qualify a **specific event's displayed clock as GMT** only when all frozen gates pass. It still does not invent a year, so it cannot construct a kickoff UTC instant.

No SportyBet network request is introduced.

## Exact evidence chain

The successful path is:

`exact PR #153 event manifest + exact PR #154 native inventory + exact preserved event HTML`

`-> exact PR #156 event-header re-derivation`

plus

`exact PR #157 Terms qualification + exact preserved Terms HTML`

`-> exact PR #157 qualification re-derivation`

then

`temporal compatibility + reviewed event-local override scan`

`-> specific event display clock qualified as GMT, year still unknown`

Both upstream derivatives are rebuilt from their authoritative raw bytes. Matching hashes alone are insufficient.

## Temporal compatibility

The Terms evidence is observation-scoped rather than perpetual. For the global default to be applied to an event page:

- the Terms page must have been user-observed **at or before** the event-page observation;
- the age difference must be no greater than exactly `3,600,000,000` microseconds (one hour);
- the comparison uses the timezone-aware user-attested observation timestamps already carried by the reviewed evidence boundaries;
- imported-at timestamps are ingestion metadata and are never substituted for the observation timestamps.

If the Terms observation postdates the event page or is older than the frozen one-hour window, qualification fails closed.

## Event-local override rule

The official rule contains the exception `unless stated otherwise`, so an event page cannot silently inherit GMT when it visibly declares another time basis.

This PR freezes a conservative visible-text marker grammar. The PR #156 rendered-text extractor is reused, so script/style/template decoys do not count as visible provider statements.

Reviewed strong markers include:

- common timezone abbreviations such as `GMT`, `UTC`, `WAT`, `CAT`, `SAST`, `BST`, `CET`, `CEST`, `EET`, `EEST`, North-American abbreviations and `IST`;
- `GMT` / `UTC` numeric offsets;
- standalone `+HH:MM` / `-HH:MM` offsets;
- IANA-like zone labels such as `Africa/Lagos`;
- phrases such as `time zone`, `timezone`, `local time`, `times shown/stated/displayed`, and `kickoff times`.

**Any reviewed visible marker fails closed for separate review, including an explicit `GMT` marker.** This is intentional. The automatic path proves only the provider-global-default case; it does not reinterpret an explicit event-local declaration.

The output therefore records:

- `event_local_override_scan_status = NO_REVIEWED_VISIBLE_TIME_BASIS_MARKER_DETECTED`;
- `event_local_override_marker_count = 0`;
- `specific_event_time_basis_qualified = true` only after every exact gate passes.

## Qualified result

A successful artifact may carry:

- provider event ID and sport ID from the exact reviewed event source;
- exact PR #156 candidate hash;
- exact event manifest/inventory/raw lineage hashes;
- exact PR #157 Terms evidence ID, qualification hash, raw hash and rule hash;
- event and Terms user-attested observation timestamps;
- exact Terms age in microseconds;
- competition/home/away display text from the PR #156 candidate;
- displayed `DD/MM Weekday HH:MM` components;
- `kickoff_timezone = GMT`;
- `utc_offset_seconds = 0`.

It still carries:

- `kickoff_year = null`;
- `kickoff_utc = null`;
- `provider_quote_at = null`;
- `provider_snapshot_id = null`.

## What remains blocked

This boundary does **not** authorize:

- SportyBet network acquisition;
- event-year inference;
- production SportyBet ↔ FotMob fixture reconciliation;
- bookmaker equivalence;
- canonical market mapping;
- fresh-price claims;
- pricing/value integration;
- model integration;
- selection;
- ACCA/slip construction;
- booking-code generation;
- SportyBet execution;
- `BET`.

Every corresponding safety field remains exact `false`.

## Why year remains separate

Knowing that the displayed clock uses GMT is not enough to construct a timestamp. `18/08 Tuesday 20:00 GMT` still has no provider-proven year. This PR refuses to infer that year from the user observation time, current calendar, weekday arithmetic, FotMob, competition season or any other external clue.

The later fixture-reconciliation boundary must resolve year/fixture identity with separate exact evidence rather than smuggling it into this timezone step.

## Next boundary

After this PR is merged, genuine user-controlled SportyBet Terms and event-detail evidence can be passed through the combined qualifier. If a real event successfully qualifies, the next narrow engineering step is to revisit SportyBet ↔ FotMob fixture reconciliation using the now-qualified **day/month/weekday/time/GMT** partial calendar identity while keeping year ambiguity explicit and refusing fuzzy team/competition matching or kickoff tolerance.
