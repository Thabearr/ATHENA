# Current All-Market Shadow Probability & Settlement Adapter

**Boundary:** research / Shadow only  
**PR:** C of master issue #261  
**Authority:** all production / pricing / selection / BET flags remain `false`

## Path

```
reviewed current fixture
  → research/shadow xG rates (sealed calibrated home/away)
  → exactly one normalized ScoreMatrix
  → canonical ScoreMatrix markets
       MATCH_RESULT, TOTAL_GOALS (half-lines), BTTS,
       DOUBLE_CHANCE, RESULT_OR_OVER_2.5, WIN_TO_NIL,
       DRAW_NO_BET (full WIN/PUSH/LOSS distribution),
       ASIAN_HANDICAP (full/half/push settlement)
  + specialist WEH (frozen Stage 4A/4B inference, 74 features)
  + specialist 1UP/2UP (independent Poisson conditional goal-order lead path)
  → exactly 15 canonical MarketId rows
  → optional PR-B provider-semantic readiness overlay
  → research-only deterministic handoff
```

## What this PR does **not** do

- no Price-all
- no Router
- no Portfolio
- no accumulator construction
- no SportyBet share code
- no stake / wallet / login
- no wager
- no production promotion of the fresh-holdout xG model

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

## Axes kept independent

1. **Mathematical capability** — ScoreMatrix / specialist inference  
2. **Provider semantic capability** — PR B registry  
3. **Production authority** — always false in this boundary  

Example: Asian Handicap can be analytically ready while provider-semantic status remains `CURRENT_PROVIDER_UNPROVEN`.

## Authority map (immutable, all false)

`production_model`, `production_probability`, `score_matrix_production`, `phase6`,  
`production_price_all`, `production_market_router`, `production_portfolio`,  
`production_selection`, `sportybet_execution`, `staking`, `bet`, `wager_placed`

## Next boundary (not this PR)

Join PR B (provider semantics) + PR C (probability/settlement) into:

current SportyBet quotes → Price-all → Router → Portfolio → target 20 / honest shortfall
