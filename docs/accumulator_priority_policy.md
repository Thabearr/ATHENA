# ATHENA accumulator priority policy

## Purpose

This boundary controls **consideration order only** for an accumulator request such as a 20-fold for Saturday or a 50-fold over two days.

It does not make a fixture bettable. A fixture must first pass the reviewed fixture, model, market, evidence, pricing, selection and correlation gates that apply to the requested output. `NO_BET` remains valid. A requested fold is never padded with unsupported fixtures merely to reach the requested leg count.

## Bootstrap hierarchy versus model reliability

The static hierarchy is explicitly a **bootstrap reviewed-coverage order**, not a permanent claim about comparative model accuracy.

ATHENA has multi-league historical evidence. The fact that the Premier League is rank 1 in the bootstrap registry does **not** mean the models were trained only on the Premier League, and it does not mean every model performs best there.

The model-specific reliability boundary is `domain.model_league_reliability`. It may supersede the bootstrap order for a model family only after exact reviewed held-out league metrics authorize a ranking. At the current boundary no family has enough evidence to do so, so every model family retains an explicit bootstrap fallback with a machine-readable reason.

The bootstrap policy basis is:

`BOOTSTRAP_REVIEWED_COVERAGE_NOT_MODEL_RELIABILITY`

## Default bootstrap league hierarchy

| Rank | League | Band | Bootstrap basis |
|---:|---|---:|---|
| 1 | Premier League | 1 | reviewed domestic-history coverage |
| 2 | La Liga | 1 | reviewed domestic-history coverage |
| 3 | Serie A | 1 | reviewed domestic-history coverage |
| 4 | Bundesliga | 1 | reviewed domestic-history coverage |
| 5 | Ligue 1 | 1 | reviewed domestic-history coverage |
| 6 | Eredivisie | 2 | reviewed domestic-history coverage |
| 7 | Primeira Liga | 2 | reviewed domestic-history coverage |
| 8 | Belgian Pro League | 2 | reviewed domestic-history coverage |
| 9 | Scottish Premiership | 2 | reviewed domestic-history coverage |
| 10 | Süper Lig | 2 | reviewed domestic-history coverage |
| 11 | Greek Super League | 2 | reviewed domestic-history coverage |
| 12 | UEFA Champions League | 3 | continental expansion; explicit model support still required |
| 13 | UEFA Europa League | 3 | continental expansion; explicit model support still required |
| 14 | UEFA Conference League | 3 | continental expansion; explicit model support still required |
| 999 | unclassified competition | fallback only | only after configured leagues are exhausted |

The first eleven mirror ATHENA's reviewed domestic historical source coverage (`E0`, `SP1`, `I1`, `D1`, `F1`, `N1`, `P1`, `B1`, `SC0`, `T1`, `G1`). UEFA competitions are a later bootstrap band: priority is not model support.

The bootstrap hierarchy is versioned as `athena-league-priority-v2`.

## Model-specific reliability

All 15 canonical markets map to an explicit probability-model reliability family:

- eleven ScoreMatrix markets -> `SCORE_MATRIX_XG`;
- Home Win Either Half -> `WIN_EITHER_HALF_HOME`;
- Away Win Either Half -> `WIN_EITHER_HALF_AWAY`;
- 1UP/2UP -> `EARLY_PAYOUT_LEAD_PATH`.

The reliability policy is versioned as `athena-model-league-reliability-v1`.

Current evidence-ranked overrides are intentionally empty:

- xG/ScoreMatrix: frozen validation lacks competition identity, so league robustness cannot be evaluated;
- Home/Away WEH: reviewed Stage 4B proves subgroup analysis exists, but the exact per-league metric rows are not committed/replayable from the current repository boundary, so prose is not converted into a comparative ranking;
- 1UP/2UP: no independent league-stratified held-out probability validation exists.

See `docs/model_specific_league_reliability.md` for the exact evidence references and blockers.

## Exact matching

League aliases use normalized whole-name matching only. Case, accents and punctuation may normalize, but substring/fuzzy matching is forbidden. `Bundesliga (Austria)` cannot accidentally resolve to the German `Bundesliga`.

Unknown competitions receive rank `999` rather than borrowing authority from a similar name.

## Strict exhaustion algorithm

For a target size `N`:

1. start with fixtures that already passed the caller's real eligibility gates;
2. resolve the candidate's exact canonical market/model family;
3. use a reviewed model-specific league rank only if that family has authorized held-out league evidence;
4. otherwise retain the versioned bootstrap league rank and record the blocker;
5. within one league, order fixtures by the transparent fixture-priority key below;
6. consider every eligible/reviewable candidate in the current league before the next league;
7. a rejected candidate does not block progress: continue through the remaining candidates in that league;
8. continue until `N` accepted legs are obtained or every candidate is exhausted;
9. rank-999/unclassified leagues are reachable only when explicitly allowed and after configured leagues are exhausted;
10. if fewer than `N` survive, return the smaller fold/shortfall. Never manufacture legs.

Caller-provided model reliability ranks are ignored. The reviewed registry is the only source that may create a model-specific league override.

## Fixture priority inside a league

ATHENA uses a lexicographic key rather than an opaque weighted score:

1. higher estimated probability for the **exact priced selection**;
2. lower reviewed fixture/model risk;
3. fresher reviewed evidence;
4. higher **validated bookmaker** edge in percentage points;
5. earlier kickoff;
6. stable fixture identity/input order as deterministic tie-breakers.

Missing quality signals sort behind present signals within the same league.

The priority planner never treats the legacy global-baseline `edge` field as bookmaker value. Only `edge_pp` explicitly marked `edge_is_bookmaker_value=true` participates in the fixture-priority key.

The accumulator priority policy is versioned as `athena-acca-priority-v2`.

## Saturday 20-fold acceptance target

For Saturday 2026-08-22, the operational target is a **20-leg accumulator** built only from fixtures/selections that survive all reviewed gates.

The planner may consider more than 20 candidate fixtures. It must stop only when either 20 authorized legs have been accepted or every eligible candidate in the permitted hierarchy has been exhausted. If only 17 survive, the correct output is a 17-leg shortfall report, not three invented selections.

The final Saturday run must preserve, per leg, exact FotMob fixture identity/kickoff, model-family league-priority basis/version/rank, exact market/model/calibration identity, reviewed fixture-intelligence freshness, exact SportyBet reconciliation and fresh same-snapshot price, value/authority state, and deterministic fixture-priority reasons.

## Interaction with the current accumulator runtime

`AccaFilter` applies priority only after its eligibility gates and has no arbitrary four-legs-per-league cap. It does not perform ad-hoc live NLP/web injury, fatigue, motivation, or pressure adjustments; current football context must already have crossed ATHENA's reviewed upstream evidence/model boundary.

`AccumulatorEngine` preserves the incoming priority order when candidates carry priority-policy metadata. It does not re-sort those candidates with the legacy weighted score. Callers without reviewed priority metadata retain the historical score fallback for compatibility only; the Saturday path must use the reviewed metadata.

## Safety and authority

Priority is not authority. This policy does **not** set or imply analytical model authority, calibration authority, SportyBet price authority, selection authority, BET authority, or bookmaker execution authority.

A famous or high-ranked league cannot rescue stale evidence, unsupported markets, missing prices, model uncertainty, correlation conflicts, or `NO_BET` decisions.
