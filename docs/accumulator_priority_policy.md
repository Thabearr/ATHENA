# ATHENA accumulator priority policy

## Purpose

This boundary controls **consideration order only** for accumulator work such as the Saturday 2026-08-22 20-fold target.

It does not make a fixture bettable. A fixture must still pass the reviewed fixture, model, market, evidence, pricing, selection and correlation gates that apply to the requested output. `NO_BET` remains valid, and a requested fold is never padded merely to reach a number.

## Three different questions

ATHENA keeps three concepts separate:

1. **competition review priority** — where ATHENA should look first in a real fixture universe;
2. **model reliability** — where reviewed held-out evidence says a particular probability model is more or less reliable;
3. **fixture/selection quality** — which exact already-eligible fixture/market is preferable after probability, risk, freshness and bookmaker value are known.

A competition may be high in review priority without having evidence-ranked model reliability.

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
| 6 | Primeira Liga | domestic league | 2 |
| 7 | Süper Lig | domestic league | 2 |
| 8 | Eredivisie | domestic league | 2 |
| 9 | **FA Cup** | **domestic cup** | 3 |
| 9 | **Copa del Rey** | **domestic cup** | 3 |
| 9 | **Coppa Italia** | **domestic cup** | 3 |
| 9 | **DFB-Pokal** | **domestic cup** | 3 |
| 9 | **Coupe de France** | **domestic cup** | 3 |
| 10 | Belgian Pro League | domestic league | 4 |
| 11 | Scottish Premiership | domestic league | 4 |
| 12 | Greek Super League | domestic league | 4 |
| 999 | unreviewed competition identity | fallback only | 99 |

The major domestic cups of the top-five countries deliberately share one review rank. They sit **below Primeira Liga, Süper Lig and Eredivisie, but above Belgian Pro League, Scottish Premiership and Greek Super League**.

The shared cup rank is intentional. ATHENA does not arbitrarily say FA Cup is more valuable than Copa del Rey or DFB-Pokal. Once the cup band is reached, exact fixture quality breaks the tie using reviewed probability, risk, freshness, bookmaker value, kickoff and stable identity.

The registry is source-qualified. A FotMob candidate with source metadata is resolved from exact country code plus normalized whole competition name. Generic labels do not borrow identity across countries. Examples:

- `ENG + Premier League` resolves to the English Premier League;
- `BLR + Premier League` does not;
- `ITA + Serie A` resolves to Italian Serie A;
- `ECU + Serie A` does not;
- `GER + Bundesliga` resolves to German Bundesliga;
- `AUT + Bundesliga` does not;
- `ENG + FA Cup` resolves to FA Cup;
- `ESP + Copa del Rey` resolves to Copa del Rey;
- `ITA + Coppa Italia` resolves to Coppa Italia;
- `GER + DFB Pokal` resolves to DFB-Pokal;
- `FRA + Coupe de France` resolves to Coupe de France.

When source identity is present, ATHENA never falls back to an ambiguous bare competition label. An unreviewed competition such as a generic `GER + Super Cup` remains rank 999 until its exact source identity is explicitly reviewed; the word `Cup` never creates priority by itself.

## Cup fixtures are still fixture-specific

Competition priority decides **where to inspect first**. It does not say every major-cup tie is equally attractive.

A strong top-flight side away to a lower-level opponent can have a very different uncertainty profile from a near-peer cup tie. Rotation, lineup certainty, team-level gap, manager incentives, home advantage and market robustness still belong to reviewed fixture-intelligence/model layers.

ATHENA therefore does not encode a hidden `cup favourite = bet` heuristic. Within one review rank the fixture-quality ordering remains lexicographic:

1. higher estimated probability for the **exact priced selection**;
2. lower reviewed fixture/model risk;
3. fresher reviewed evidence;
4. higher validated bookmaker edge in percentage points;
5. earlier kickoff;
6. stable fixture identity/input order as deterministic tie-breakers.

A cup fixture may enter the serious review pool before Belgium/Scotland/Greece and still be rejected later for rotation, stale context, weak model support, bad price, correlation or any other gate.

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

At this boundary no model family has sufficiently replayable league-level held-out evidence to create an evidence-ranked override. The current model reliability states remain explicit fallbacks with machine-readable blockers. Review priority does not alter those blockers.

## Strict exhaustion algorithm

For a target size `N`:

1. begin with fixtures/selections that already passed the caller's real eligibility gates;
2. if exact source competition identity is preserved, resolve the source-qualified competition review rank;
3. if source identity is present but unreviewed, fail closed unless explicit expansion is permitted;
4. if source identity is absent, retain the model-league/league bootstrap compatibility path;
5. exhaust the higher review-priority rank before moving to the next one;
6. where multiple competitions share a rank, order their fixtures by the transparent fixture-quality key rather than arbitrary competition prestige;
7. a rejected candidate never blocks progress through remaining candidates;
8. continue until `N` accepted legs exist or every permitted candidate is exhausted;
9. if fewer than `N` survive, return the smaller fold/shortfall; never manufacture legs.

Caller-provided model reliability ranks are ignored. Source-qualified competition review priority and reviewed model reliability are separate versioned registries.

## Saturday 20-fold acceptance target

For Saturday 2026-08-22, the operational target remains a **20-leg accumulator** built only from fixtures/selections that survive all reviewed gates.

The exact Saturday FotMob capture currently contains 11 DFB-Pokal fixtures. They enter the rank-9 major-cup band. The same architecture is now ready for exact FA Cup, Copa del Rey, Coppa Italia and Coupe de France source identities when those competitions are present in a fixture universe; they do not need a future DFB-specific exception.

The final Saturday run must still preserve, per leg, exact FotMob fixture identity/kickoff, source-qualified competition review basis/version/rank, model-family reliability basis, exact market/model/calibration identity, reviewed fixture-intelligence freshness, exact SportyBet reconciliation and fresh same-snapshot price, value/authority state and deterministic fixture-priority reasons.

## Interaction with the current accumulator runtime

`AccaFilter` applies priority only after its eligibility gates and has no arbitrary four-legs-per-league cap. It does not perform ad-hoc live NLP/web injury, fatigue, motivation or pressure adjustments; current football context must already have crossed ATHENA's reviewed upstream evidence/model boundary.

`AccumulatorEngine` preserves incoming priority order when candidates carry priority-policy metadata. It does not re-sort those candidates with the legacy weighted score. Callers without reviewed priority metadata retain the historical score fallback for compatibility only; the Saturday path must preserve the reviewed source competition metadata.

The accumulator priority compatibility envelope is versioned as `athena-acca-priority-v3`.

## Safety and authority

Priority is not authority. This policy does **not** set or imply analytical model authority, calibration authority, SportyBet price authority, selection authority, BET authority or bookmaker execution authority.

A famous club, large team-level gap, cup label or high review rank cannot rescue stale evidence, unsupported markets, missing prices, model uncertainty, correlation conflicts or `NO_BET` decisions.
