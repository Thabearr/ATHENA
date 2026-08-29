# Current All-Market Shadow Probability & Settlement Adapter

**Boundary:** research / Shadow only  
**PR:** C of master issue #261  
**Authority:** all production / pricing / selection / BET flags remain `false`

## Two layers

### A. Lower-level mathematical composition — `scan_fixture_all_markets`

Accepts already-reviewed mathematical inputs (research xG rates, optional reviewed-style
WEH 74-feature mapping, optional provider-status overlay strings).

It does **not** claim those inputs are the complete current source state.

### B. Current source-bound entrypoint — `scan_current_fixture_all_markets`

- **xG** is replayed from the complete current PR151 durable-history handoff
  (`CurrentLatestDurableFreshHistoryHandoff`). Raw caller xG floats are rejected.
- **Provider semantics** come from the typed PR-B `CurrentSportyBetSemanticRegistry`.
  Arbitrary `Mapping[MarketId, str]` cannot grant support on this lane.
- **TG / AH lines** come from exact PR-B current bookable observations only.
- **WEH** requires a reviewed source-bound specialized feature handoff. PR C does
  not invent one; the current entrypoint therefore keeps WEH at
  `SPECIALIST_FEATURES_MISSING`. Raw `weh_feature_row` is **not** accepted here
  and cannot mint current readiness.

## Path

```
complete current durable history (PR151)
  → sealed research/shadow xG rates
  → exactly one normalized ScoreMatrix
  → canonical ScoreMatrix markets
       MATCH_RESULT, TOTAL_GOALS (exact half-lines from PR-B), BTTS,
       DOUBLE_CHANCE, RESULT_OR_OVER_2.5, WIN_TO_NIL,
       DRAW_NO_BET (full WIN/PUSH/LOSS distribution),
       ASIAN_HANDICAP (exact quarter-lines; full/half/push settlement)
  + specialist WEH (blocked until source-bound feature handoff)
  + specialist 1UP/2UP (independent Poisson conditional goal-order lead path)
  → exactly 15 canonical MarketId rows
  → typed PR-B provider-semantic readiness overlay
  → research-only deterministic handoff
```

## Provider status binding

Provider readiness is derived from the typed PR-B enum
`ProviderSemanticStatus`:

| Status | Provider axis |
|--------|---------------|
| `SUPPORTED` | ready |
| `SUPPORTED_WITH_EXACT_LINE_POLICY` | ready |
| `CURRENT_PROVIDER_UNAVAILABLE_UNPROVEN` (value: `CURRENT_PROVIDER_UNAVAILABLE/UNPROVEN`) | blocked |
| any other / unknown / forged token | blocked (fail closed) |

Supported math does not override a blocked provider axis: disposition becomes
`ANALYTICAL_READY_PROVIDER_BLOCKED`.

## What this PR does **not** do

- no Price-all
- no Router
- no Portfolio
- no accumulator construction
- no SportyBet share code
- no stake / wallet / login
- no wager
- no production promotion of the fresh-holdout xG model
- no caller-minted current WEH feature values

The fresh holdout blocks **production** promotion.  
It does **not** prohibit research/shadow use of the frozen reviewed xG model.

## Composition (reuse, do not rewrite)

| Capability | Reviewed module |
|------------|-----------------|
| ScoreMatrix | `domain/score_matrix.py` |
| Ordinary + settlement market projection | `domain/score_matrix_market_probabilities.py` |
| DNB / AH full settlement | `domain/score_matrix_settlement.py` |
| 1UP / 2UP lead path | `domain/early_payout_lead_path_probabilities.py` |
| WEH inference | `domain/win_either_half_inference.py` |
| Canonical markets | `domain/markets.py` |
| Model status contract | `domain/model_status.py` |
| Provider semantics (overlay only) | `domain/current_sportybet_semantic_registry.py` (PR B) |
| Current durable history | `domain/current_fotmob_latest_durable_fresh_history.py` |

## Axes kept independent

1. **Mathematical capability** — ScoreMatrix / specialist inference  
2. **Provider semantic capability** — typed PR-B registry  
3. **Production authority** — always false in this boundary  

Example: Asian Handicap can be analytically ready while provider-semantic status
remains `CURRENT_PROVIDER_UNAVAILABLE/UNPROVEN`.

## Authority map (immutable, all false)

`production_model`, `production_probability`, `score_matrix_production`, `phase6`,  
`production_price_all`, `production_market_router`, `production_portfolio`,  
`production_selection`, `sportybet_execution`, `staking`, `bet`, `wager_placed`

## Next boundary (not this PR)

Join PR B (provider semantics) + PR C (probability/settlement) into:

current SportyBet quotes → Price-all → Router → Portfolio → target 20 / honest shortfall

A later source-bound WEH feature handoff is required before WEH becomes
fixture-eligible on the current lane.
