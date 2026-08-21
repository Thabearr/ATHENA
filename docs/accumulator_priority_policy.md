# ATHENA accumulator priority policy

## Purpose

This boundary controls **consideration order only** for accumulator work such as the Saturday 2026-08-22 20-fold target.

It does not make a fixture bettable. A fixture must still pass the reviewed fixture, model, market, evidence, pricing, selection and correlation gates that apply to the requested output. `NO_BET` remains valid, and a requested fold is never padded merely to reach a number.

## Three different questions

ATHENA now keeps three concepts separate:

1. **competition review priority** — where ATHENA should look first in a real fixture universe;
2. **model reliability** — where reviewed held-out evidence says a particular probability model is more or less reliable;
3. **fixture/selection quality** — which exact already-eligible fixture/market is preferable after probability, risk, freshness and bookmaker value are known.

A competition may be high in review priority without having evidence-ranked model reliability. That distinction is deliberate.

## Source-qualified competition review priority

The source-qualified review policy is versioned as:

`athena-competition-review-priority-v1`

Its basis is:

`BOOTSTRAP_REVIEW_ORDER_NOT_MODEL_RELIABILITY`

For the current Saturday execution boundary the reviewed order is:

| Rank | Competition | Kind | Review band |
|---:|---|---|---:|
| 1 | Premier League | domestic league | 1 |
| 2 | La Liga | domestic league | 1 |
| 3 | Serie A | domestic league | 1 |
| 4 | Bundesliga | domestic league | 1 |
| 5 | Ligue 1 | domestic league | 1 |
| 6 | **DFB-Pokal** | **domestic cup** | 2 |
| 7 | Eredivisie | domestic league | 2 |
| 8 | Primeira Liga | domestic league | 2 |
| 9 | Belgian Pro League | domestic league | 3 |
| 10 | Scottish Premiership | domestic league | 3 |
| 11 | Süper Lig | domestic league | 3 |
| 12 | Greek Super League | domestic league | 3 |
| 999 | unreviewed competition identity | fallback only | 99 |

DFB-Pokal is intentionally inspected before Eredivisie/Primeira Liga and ahead of Belgium, Scotland, Turkey and Greece. This is a **review-search decision**, not a claim that ATHENA's model is statistically more accurate in DFB-Pokal.

The registry is source-qualified. A FotMob candidate with source metadata is resolved from exact country code plus normalized whole competition name. Generic labels do not borrow identity across countries. Examples:

- `ENG + Premier League` resolves to the English Premier League;
- `BLR + Premier League` does not;
- `ITA + Serie A` resolves to Italian Serie A;
- `ECU + Serie A` does not;
- `GER + Bundesliga` resolves to German Bundesliga;
- `AUT + Bundesliga` does not;
- `GER + DFB Pokal` resolves to DFB-Pokal.

When source identity is present, ATHENA never falls back to an ambiguous bare league label. An unreviewed cup such as a generic `GER + Super Cup` remains rank 999 until its own source identity is explicitly reviewed; cup status alone never creates priority.

## Why DFB-Pokal is not one homogeneous signal

Competition priority only decides **where to inspect first**. It does not say every DFB-Pokal tie is equally attractive.

A tie such as a strong top-flight side away to a lower-level opponent can have a very different uncertainty profile from a near-peer cup tie. Rotation, lineup certainty, team-level gap, manager incentives, home advantage and market robustness still belong to reviewed fixture intelligence/model layers.

ATHENA therefore does not encode a hidden 'cup favourite = bet' heuristic. Once reviewed fixture/model signals exist, ordering inside one competition remains lexicographic:

1. higher estimated probability for the **exact priced selection**;
2. lower reviewed fixture/model risk;
3. fresher reviewed evidence;
4. higher validated bookmaker edge in percentage points;
5. earlier kickoff;
6. stable fixture identity/input order as deterministic tie-breakers.

This lets a DFB-Pokal fixture enter the serious review pool early while still allowing ATHENA to reject it later for rotation, stale context, weak model support, bad price, correlation or any other gate.

## Compatibility league hierarchy

`config.league_priority` remains the generic league-only compatibility registry for callers that do not preserve source competition identity. It is versioned as `athena-league-priority-v2` and remains a bootstrap reviewed-coverage order, not a model-accuracy claim.

When exact source competition identity is present, the competition-review registry is the consideration-order authority. When source identity is absent, the existing model-league/league bootstrap path remains the compatibility fallback.

## Model-specific reliability stays separate

The model-specific reliability boundary is `domain.model_league_reliability`, versioned as:

`athena-model-league-reliability-v1`

All 15 canonical markets map to a probability-model reliability family:

- eleven ScoreMatrix markets -> `SCORE_MATRIX_XG`;
- Home Win Either Half -> `WIN_EITHER_HALF_HOME`;
- Away Win Either Half -> `WIN_EITHER_HALF_AWAY`;
- 1UP/2UP -> `EARLY_PAYOUT_LEAD_PATH`.

At this boundary no model family has sufficiently replayable league-level held-out evidence to create an evidence-ranked override. The current model reliability states therefore remain explicit fallbacks with machine-readable blockers. Elevating DFB-Pokal in review order does not alter those blockers.

## Strict exhaustion algorithm

For a target size `N`:

1. begin with fixtures/selections that already passed the caller's real eligibility gates;
2. if exact source competition identity is preserved, resolve the source-qualified competition review rank;
3. if source identity is present but unreviewed, fail closed unless explicit expansion is permitted;
4. if source identity is absent, retain the model-league/league bootstrap compatibility path;
5. exhaust the higher review-priority competition before moving to the next one;
6. within one competition, use the transparent fixture-quality key above;
7. a rejected candidate never blocks progress through remaining candidates;
8. continue until `N` accepted legs exist or every permitted candidate is exhausted;
9. if fewer than `N` survive, return the smaller fold/shortfall; never manufacture legs.

Caller-provided model reliability ranks are ignored. Source-qualified competition review priority and reviewed model reliability are separate versioned registries.

## Saturday 20-fold acceptance target

For Saturday 2026-08-22, the operational target remains a **20-leg accumulator** built only from fixtures/selections that survive all reviewed gates.

The real FotMob Saturday capture contains DFB-Pokal fixtures that were previously left in the generic rank-999 bucket because the first policy was league-centric. The new review policy deliberately brings exact `GER + DFB Pokal` fixtures into the serious first-pass pool without promoting unrelated cups or same-name foreign competitions.

The final Saturday run must still preserve, per leg, exact FotMob fixture identity/kickoff, source-qualified competition review basis/version/rank, model-family reliability basis, exact market/model/calibration identity, reviewed fixture-intelligence freshness, exact SportyBet reconciliation and fresh same-snapshot price, value/authority state and deterministic fixture-priority reasons.

## Interaction with the current accumulator runtime

`AccaFilter` applies priority only after its eligibility gates and has no arbitrary four-legs-per-league cap. It does not perform ad-hoc live NLP/web injury, fatigue, motivation or pressure adjustments; current football context must already have crossed ATHENA's reviewed upstream evidence/model boundary.

`AccumulatorEngine` preserves incoming priority order when candidates carry priority-policy metadata. It does not re-sort those candidates with the legacy weighted score. Callers without reviewed priority metadata retain the historical score fallback for compatibility only; the Saturday path must preserve the reviewed source competition metadata.

The accumulator priority compatibility envelope is versioned as `athena-acca-priority-v3`.

## Safety and authority

Priority is not authority. This policy does **not** set or imply analytical model authority, calibration authority, SportyBet price authority, selection authority, BET authority or bookmaker execution authority.

A famous club, large team-level gap, cup label or high review rank cannot rescue stale evidence, unsupported markets, missing prices, model uncertainty, correlation conflicts or `NO_BET` decisions.
