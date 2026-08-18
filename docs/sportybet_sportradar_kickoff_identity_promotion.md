# SportyBet ↔ Sportradar kickoff identity promotion

## Purpose

PR #158 proved only that one reviewed SportyBet event's visible clock inherits the provider's GMT default. Its visible header contains day, month, weekday, hour and minute, but no year.

PR #160 proved a documentation-backed identity bridge from the exact SportyBet `eventId=sr:match:N` to current Sportradar `sr:sport_event:N`, preserving the same numeric event identifier.

PR #161 permits offline ingestion of an official Sportradar Soccer v4 Sport Event Summary response for that exact revalidated event ID, while deliberately refusing to promote the response timestamp back onto SportyBet.

This boundary performs that missing promotion step, but only under a strict three-source consistency gate.

## Exact source chain

A successful promotion requires all of these inputs again:

1. exact PR #153 SportyBet user-controlled evidence manifest;
2. exact PR #154 native inventory;
3. exact preserved SportyBet event HTML;
4. exact PR #157 Terms qualification and exact Terms HTML;
5. exact PR #158 event-local GMT qualification;
6. exact PR #160 SportyBet/Sportradar event-ID bridge;
7. exact PR #161 Sportradar metadata evidence;
8. exact preserved Sportradar JSON response.

The PR #158 time-basis object is rebuilt from the SportyBet/Terms bytes and must match canonically. The PR #160 bridge is rebuilt from the SportyBet bytes and must match canonically. PR #161 metadata is then rebuilt from the exact Sportradar response plus the exact revalidated bridge and must match canonically.

Hash-shaped or structurally plausible artifacts are not enough.

## Promotion gate

The official Sportradar metadata may supply the previously unknown SportyBet year and full kickoff UTC only when all of the following hold:

- `sport_event.id` is the exact revalidated `sr:sport_event:N`;
- `start_time_confirmed` is exact boolean `true`;
- `date_confirmed` is exact boolean `true`;
- `replaced_by` is null/absent;
- the PR #158 SportyBet event time basis is exact `GMT`, UTC offset `0`;
- the official provider `start_time` is timezone-aware and normalizes to UTC;
- normalized UTC **day, month, weekday, hour and minute** exactly equal the SportyBet visible GMT partial calendar.

There is no kickoff tolerance, rounding, nearest-date selection or current-year assumption. FotMob is not an input to this promotion.

The weekday check is important. A date such as `18/08 20:00` in another year is not accepted merely because the numeric day/month/time match; the official year must also produce the exact visible weekday.

## Provider timestamp precision

SportyBet's visible header is minute-precision. Sportradar may carry seconds or microseconds. This boundary does **not** round or zero those provider fields.

The exact provider instant is preserved as the promoted full UTC after the day/month/weekday/hour/minute consistency gate succeeds. Thus a confirmed `20:00:37.123456Z` remains `20:00:37.123456Z`; ATHENA never manufactures `20:00:00Z`.

## What is promoted

A successful result may state:

- the exact provider event kickoff identity is resolved across the reviewed SportyBet/Sportradar bridge;
- the missing SportyBet kickoff year is promoted from the confirmed official Sportradar timestamp;
- the full SportyBet kickoff UTC is promoted from the same exact provider instant.

The result also preserves both SportyBet display labels and official Sportradar competition/competitor labels. Those labels are **not** declared equivalent and are not fuzzy-matched.

## What remains blocked

This PR does not prove SportyBet ↔ FotMob fixture equivalence. In particular it does not authorize:

- FotMob fixture reconciliation;
- fuzzy/alias team or competition matching;
- canonical SportyBet market mapping;
- provider quote timestamp or snapshot identity;
- fresh-price authority;
- pricing/value/model integration;
- selection;
- ACCA/slip construction;
- booking-code generation;
- SportyBet execution;
- BET.

Every downstream safety flag remains exact `false`.

## Consumption-time verification

`revalidate_kickoff_identity_promotion()` rebuilds the complete promotion from all preserved inputs and requires canonical byte-for-byte equality with the supplied promotion object. Downstream consumers must use that boundary rather than trusting serialized hashes or fields by shape.

## Next boundary

Once a real event has passed this promotion gate, ATHENA can revisit the SportyBet ↔ FotMob reconciliation boundary with a **full provider-resolved UTC kickoff** instead of a year-unknown partial calendar.

That next boundary must still preserve strict literal home/away/competition matching unless a separately reviewed explicit alias contract is introduced. It must not add fuzzy matching or kickoff tolerance merely because a full timestamp is now available.
