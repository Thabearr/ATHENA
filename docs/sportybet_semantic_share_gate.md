# SportyBet semantic share-code gate

## Problem closed by this boundary

ATHENA already had a direct SportyBet Nigeria bridge that could submit a list of provider-native `(eventId, marketId, outcomeId, specifier)` identities, receive a genuine share code, load that code again, and prove that the same identities survived the round trip.

That transport proof is necessary but not sufficient for a user-facing ATHENA ticket. A wrong native selection can round-trip perfectly. The failure observed on 2026-08-23 was exactly that: the code transport was valid, but the native IDs supplied to it represented a different 20-selection set from the ATHENA selections shown to the user.

The semantic share gate prevents that class of failure.

## Semantic intent contract

The new `scripts/sportybet_semantic_share_bridge.py` command accepts **semantic intent only**. Each row contains:

- exact SportyBet `eventId`;
- exact provider `homeTeamName`;
- exact provider `awayTeamName`;
- exact provider `marketLabel`;
- exact provider `outcomeLabel`;
- optional exact provider `specifier` such as `total=1.5`.

The caller cannot supply `marketId` or `outcomeId` through this boundary. Those IDs are derived from the live SportyBet event payload only after the semantic checks pass.

## Fail-closed sequence

For every intended leg, the gate:

1. fetches the exact public SportyBet Nigeria event payload for the stated `eventId`;
2. requires successful SportyBet response semantics;
3. requires exact home and away provider team names;
4. requires the event to remain bookable and safely pre-match;
5. finds exactly one active market whose provider label and optional line specifier equal the intended values;
6. finds exactly one active outcome whose provider label equals the intended outcome;
7. derives the provider-native `marketId` and `outcomeId` from that exact semantic match;
8. passes only those derived native identities to the reviewed direct share-code bridge;
9. requires the existing exact create -> load provider-native round-trip proof;
10. fetches every event again after the share-code round trip;
11. re-resolves the same semantic fixture/market/outcome/line intent;
12. requires every post-roundtrip provider-native identity to equal the pre-create identity exactly.

Any fixture mismatch, market-label mismatch, outcome-label mismatch, line mismatch, ambiguity, inactive selection, unsafe kickoff state, provider-native drift or lower-level round-trip failure stops code acceptance.

## Why this fixes the 2026-08-23 failure

The earlier failure could pass because the lower-level bridge was asked only: "did these IDs survive create/load?" It answered correctly even though the IDs were not the user's intended ATHENA selections.

The new gate asks two questions in order:

1. "Do these exact provider-native IDs correspond to the intended fixture, market, outcome and line right now?"
2. "Did those exact IDs survive SportyBet create/load and still correspond to the same semantics afterward?"

A valid but unrelated native selection therefore cannot substitute for an intended leg merely because it has attractive odds or a valid provider identity.

## Evidence written by a successful run

The output directory contains:

- canonical `semantic-intents.json`;
- exact pre-create SportyBet event response bytes for every leg;
- canonical pre-create semantic resolution audit;
- the complete lower-level direct-share proof directory;
- exact post-roundtrip SportyBet event response bytes for every leg;
- canonical post-roundtrip semantic resolution audit;
- `semantic-share-proof-receipt.json` binding hashes for the semantic intent, both resolution passes and the native round-trip receipt.

A successful semantic receipt asserts:

- `semantic_fixture_market_outcome_line_verified: true`;
- `post_roundtrip_semantic_revalidation_verified: true`;
- `exact_roundtrip_selection_identity_verified: true`;
- `wager_placed: false`.

## Safety boundary

This bridge uses the same public anonymous SportyBet Nigeria event/share surfaces already reviewed for the direct bridge. It does not use credentials, cookies, account state, wallet state or payment data. It creates a shareable betslip code only; it does not submit a stake or place a wager.

The original `sportybet_direct_share_bridge.py` remains the low-level native-identity transport proof. User-facing ATHENA code creation should go through the semantic gate so transport identity cannot be confused with selection meaning.
