# ATHENA accumulator priority policy

## Purpose

This boundary implements **Athena Football Competition Hierarchy v1.0** as consideration order for accumulator work.

It does not make a fixture bettable. Competition rank controls where ATHENA looks first; every fixture still has to pass the reviewed identity, evidence, model, market, freshness, pricing, selection and correlation gates. `NO_BET` remains valid and a requested fold is never padded merely to reach a target size.

## Separate club and international hierarchies

Club and international country football have separate priority spaces. They must not be mechanically compared inside one accumulator priority plan.

The club hierarchy is versioned as:

- competition policy: `athena-competition-review-priority-v2`
- league-only compatibility policy: `athena-league-priority-v3`
- accumulator priority envelope: `athena-acca-priority-v4`

The policy basis is `ATHENA_FOOTBALL_COMPETITION_HIERARCHY_V1`.

## Club master order

| Tier | Band | Base score | Competition order |
|---:|---|---:|---|
| 1 | S | 100 | UEFA Champions League → UEFA Europa League → UEFA Conference League |
| 2 | A | 88–80 | Premier League → La Liga → Serie A → Bundesliga → Ligue 1 |
| 3 | B | 78 | FA Cup / EFL Cup / Copa del Rey / Coppa Italia / DFB-Pokal / Coupe de France |
| 4 | C1 | 76–70 | Eredivisie → Primeira Liga → Süper Lig → Belgian Pro League |
| 5 | C2 | 68–60 | Eliteserien → Danish Superliga → Allsvenskan → Swiss Super League → Greek Super League |
| 6 | D | 58 | EFL Championship |
| 7 | E | 54 | Major League Soccer |
| 8 | F | 50 | Saudi Pro League |
| 9 | G | 45 or lower | other explicitly approved leagues |

Scottish Premiership is retained as an already-reviewed historical competition in Tier G. That does **not** make every unknown league a Tier-G league. Unrecognized competitions remain rank/tier `999` unless explicitly approved.

The resolved order is therefore UEFA → Big Five → Big Five cups → preferred European top flights → Championship → MLS → Saudi → explicitly approved long tail.

## Exact source-qualified identity

When provider metadata exists, priority is resolved only from an exact country-code + normalized whole competition-name pair. Generic same-name competitions in another country never inherit the intended rank.

Reviewed FotMob pairs include, among others:

- `INT + Champions League` → UEFA Champions League;
- `INT + Europa League` → UEFA Europa League;
- `INT + Conference League` → UEFA Conference League;
- `ENG + Premier League` → Premier League;
- `ENG + FA Cup` → FA Cup;
- `ENG + League Cup` or `ENG + EFL Cup` → EFL Cup;
- `NED + Eredivisie` → Eredivisie;
- `ENG + Championship` → EFL Championship;
- `USA + Major League Soccer` → MLS;
- `KSA + Saudi Pro League` → Saudi Pro League;
- `SCO + Premiership` → Scottish Premiership.

Examples such as `BLR + Premier League`, `ECU + Serie A` and `AUT + Bundesliga` remain unprioritized. There is no substring, fuzzy, prestige or country-free source fallback.

## Domestic cup stage modifiers

Cup stage evidence changes **attention order only** and is applied only when the stage/context evidence has already been reviewed.

- UEFA or domestic cup final / semi-final: move up one band.
- Quarter-final: no automatic upgrade; move up one band only when both sides are expected to field strong teams.
- Early cup round with expected top-flight rotation: move down one band.
- Two-leg second leg: retain the competition band but mark a confidence focus on aggregate score, qualification incentives and game state.
- Non-Big-Five domestic cup: default one band below its parent league; quarter-final/semi-final/final may restore the parent league band.

These modifiers never create model, selection, pricing or BET authority.

## International country football hierarchy

Country football uses a separate hierarchy:

| Tier | Band | Competition family |
|---:|---|---|
| 1 | INT-S | FIFA World Cup |
| 2 | INT-A | UEFA European Championship → Copa America → AFCON → AFC Asian Cup → CONCACAF Gold Cup |
| 3 | INT-B | FIFA World Cup qualifiers |
| 4 | INT-C | continental championship qualifiers |
| 5 | INT-D | Nations League competitions |
| 6 | INT-E | official one-off / secondary senior tournaments |
| 7 | INT-F | international friendlies |
| 8 | INT-G | youth / Olympic / age-grade internationals |

International aliases are exact normalized aliases inside the explicit `INTERNATIONAL` scope. A club and an international candidate in the same priority-plan call cause the planner to fail rather than invent a cross-table comparison.

## Fixture ordering inside one hierarchy position

Competition hierarchy is evaluated before fixture strength. Inside the same effective competition position, fixture ordering remains transparent and lexicographic:

1. higher estimated probability for the exact priced selection;
2. lower reviewed risk;
3. fresher reviewed evidence;
4. higher validated bookmaker edge;
5. earlier kickoff;
6. stable fixture identity/input order.

The same-rank Big Five domestic cups therefore do not get an arbitrary prestige ordering; exact fixture quality breaks their ties.

## Model reliability remains separate

`domain.model_league_reliability` remains versioned independently as `athena-model-league-reliability-v1`.

The hierarchy is a scan/review order, not evidence that one probability model is better in one competition than another. An evidence-ranked model-specific override still requires replayable held-out competition metrics. Caller-provided model ranks cannot create that authority.

## Strict exhaustion

For target size `N`:

1. start only with candidates already eligible at the caller boundary;
2. identify club versus international scope;
3. resolve exact source-qualified competition identity when present;
4. apply only reviewed stage modifiers;
5. exhaust higher hierarchy bands/ranks before lower ones;
6. order fixtures transparently inside one position;
7. continue through reserves when an individual candidate is rejected;
8. stop when `N` accepted legs exist or the permitted universe is exhausted;
9. return a shortfall rather than manufacturing unsupported legs.

## Historical warehouse relationship

The historical warehouse built in PR203 is a separate high-volume SQLite evidence store. It contains the club and international competitions needed to support this hierarchy, while PR205 preserves cross-source neutral-international orientation correctly and PR215 audits season-level completeness. The historical registry supplies evidence coverage; this accumulator hierarchy supplies review order. Neither grants BET authority by itself.

## Safety

A famous competition, large team-name gap, high hierarchy band or cup stage cannot rescue missing data, stale evidence, an unsupported model, an unpriced market, poor value, correlation conflicts or `NO_BET`.
