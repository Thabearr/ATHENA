# ATHENA accumulator priority policy

## Purpose

This boundary controls **consideration order only** for an accumulator request such as a 20-fold for Saturday or a 50-fold over two days.

It does not make a fixture bettable. A fixture must first pass the reviewed fixture, model, market, evidence, pricing, selection and correlation gates that apply to the requested output. `NO_BET` remains valid. A requested fold is never padded with unsupported fixtures merely to reach the requested leg count.

## Bootstrap hierarchy versus model reliability

The static hierarchy in this PR is explicitly a **bootstrap reviewed-coverage order**, not a permanent claim about comparative model accuracy.

ATHENA has multi-league historical evidence. The fact that the Premier League is rank 1 here does **not** mean the models were trained only on the Premier League, and it does not mean every model performs best there.

The next reviewed boundary should derive market/model-specific league reliability from held-out evidence. When such evidence exists, it should supersede the bootstrap order for the relevant model family. For example, the ScoreMatrix/xG family and Win Either Half may legitimately have different league reliability rankings.

The bootstrap policy basis is:

`BOOTSTRAP_REVIEWED_COVERAGE_NOT_MODEL_RELIABILITY`

## Default bootstrap league hierarchy

ATHENA uses strict league exhaustion by default.

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

The first eleven mirror ATHENA's reviewed domestic historical source coverage (`E0`, `SP1`, `I1`, `D1`, `F1`, `N1`, `P1`, `B1`, `SC0`, `T1`, `G1`). The UEFA competitions are deliberately a later bootstrap band: league priority is not a claim that the current model supports them.

The hierarchy is versioned as `athena-league-priority-v2`.

## Exact matching

League aliases use normalized whole-name matching only.

Case, accents and punctuation may normalize, so `Süper Lig` and `SUPER-LIG` resolve to the same configured competition. Substring matching is forbidden. In particular, `Bundesliga (Austria)` cannot accidentally resolve to the German `Bundesliga`.

Unknown competitions receive rank `999` rather than borrowing authority from a similar name.

## Strict exhaustion algorithm

For a target size `N`:

1. start with fixtures that already passed the caller's real eligibility gates;
2. determine the reviewed league-order source for the relevant model family; use model-specific reliability when available, otherwise the versioned bootstrap order;
3. order by league rank;
4. within one league, order fixtures by the transparent fixture-priority key below;
5. consider every eligible/reviewable candidate in the current league before the next league;
6. a rejected candidate does not block progress: the system continues through the remaining candidates in that league;
7. only after that league is exhausted does the next league become reachable;
8. continue until `N` accepted legs are obtained or every candidate is exhausted;
9. only then can rank-999/unclassified leagues be used, and only if those fixtures independently passed all real model/pricing/selection gates;
10. if fewer than `N` survive, return the smaller fold/shortfall. Never manufacture legs.

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

The fixture policy is versioned as `athena-acca-priority-v1`.

## Saturday 20-fold acceptance target

For Saturday 2026-08-22, the operational target is a **20-leg accumulator** built only from fixtures/selections that survive all reviewed gates.

The planner may consider more than 20 candidate fixtures. It must stop only when either:

- 20 authorized legs have been accepted; or
- every eligible candidate in the permitted hierarchy has been exhausted.

If only 17 survive, the scientifically correct output is a 17-leg shortfall report, not three invented selections.

The final Saturday run must preserve, per leg:

- exact FotMob fixture identity and kickoff;
- league-priority source/version and rank;
- exact market/model identifier;
- analytical probability and model/calibration provenance;
- reviewed fixture-intelligence freshness/status;
- exact SportyBet fixture/market/outcome/line reconciliation;
- fresh same-snapshot SportyBet price;
- bookmaker edge/value calculation where authorized;
- selection/BET authority state;
- fixture-priority fields;
- deterministic reason why the leg outranked lower alternatives.

## Interaction with the current accumulator runtime

`AccaFilter` applies the hierarchy after eligibility gates and removes the former arbitrary four-legs-per-league cap. Lower-priority leagues therefore cannot enter simply because four legs have already been taken from a higher-ranked league.

`AccaFilter` no longer performs ad-hoc live NLP/web adjustments. Injuries, availability, fatigue and other football context must already have crossed ATHENA's reviewed upstream evidence/model boundary before a BET candidate reaches the accumulator. This prevents subjective late web scores from bypassing the newer FotMob evidence chain.

`AccumulatorEngine` preserves the priority order when candidates carry priority-policy metadata. It no longer re-sorts those candidates with the legacy weighted "fullproof" score, which would otherwise undo league exhaustion.

Callers without the new priority metadata retain the historical score fallback for compatibility only; the Saturday production path must use the reviewed priority metadata.

## Safety and authority

Priority is not authority.

This policy does **not** set or imply:

- analytical model authority;
- calibration authority;
- SportyBet price authority;
- selection authority;
- BET authority;
- bookmaker execution authority.

A famous or high-ranked league cannot rescue stale evidence, unsupported markets, missing prices, model uncertainty, correlation conflicts or `NO_BET` decisions.
