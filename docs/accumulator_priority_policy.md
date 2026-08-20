# ATHENA accumulator priority policy

## Purpose

This boundary controls **consideration order only** for an accumulator request such as a 50-fold over two days.

It does not make a fixture bettable. A fixture must first pass the reviewed fixture, model, market, evidence, pricing, selection and correlation gates that apply to the requested output. `NO_BET` remains valid. A requested 50-fold is never padded with unsupported fixtures merely to reach 50 legs.

## Default league hierarchy

ATHENA now uses strict league exhaustion by default.

| Rank | League | Band | Basis |
|---:|---|---:|---|
| 1 | Premier League | 1 | core reviewed domestic-history coverage |
| 2 | La Liga | 1 | core reviewed domestic-history coverage |
| 3 | Serie A | 1 | core reviewed domestic-history coverage |
| 4 | Bundesliga | 1 | core reviewed domestic-history coverage |
| 5 | Ligue 1 | 1 | core reviewed domestic-history coverage |
| 6 | Eredivisie | 2 | reviewed domestic-history expansion coverage |
| 7 | Primeira Liga | 2 | reviewed domestic-history expansion coverage |
| 8 | Belgian Pro League | 2 | reviewed domestic-history expansion coverage |
| 9 | Scottish Premiership | 2 | reviewed domestic-history expansion coverage |
| 10 | Süper Lig | 2 | reviewed domestic-history expansion coverage |
| 11 | Greek Super League | 2 | reviewed domestic-history expansion coverage |
| 12 | UEFA Champions League | 3 | continental expansion; still requires explicit model support |
| 13 | UEFA Europa League | 3 | continental expansion; still requires explicit model support |
| 14 | UEFA Conference League | 3 | continental expansion; still requires explicit model support |
| 999 | unclassified competition | fallback only | only after configured leagues are exhausted |

The first eleven mirror ATHENA's reviewed domestic historical source coverage (`E0`, `SP1`, `I1`, `D1`, `F1`, `N1`, `P1`, `B1`, `SC0`, `T1`, `G1`). The UEFA competitions are deliberately a later band: league priority is not a claim that the current model supports them.

The hierarchy is versioned as `athena-league-priority-v2`.

## Exact matching

League aliases use normalized whole-name matching only.

Case, accents and punctuation may normalize, so `Süper Lig` and `SUPER-LIG` resolve to the same configured competition. Substring matching is forbidden. In particular, `Bundesliga (Austria)` cannot accidentally resolve to the German `Bundesliga`.

Unknown competitions receive rank `999` rather than borrowing authority from a similar name.

## Strict exhaustion algorithm

For a target size `N`:

1. start with fixtures that already passed the caller's real eligibility gates;
2. order by configured league rank;
3. within one league, order fixtures by the transparent fixture-priority key below;
4. consider every eligible/reviewable candidate in league rank 1 before rank 2;
5. a rejected rank-1 candidate does not block progress: the system continues through the remaining rank-1 candidates;
6. only after rank 1 is exhausted does rank 2 become reachable;
7. continue until `N` accepted legs are obtained or every candidate is exhausted;
8. only then can rank-999/unclassified leagues be used by the accumulator integration, and only if those fixtures independently passed all real model/pricing/selection gates;
9. if fewer than `N` survive, return the smaller fold/shortfall. Never manufacture legs.

This means a 50-fold request does not mean "pick the best 50 from the whole world." It means "fill from the strongest configured competition pool in order, descending only when the higher-priority pool is exhausted."

## Fixture priority inside a league

ATHENA uses a lexicographic key rather than an opaque weighted score:

1. higher estimated probability for the exact priced selection;
2. lower fixture risk score;
3. fresher evidence;
4. higher **validated bookmaker** edge in percentage points;
5. earlier kickoff;
6. stable fixture identity/input order as deterministic tie-breakers.

Missing quality signals sort behind present signals within the same league.

The priority planner never treats the legacy global-baseline `edge` field as bookmaker value. Only `edge_pp` explicitly marked `edge_is_bookmaker_value=true` participates in the fixture-priority key.

The fixture policy is versioned as `athena-acca-priority-v1`.

## Example: requested 50-fold across two days

Assume, after all real gates:

- Premier League: 15 eligible fixtures across the window;
- La Liga: 14;
- Serie A: 12;
- Bundesliga: 10;
- Ligue 1: 8;
- all other leagues: additional candidates.

ATHENA considers all 15 Premier League fixtures first, then all 14 La Liga fixtures, then all 12 Serie A fixtures. That gives 41. It then needs only the first 9 eligible Bundesliga fixtures according to the fixture-priority key and stops at 50. Ligue 1 and lower bands never enter that slip.

If correlation/duplicate-team/category gates reject three of those Bundesliga candidates, the system keeps walking the remaining Bundesliga pool before moving to Ligue 1.

If all configured leagues are exhausted at 47 accepted legs, ATHENA may inspect rank-999 fallback competitions only if their fixtures have genuine independent model/pricing/selection authority. If none qualify, the correct result is a 47-fold/shortfall, not a fabricated 50-fold.

## Interaction with the current accumulator runtime

`AccaFilter` applies the hierarchy after its existing eligibility gates and removes the former arbitrary four-legs-per-league cap. Lower-priority leagues therefore cannot enter simply because four legs have already been taken from a higher-ranked league.

`AccumulatorEngine` preserves the priority order when the candidates carry priority-policy metadata. It no longer re-sorts those candidates with the legacy weighted "fullproof" score, which would otherwise undo league exhaustion.

Callers without the new priority metadata retain the historical score fallback for compatibility.

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
