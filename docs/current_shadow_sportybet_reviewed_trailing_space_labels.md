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

The next operational gate remains the exact final `target=15 scope=three-day` Shadow proof after this compatibility change is merged and hosted tests are green.
