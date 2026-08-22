# SportyBet direct booking/share-code bridge

## Purpose

This boundary lets ATHENA read exact public SportyBet Nigeria event/market data and create a genuine anonymous SportyBet booking/share code without an intermediary, SportyBet login, cookie, wallet, stake, or wager placement.

The direct browser contract recovered from preserved SportyBet client bytes is:

- event markets: `GET /api/ng/factsCenter/event?productId=3&eventId=<sr:match:...>`
- create share code: `POST /api/ng/orders/share?throwInvalidEvent=true`
- load/verify share code: `GET /api/ng/orders/share/<shareCode>`
- Nigeria operator header: `OperId: 2`

The site client rewrites its root-relative `/orders/share` browser requests beneath `/api/<country>/`, so the reviewed Nigeria network path is `/api/ng/orders/share`.

## Security and execution boundary

The bridge does not accept or use a SportyBet username, password, PIN, session cookie, account ID, wallet, payment credential, or stake. It does not place a wager. The returned booking code is only a shareable betslip representation.

There is no Parse API dependency in the production path. There is also no browser impersonation, signed-client reproduction, proxy/WAF bypass, cookie replay, or anti-bot circumvention. If the public anonymous endpoint stops accepting the reviewed request contract, ATHENA fails closed rather than adding an evasion layer.

## Provider-native selection identity

Selections are frozen using only provider-native identifiers:

- `eventId`
- `marketId`
- `outcomeId`
- optional `specifier`

The bridge allows at most one selection per event and rejects malformed IDs, duplicate events, unsupported fields, unavailable outcomes, changed round-trip identities, or response-shape drift.

## Round-trip gate

A generated code is accepted only when all of the following hold:

1. create request returns HTTP 200 and SportyBet `bizCode == 10000`;
2. `unavailableOutcomes` is empty;
3. SportyBet returns a recognized `shareCode`;
4. loading that code directly also returns HTTP 200 / `bizCode == 10000`;
5. the loaded ticket contains exactly the same number of selections;
6. every `(eventId, marketId, outcomeId, specifier)` identity matches the original request exactly;
7. accepted outcome odds are finite and greater than 1.0.

Raw create/load responses and canonical receipts are hashed and preserved as workflow artifacts.

## Proven Saturday 2026-08-22 result

PR #204 exact-head run `32560333323` on head `f65bbca0f400007c35b54948579069ceb206b627` proved a 20-selection direct create-and-load round trip against SportyBet Nigeria. SportyBet accepted all 20 selections with zero unavailable outcomes and reconstructed the exact requested provider-native identities. The workflow artifact was `9472590101`, digest `sha256:a737cf3bae4da783465720ba0cf3877c8987ac81b1a11682df5d00df64c39e70`.

This proof establishes booking-code transport and exact SportyBet market identity only. It does not independently grant ATHENA model, value, staking, or `BET` authority.
