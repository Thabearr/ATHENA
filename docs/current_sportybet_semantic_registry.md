# PR-B current SportyBet semantic registry

PR-B adds a versioned, research-only semantic/readiness boundary for the
fifteen canonical markets in `domain/markets.py`.  It answers which exact
SportyBet native structures have been observed and reviewed on a current,
prematch, bookable event.  It does not calculate all-market probabilities,
prices, value, routing, portfolio legs, share codes, or bets.

## Authority and source binding

The registry derives canonical family/outcome/line identity from
`MARKET_REGISTRY` and analytical method/input/missing-input/settlement/
calibration/authority fields from `MODEL_STATUS_REGISTRY`.  It emits exactly
one immutable row for every `MarketId`; missing, duplicate, or unknown rows
fail closed.  The authority map keeps production model/probability, Phase 6,
Price-all, Router, Portfolio, selection, SportyBet execution, staking, BET,
and `wager_placed` false.

Each provider observation is bound to the exact event-detail raw SHA-256,
manifest SHA-256, reconstructed inventory SHA-256, source contract identity,
provider-native market and outcome IDs, literal display labels, literal
specifier, and fixture/event identity.  `replay_event_evidence()` verifies and
reconstructs the retained raw and manifest before any semantic row is issued;
caller-supplied detached hashes cannot relabel evidence.

The live proof reuses the reviewed anonymous current discovery and exact event
detail GETs.  Discovery uses the existing request/parser contract as a bounded
20-page prefix (a still-populated provider page cap is recorded rather than
silently paginated or retried).  Detail reads are bounded at twenty, only safe
prematch/bookable events are considered, and every attempt (including a failed
read) is retained in `proof.json`.  No odds are used as football-model inputs.
No login, cookie, wallet, stake, create, reload, share-code, or wager operation
is present.

## Provider policy

Provider matching is exact and market-specific.  It does not add aliases to
`domain/markets.py` and does not perform case folding, fuzzy/substring/nearest
matching, first-match rescue, or cross-line substitution.  The current market
18 `Total Goals` -> `Over/Under` rename remains the explicit PR258 policy only;
it is not a generic alias engine.  Total Goals records every exact observed
line but marks integer/push-capable lines outside the current half-goal model
capability.  Asian Handicap records exact signed specifiers and the observed
home/away orientation, including quarter-line split settlement.

Settlement classes remain explicit: 1X2 partition; exact-line Total Goals
settlement with per-line topology (half-goal lines are ordinary Over/Under
partitions, while integer lines retain an explicit PUSH state);
result-or-total union/complement; complementary BTTS, WEH, and win-to-nil;
overlapping Double Chance and early-payout selections; DNB WIN/PUSH/LOSS; and
full Asian-Handicap WIN/HALF-WIN/PUSH/HALF-LOSS/LOSS where applicable.  The
registry does not authorize ordinary de-vig for push-capable or overlapping
markets.  The per-observation topology is serialized so later reviewed
consumers cannot mistake an integer Total Goals line for a binary partition.

## Currentness and next boundary

`SUPPORTED` means the complete exact provider structure is currently present
and bookable on the observed event. `SUPPORTED_WITH_EXACT_LINE_POLICY` means
the provider structure is present but line/specifier identity remains exact.
`CURRENT_PROVIDER_UNAVAILABLE/UNPROVEN` is explicit for absence, conflict,
incomplete outcomes, stale/future evidence, non-bookable rows, or an event too
close to kickoff.  Event-specific availability is never promoted to a claim
that every fixture offers the market.

The next reviewed boundary is PR-C: an all-market shadow probability/
settlement adapter.  PR-B itself cannot mint pricing or selection authority.
