# SportyBet reviewed canonical market mapping

## Purpose

This is the next SportyBet boundary after PRs #163-#166. It maps exact provider-native SportyBet selection identities into ATHENA's canonical market registry only after the event has a durable, source-replayed `UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED` receipt. Mapping is explicit-review driven: no fuzzy market names, outcome guesses, odds-based inference, event proximity, or guessed provider IDs.

## Full 15-market scope

The target is the complete current `domain/markets.py` registry: Match Result 1X2, Total Goals, Double Chance, Asian Handicap, Draw or Over 2.5, Away or Over 2.5, Home Team or Over 2.5, BTTS/GG-NG, Home Win to Nil, Away Win to Nil, Home Win Either Half, Away Win Either Half, Draw No Bet, Match Result 1UP, and Match Result 2UP.

The implementation fails closed if that exact 15-ID registry drifts. `all_15_target_markets_represented` means only that at least one exact reviewed provider selection maps into each target ID; it does not imply every line/outcome is present, fresh, model-supported, or bettable.

## Required source chain

The public builder requires PR #164's durable reconciliation receipt and the complete `FullUtcReconciliationSourceBundle`. Verification re-executes PR #163 from preserved SportyBet, Terms, Sportradar and FotMob sources and requires exact stored-byte equality.

Only exact `UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED` with fixture-reconciliation authority may continue. The native inventory must be the same exact SHA-256 and event/evidence identity already bound into that reconciliation.

## Explicit review decisions

Each `ReviewedCanonicalMappingDecision` binds one exact provider selection: SportyBet event ID, market ID, source-preserved market name, exact specifier, outcome ID, source-preserved selection label, target ATHENA `MarketId`, target `OutcomeId`, and canonical line where required.

Source labels must exist and match exactly. Opaque IDs without reviewed labels stay unmapped. Duplicate provider decisions fail closed, and two provider selections cannot claim one canonical market/outcome/line identity.

## Lines and promotions

Total Goals requires exact `total=<decimal>` and Asian Handicap exact `hcp=<decimal>`; the provider decimal must equal the canonical line. A provider specifier cannot disappear into a canonical non-line market.

1UP/2UP identifiers may be mapped so the complete 15-market namespace is
preserved. Historical calls without the later exact SportyBet early-payout
settlement receipt remain `PROVIDER_PROMOTION_RULES_UNPROVEN`, preserving the
earlier receipt semantics. A new mapping call may supply that exact immutable
receipt and its canonical bytes. Only then may the exact early-payout
selection carry
`REVIEWED_SPORTYBET_EARLY_PAYOUT_SETTLEMENT_EQUIVALENCE` and its settlement
receipt SHA. This upgrades provider settlement equivalence only; price
freshness, pricing, selection, execution, and BET authority remain false.

The receipt binds official SportyBet 1X2/1UP/2UP help clauses and the exact
reviewed `one_x_two_one_up` / `one_x_two_two_up` site-configuration key
projection. Any changed evidence or receipt bytes fail closed. Standard
mappings continue to carry `REVIEWED_STANDARD_SETTLEMENT_EQUIVALENCE` only for
the exact reviewed provider selection.

## Price and execution boundary

Mapped selections retain exact source odds and availability for traceability, but the reviewed Lite source still proves neither provider quote time nor provider snapshot identity. Consequently `provider_quote_at` and `provider_snapshot_id` remain null, while fresh-price, pricing, model-integration, selection, slip, booking-code, SportyBet execution and BET authority remain false. No SportyBet network I/O is added.

After real user-controlled evidence and a unique source-replayed fixture receipt exist, explicit decisions can establish exact mappings for observed selections. Provider-native price freshness/snapshot identity remains the next independent trust gate.
