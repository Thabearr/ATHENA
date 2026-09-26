# Current Shadow SportyBet reviewed trailing-space team labels

## Evidence

This compatibility boundary is derived only from exact hosted diagnostic run `33743684967` on main `80c3af81ed2382b58f39f0b7a28872b3339fc3f2`.

Artifact:

- name: `current-shadow-sportybet-source-diagnostic`
- artifact id: `9888817924`
- artifact SHA-256: `d67c65d8b77ce61fc76a129aaf588b1b6cdf2983f728c803eaef79288f37aaef`
- active provider tournaments observed: `247`
- reviewed parser accepted: `245`
- reviewed parser rejected: `2`

The two rejected source rows were:

1. event `sr:match:73831434`, category `sr:category:33`, tournament `sr:tournament:1117`
   - exact source home label: `Jeugd Royal Francs Borains ` (one trailing ASCII space)
   - exact projected label: `Jeugd Royal Francs Borains`
   - exact tournament raw SHA-256: `9df644f04346dee648eeaaeb40756d3e063fe81f3aa68359277dceb7730033f4`
2. event `sr:match:74207246`, category `sr:category:365`, tournament `sr:tournament:27396`
   - exact source away label: `Comunicaciones FC ` (one trailing ASCII space)
   - exact projected label: `Comunicaciones FC`
   - exact tournament raw SHA-256: `6ca26904b3682f13cf936d1b43fa273fcffd3521668c196c6e625992e272ac80`

## P3.0-E1 blocker diagnostic evidence

P3.0-E1 run `34689212035` on main `e4254e64b132e8805fa712b410a363d22375c907` failed before paired corpus creation because the provider team-label whitespace shape was outside reviewed evidence.

- failure artifact id: `10296551851`
- failure artifact SHA-256: `44eff54fdf103e78f5c1eae89dd266dfaf462fd984f7fbc1a6a099c1142b835b`

The subsequent anonymous source diagnostic run `34689842174` produced artifact `10296832530` (SHA-256 `0077d93de5c9cf729cf9bf6a0a1a9aaff91f4967ec8f0065d350baef0ce79db0`). Its catalog was observed at `2026-09-12T10:59:50.483590Z` with SHA-256 `94d5826c753c675063cbae29a4adcd76f85e30f5ca9913efefe981cd2c70a1e5`.

It retained `403` tournament responses. Exactly one was parser-rejected and exactly one `homeTeamName`/`awayTeamName` field across all retained raws carried leading or trailing whitespace:

- category `sr:category:365`; tournament `sr:tournament:27396`
- tournament raw SHA-256: `46a549f09d3d4864f8b00185b8634d427d11d219e4e0545a5e3746198ec22b11`
- event `sr:match:72474956`; field `awayTeamName`
- exact raw label: `Comunicaciones FC ` (one trailing ASCII `U+0020` only)
- exact projected label: `Comunicaciones FC`

This is one new event-bound tuple. It does not make future occurrences of `Comunicaciones FC ` automatically safe, does not permit generic trimming, and does not change the authority of raw provider bytes.

## Admitted compatibility

The Shadow fanout parser may project only those exact `(event id, source field, exact source label)` tuples. The projection is literal registry lookup. It is **not** a generic `.strip()` rule.

Already-trimmed provider labels continue unchanged. Every other whitespace-bearing team label fails closed, including:

- unknown event ids;
- a different source label on a reviewed event;
- leading spaces;
- multiple trailing spaces;
- tabs or other control whitespace.

The exact raw provider response remains authoritative evidence and the parsed event retains its exact source raw SHA-256 ancestry. The frozen non-Shadow reviewed parser is not modified.

## Authority

This compatibility policy grants source-schema compatibility only. It independently grants no fixture reconciliation, model, canonical market mapping, Price-all, Router, Portfolio, final selection, share-code transport, login, cookies, wallet, staking, BET, or wager authority.

At the time of the earlier compatibility evidence above, the next operational
gate was the exact final `target=15 scope=three-day` Shadow proof. That
historical gate statement is superseded by the post-PR #360 P3.0-E1 evidence
below. This document does not authorize a Current Shadow run or a P3.0-E1
retry; any later live capture requires separate owner authorization.

## Post-PR #360 P3.0-E1 blocker diagnostic evidence

P3.0-E1 run `34896432610` on main
`18576eff9e62c643666702838302ff32bf8d70bc` failed before paired corpus
creation with `provider team label whitespace shape is outside reviewed evidence`.
Its failure artifact was `10368987784` with SHA-256
`2f55f576e8c8b9d1b3b64a7699c9bea89dda73e10063868e9b0f251e1eaac856`.

The owner-gated diagnostic run `34897587697` retained artifact `10369576508`
(SHA-256 `d056a7a93adf8c8780355ade436b4c02a772684d3ad08325aecb41f485677f9c`).
Its catalog was observed at `2026-09-14T21:14:57.988182Z` with raw SHA-256
`57d15deab140a60aa39c92ce24799e1a56a99cf549c753a7bb0a5a8e53696d1b`.
It observed 194 active tournaments and acquired 194 responses, with zero
acquisition failures, 193 parser accepts, one parser rejection, 874 retained
event rows independently inspected, one whitespace-bearing team-label field,
and one unique whitespace tuple.

That exact tuple is category `sr:category:951`, tournament
`sr:tournament:20162`, event `sr:match:73806008`, field `homeTeamName`, raw
label `SC Kiyovu ` with one trailing ASCII `U+0020`, and projection
`SC Kiyovu`. The retained tournament raw SHA-256 is
`652a5fd4a33b95a4b0ed261740d486156c8fe85b8c842c659a5bc0bc39a00ce9` and
its observation time is `2026-09-14T21:16:10.040050Z`.

This event-bound tuple does not make other `SC Kiyovu ` occurrences
automatically safe, does not create generic trimming authority, and does not
replace previously reviewed event `sr:match:73805972`. Raw provider bytes
remain authoritative. This diagnostic does not prove fixture identity, market
identity, or wager authority.

Current control state: the P3.0-E1 retry has not been performed, the P3.0
comparator remains unstarted, and P3.1 remains unstarted.

## P4.4N — exact one-trailing-ASCII-space source shape

V5 used six event-bound exact projections. Across five independent retained
hosted captures, those six examples repeatedly showed the same narrow source
shape: exactly one final ASCII space (`U+0020`). P4.4N promotes only that shape
for the provider fields `homeTeamName` and `awayTeamName`; already-trimmed
labels pass through unchanged. The six historical rows and their event,
category, tournament, raw-page SHA, run, and artifact metadata remain immutable
evidence examples. They are no longer the event admission allowlist.

The failed post-PR407 successor proof run `36229731847` did not preserve its
active pcUpcoming raw pages, so its exact new raw label is unknown. That run is
not evidence that its label had one trailing ASCII space. P4.4N's shape authority
comes only from the prior retained six-example evidence. P4.4M adds the active
pcUpcoming source root to future canonical artifact preservation.

Generic trimming remains forbidden. Leading whitespace, multiple trailing
spaces, non-ASCII boundary whitespace, and tabs/control whitespace remain
fail-closed. Projection removes only the one final ASCII space; retained raw
provider bytes and source-page SHA ancestry remain authoritative. This source
schema rule grants no fixture, model, pricing, selection, share-code, account,
or wager authority. No provider acquisition, retry, or live workflow is part of
P4.4N.
