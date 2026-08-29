# Shadow Price-all + all-market Router (PR D)

**Boundary:** research / Shadow only  
**Master issue:** #261 Track E  
**Authority:** production Price-all / Router / selection / Portfolio / execution = false

## Lane

```
PR-C CurrentAllMarketShadowFixtureScan (15 MarketId rows)
  + source-bound ShadowExactQuote (inventory + selection join only)
  → price_all_shadow_fixture  (complete audit, no EV prefilter)
  → route_shadow_price_results (strongest robust value OR NO_BET)
```

## Source-bound quotes

`ShadowExactQuote` requires `source_bound_issuance == ATHENA_SHADOW_QUOTE_SOURCE_BOUND_V1`.
Only `build_shadow_exact_quote(inventory, selection, ...)` may issue quotes.
Source raw/manifest/inventory SHAs come exclusively from `SportyBetLiveEventQuoteInventory`.

## Ancestry retained on every price row

- `prc_scan_sha256`
- sealed xG / history prefix (when present)
- source raw / manifest / inventory SHAs
- observation identity
- `score_matrix_audit` (serialized in `to_dict`)

## Router gates

- Ordinary partitions: require `PROPORTIONAL_COMPLETE_PARTITION` + fair + positive robust edge
- Incomplete / cross-snapshot ordinary partitions: REJECTED
- Event probability floor 0.55 applies to all non-full-settlement scalar markets (including Double Chance / 1UP / 2UP)
- DNB/AH: settlement-aware EV; no fake fair/edge
- Empty quote corpus → truthful NO_BET (fixture identity from PR-C scan)

## Explicit non-goals

Portfolio, share-code, stake/wager, Phase-6 candidate minting, WEH feature repair.
