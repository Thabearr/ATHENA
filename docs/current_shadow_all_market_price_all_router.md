# Shadow Price-all + all-market Router (PR D)

**Boundary:** research / Shadow only  
**Master issue:** #261 Track E  
**Authority:** production Price-all / Router / selection / Portfolio / execution = false

## Lane

```
PR-C CurrentAllMarketShadowFixtureScan (15 MarketId rows)
  + exact ShadowExactQuote rows (source-identity fields)
  → price_all_shadow_fixture  (complete audit, no EV prefilter)
  → route_shadow_price_results (strongest robust value OR NO_BET)
```

## What PR D does

- Price every analytically ready PR-C opportunity that has an exact current quote
- Ordinary proportional de-vig only for mutually exclusive exhaustive same-snapshot partitions
- Settlement-aware EV for DNB (WIN/PUSH/LOSS) and AH (full/half/push states)
- Overlapping markets (Double Chance, 1UP/2UP): no false partition de-vig
- Router compares **all** market families — no Total Goals privilege
- Frozen thresholds: event_p ≥ 0.55, net EV > 0, robust EV > 0, robust edge > 0 (when fair exists)
- Retain runner-up and strongest rejected counterfactual
- NO_BET is a successful terminal decision

## What PR D deliberately does NOT do

- Portfolio / target 20 / leg caps (PR E)
- Final current runner
- SportyBet share-code create/reload
- Login / cookies / wallet / stake / wager
- Phase-6 CalibratedValueCandidate minting
- Fake calibration artifacts
- WEH feature acquisition repair
- Fabricating AH provider support when PR-B says unproven

## Quote identity

Exact match on:
fixture, MarketId, OutcomeId, line, provider_event_id, provider_market_id,
provider_specifier, provider_outcome_id, source raw/manifest/inventory SHA.

No fuzzy, nearest-line, or cross-snapshot joins.

## Authority map

Research flags may be true. All production and execution flags remain false.
`wager_placed = false`.
