# Sportradar user-controlled event-metadata evidence

## Purpose

PR #160 establishes a documentation-backed resolver key from the exact reviewed SportyBet football `eventId=sr:match:N` to current Sportradar `sr:sport_event:N`, while deliberately leaving the missing SportyBet year and full kickoff UTC unresolved.

This boundary defines the next evidence layer: a human may obtain and export the exact JSON response from the official Sportradar Soccer v4 **Sport Event Summary** endpoint for that verified resolver key, and ATHENA may ingest the bytes offline.

ATHENA does **not** perform a Sportradar or SportyBet network request in this boundary.

## Reviewed official Sportradar semantics

The implementation review used the official Sportradar Soccer v4 documentation on 2026-08-18:

- Sport Event Summary: `https://developer.sportradar.com/soccer/reference/soccer-sport-event-summary`
- Soccer ID Handling: `https://developer.sportradar.com/soccer/docs/soccer-ig-id-handling`
- Start Date Confirmed changelog: `https://developer.sportradar.com/sportradar-updates/changelog/soccer-apis-start-date-confirmed-flag`

The reviewed Sport Event Summary endpoint is:

`https://api.sportradar.com/soccer/{access_level}/v4/{language_code}/sport_events/{sport_event_id}/summary.{format}`

For this boundary ATHENA freezes the narrow request identity to:

- access level: exact `trial` or `production`;
- API version: exact `v4`;
- language: exact `en`;
- sport-event ID: exact verified `sr:sport_event:N` from PR #160;
- format: exact `json`;
- no query string, fragment, embedded credentials, explicit port, or percent-encoded path ambiguity.

The official documentation identifies `sport_event.id` as the unique sport-event identifier, `sport_event.start_time` as the event start time, `start_time_confirmed` as the start-time confirmation flag, and `date_confirmed` as the date-confirmation flag. It also documents `sport_event_context.sport`, `sport_event_context.competition`, and home/away competitor metadata.

## User-controlled acquisition contract

The acquisition mode is exact:

`USER_CONTROLLED_OFFICIAL_API_RESPONSE_EXPORT`

The required attestation is exact:

`I_MANUALLY_OBTAINED_AND_EXPORTED_THIS_OFFICIAL_SPORTRADAR_RESPONSE`

A user may obtain the official response through a normal Sportradar account/API-key workflow outside ATHENA and export the response JSON. ATHENA receives only the response bytes and source URL. API keys and request headers are not accepted as evidence fields and are never persisted.

The user-attested observation timestamp proves only when the user says the response was obtained. It is not silently substituted for any provider-generated timestamp.

## Mandatory SportyBet bridge revalidation

Before a Sportradar response can become evidence, ATHENA must receive the exact preserved SportyBet source chain again:

1. PR #153 user-controlled SportyBet manifest;
2. PR #154 native inventory;
3. exact preserved SportyBet event HTML;
4. PR #160 event-ID bridge artifact.

The PR #160 consumption verifier rebuilds the bridge and requires canonical byte-for-byte equality. Only then may this boundary accept a Sportradar request URL whose `sr:sport_event:N` is exactly the rebuilt bridge ID.

The JSON response must then carry the same exact `sport_event.id`. A different event ID fails closed.

## Strict response parsing

The response must be bounded, non-empty UTF-8 JSON. Duplicate object keys and non-finite JSON constants are rejected at every nesting level.

The evidence extractor requires:

- exact response `sport_event.id` matching the verified resolver key;
- exact soccer `sport_event_context.sport.id = sr:sport:1`;
- a canonical Sportradar competition ID and non-empty competition name;
- exactly two competitors with exactly one `home` and one `away` qualifier;
- distinct canonical competitor IDs and non-empty names;
- a timezone-aware ISO-8601 `sport_event.start_time`;
- `start_time_confirmed` and `date_confirmed` preserved as exact booleans when present, otherwise `null`;
- optional `replaced_by` preserved only if it is a canonical sport-event ID;
- optional top-level `generated_at` preserved only if it is a timezone-aware ISO-8601 timestamp.

Provider timestamps are stored both exactly as observed and as a deterministic normalized UTC representation. The normalized representation must mathematically equal the exact timestamp and cannot be independently forged.

## Durable evidence

The reviewed evidence root is:

`.cache/athena-research/sportradar-user-controlled-event-metadata`

Each evidence directory contains exactly:

- `response.json` — exact exported response bytes;
- `manifest.json` — canonical deterministic metadata manifest.

The evidence ID binds the exact PR #160 bridge hash, source URL, user-attested observation time, and raw response SHA-256. Storage is no-overwrite and idempotent for exact replays. Traversal, symlink escape, extra files, non-canonical manifests, raw-byte tampering, and identity collisions fail closed.

At consumption time a serialized metadata manifest is still not trusted by shape or hash fields alone. The response and exact SportyBet source chain must be supplied again; ATHENA rebuilds the evidence and requires canonical byte-for-byte equality.

## What this boundary does not authorize

This PR deliberately stops at **official metadata evidence ingestion**.

Even though the response may contain an exact timestamp with a year, this boundary does not yet promote it to the SportyBet visible fixture. The following remain exact false:

- `event_metadata_resolution_authorized`;
- SportyBet year promotion;
- SportyBet kickoff-UTC promotion;
- fixture-identity promotion;
- SportyBet ↔ FotMob fixture reconciliation;
- canonical market mapping;
- fresh-price authority;
- pricing/value/model integration;
- selection;
- ACCA/slip construction;
- booking-code generation;
- SportyBet execution;
- BET.

This separation prevents an official timestamp from being silently promoted without the next explicit consistency check against the already-qualified SportyBet visible day/month/weekday/time/GMT evidence.

## Next boundary

The next narrow boundary may combine:

- exact revalidated PR #158 SportyBet event-local GMT qualification;
- exact revalidated PR #160 event-ID bridge;
- exact revalidated official Sportradar metadata evidence from this boundary.

Only if the official Sportradar timestamp is sufficiently confirmed and its UTC day/month/weekday/time exactly agrees with the SportyBet visible GMT partial calendar may ATHENA review promotion of the missing SportyBet year and full kickoff UTC. No FotMob candidate or current-calendar assumption may supply that year.
