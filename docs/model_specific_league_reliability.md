# Model-specific league reliability

## Purpose

PR #195 introduced a deterministic bootstrap league hierarchy for large accumulator requests. This boundary adds the trust rule for replacing that bootstrap order with actual model-specific league reliability.

A league may outrank another for one model family only when ATHENA has reviewed, league-identified held-out evidence with exact replayable metrics for that family. League prestige, caller-supplied ranks, qualitative summaries, bookmaker prices, and aggregate model success do not establish comparative league reliability.

## Model families

All 15 canonical markets map to one of four reliability families:

- `SCORE_MATRIX_XG`: Match Result, Asian Handicap, Total Goals, the three Result-or-Over markets, Double Chance, BTTS, Draw No Bet, and Home/Away Win to Nil;
- `WIN_EITHER_HALF_HOME`;
- `WIN_EITHER_HALF_AWAY`;
- `EARLY_PAYOUT_LEAD_PATH`: Match Result 1UP and Match Result 2UP.

This mapping reflects the probability mechanism that would need league-level validation. It does not grant analytical, selection, pricing, or BET authority.

## Current reviewed state

No family is evidence-ranked yet.

### ScoreMatrix/xG

The reviewed UTC-native expected-goals validation found useful signal versus Elo-only, but its own result review explicitly says league/competition robustness is blocked because the frozen projection does not carry competition identity. Therefore there is no lawful xG league ranking at this boundary.

Source:

- `docs/fotmob_utc_native_expected_goals_model_validation_result_review.md`

Primary future reliability metric: mean joint Poisson NLL, with the pre-registered calibration diagnostics retained as secondary evidence.

### Home Win Either Half

Stage 4B contains genuine league subgroup analysis and the documentation reports qualitative conclusions, including that ten of twelve supported leagues improved both log loss and Brier under Home isotonic calibration, while `I1` worsened both and `E0` was mixed/approximately neutral.

That is not enough to create a full comparative league ranking. The exact 356-row subgroup CSV is hashed by the committed manifest but its per-league rows are not committed or replayable from this repository boundary. ATHENA therefore does not manufacture a ranking from prose.

Sources:

- `docs/win_either_half_calibration_research.md`
- `artifacts/research-manifests/win-either-half-calibration-v1.json`

Primary future reliability metrics: binary log loss, then Brier score, then ECE, using independent final-test rows and the predeclared minimum-support rule.

### Away Win Either Half

Away retained identity calibration. Exact comparative final-test league metrics are likewise not committed here, so no league ranking is authorized.

### 1UP/2UP

The lead-path probability mechanism and SportyBet semantics are reviewed analytically, but there is no independent league-stratified probability validation. No 1UP/2UP league ranking is authorized.

## Runtime behavior

`domain.model_league_reliability` is the only model-specific league-ranking source for the accumulator priority planner.

For each candidate:

1. resolve its exact canonical market ID;
2. map that market to its model reliability family;
3. resolve the exact normalized league through the bootstrap registry;
4. use a reviewed evidence rank only if that family explicitly has `ranking_authorized=true` and the league has a committed reviewed rank;
5. otherwise retain the bootstrap rank and record the exact blocker.

Caller fields such as `model_league_priority_rank`, `model_league_ranking_authorized`, or an arbitrary reliability score are ignored and overwritten by the reviewed resolver.

The accumulator annotations now expose:

- `model_league_reliability_policy_version`;
- `model_league_family`;
- `model_league_priority_rank`;
- `model_league_priority_basis`;
- `model_league_ranking_authorized`;
- `model_league_reliability_reason`;
- `model_league_reliability_evidence`.

The older `league_priority_rank` remains the bootstrap rank for compatibility and audit. `model_league_priority_rank` is the effective consideration rank.

## Saturday implication

For the Saturday 20-fold target, this boundary prevents us from pretending that Premier League-first is scientifically proven for every market. Until exact model-family league evidence is available, the bootstrap order remains visible as a fallback rather than being mislabeled as model reliability.

The next xG champion/challenger boundary should preserve competition identity in its evaluation output so ScoreMatrix-derived markets can finally earn evidence-ranked league ordering. If exact Win Either Half subgroup metric bytes are recovered and verified against the frozen manifest hash, they can support a separate reviewed WEH reliability boundary.

## Safety

This policy grants no probability, pricing, selection, execution, or BET authority. It only controls consideration order among candidates that already passed the relevant upstream gates. `NO_BET` and requested-fold shortfall remain valid outcomes.
