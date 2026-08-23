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

The low-level direct transport bridge allows at most one selection per event and rejects malformed IDs, duplicate events, unsupported fields, unavailable outcomes, changed round-trip identities, or response-shape drift.

## Round-trip gate

A generated code is accepted by the low-level transport only when all of the following hold:

1. create request returns HTTP 200 and SportyBet `bizCode == 10000`;
2. `unavailableOutcomes` is empty;
3. SportyBet returns a recognized `shareCode`;
4. loading that code directly also returns HTTP 200 / `bizCode == 10000`;
5. the loaded ticket contains exactly the same number of selections;
6. every `(eventId, marketId, outcomeId, specifier)` identity matches the original request exactly;
7. accepted outcome odds are finite and greater than 1.0.

Raw create/load responses and canonical receipts are hashed and preserved as workflow artifacts.

## Semantic integrity failure exposed on 2026-08-23

A provider-native identity round trip is necessary but not sufficient to prove that a booking code represents ATHENA's intended selections. On 2026-08-23, a 20-selection set of provider-native IDs was successfully created and reloaded by SportyBet, but those IDs had been assembled from a different 20-selection set than the human-readable ATHENA selections presented to the user. The transport gate correctly proved identity preservation; it had no evidence that those identities meant the intended fixture/market/outcome semantics.

The permanent lesson is explicit:

`exact provider-native round trip != intended selection semantics`

No future ATHENA booking-code operation should treat raw `(eventId, marketId, outcomeId, specifier)` success as sufficient user-intent proof.

## Permanent semantic booking-code gate

`scripts/sportybet_semantic_share_bridge.py` is the canonical higher-level booking-code entry point for ATHENA-selected slips.

It accepts only semantic intent fields:

- exact SportyBet `eventId`;
- expected SportyBet home-team name;
- expected SportyBet away-team name;
- expected SportyBet market name;
- expected SportyBet outcome name;
- optional exact SportyBet line `specifier`.

Caller-supplied `marketId`, `outcomeId`, or odds are rejected. For every intent, the gate fetches the current SportyBet event payload and fails closed unless:

1. exactly one event object with the requested `eventId` and markets exists;
2. normalized exact home/away participant identity matches the intent;
3. the event remains safely pre-match and bookable;
4. exactly one active provider market matches the intended market name and exact specifier;
5. exactly one active provider outcome matches the intended outcome label;
6. provider-native `marketId` and `outcomeId` are derived from that proven semantic match, never supplied by the caller;
7. all semantic intents resolve to unique events;
8. the derived provider-native selections then pass the existing create -> reload exact-identity gate;
9. semantic-resolution count and transport-round-trip count remain identical.

The gate stores exact raw event responses, hashes them, writes a semantic-resolution receipt, writes the derived provider-native selection file, and only then invokes the low-level direct transport.

This makes the authority chain:

`ATHENA semantic intent -> live SportyBet fixture/market/outcome proof -> derived provider-native identity -> SportyBet create -> SportyBet reload -> exact native round trip`

The low-level `sportybet_direct_share_bridge.py` remains useful as transport proof and for historical evidence replay, but it must not by itself be treated as proof that a user-facing ATHENA selection was encoded correctly.

## Proven Saturday 2026-08-22 result

PR #204 exact-head run `32560333323` on head `f65bbca0f400007c35b54948579069ceb206b627` proved a 20-selection direct create-and-load round trip against SportyBet Nigeria. SportyBet accepted all 20 selections with zero unavailable outcomes and reconstructed the exact requested provider-native identities. The workflow artifact was `9472590101`, digest `sha256:a737cf3bae4da783465720ba0cf3877c8987ac81b1a11682df5d00df64c39e70`.

That historical proof establishes booking-code transport and exact SportyBet provider-native identity only. The new semantic gate is the required higher-level boundary for proving that those native identities correspond to ATHENA's intended human-readable selections.

Neither boundary independently grants ATHENA model, value, staking, or `BET` authority.
