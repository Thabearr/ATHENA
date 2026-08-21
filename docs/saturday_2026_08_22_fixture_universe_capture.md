# Saturday 2026-08-22 fixture-universe capture

## Purpose

This boundary starts the live evidence phase for ATHENA's Saturday 2026-08-22 20-fold target. It captures one exact transparent FotMob `/api/data/matches` response for `20260822`, replays the existing PR38→PR40 source path, and produces a deterministic neutral inventory of every source fixture returned for that UTC date.

It does **not** select a bet. The output is the candidate universe that later reviewed fixture-intelligence, model, SportyBet reconciliation, fresh-price, value, selection, correlation and accumulator gates must consume.

## Frozen request

The request is fixed to:

- request date: `20260822`;
- timezone: `UTC`;
- ccode3: `NGA`;
- target fold size: `20`.

The runner reuses the existing transparent FotMob capture implementation and therefore performs exactly one bounded GET to the reviewed `/api/data/matches` route. It does not use the legacy advanced scraper, cookies, a session, browser impersonation, X-Mas headers, proxies or bypass logic.

## Exact source chain

The source chain is:

```text
transparent PR38 dataMatches capture
→ PR39 structural assessment
→ PR40 UNREVIEWED fixture-candidate bundle
→ exact Saturday UTC-date check
→ exact FotMob country-code + whole competition-name identity match
→ source-qualified competition review priority
→ canonical Saturday fixture-universe artifact
```

The source candidate bundle stays `UNREVIEWED`. This boundary does not mass-approve the fixtures or convert the capture into a reviewed fixture catalog.

## Source-identity disambiguation

The first real hosted capture exposed an important ambiguity that a name-only resolver cannot safely handle. FotMob returned unrelated competitions with generic names shared by target leagues, including `Premier League` in Belarus, `Serie A` in Ecuador, `Bundesliga` in Austria, and `Premiership` in both Scotland and Northern Ireland.

Accordingly, a source fixture receives review priority only when its exact FotMob country code and normalized whole competition name match an explicitly reviewed source pair. A same-name competition from another country remains unprioritized. No fuzzy, substring or country-free fallback exists.

The shared review policy is versioned as:

`athena-competition-review-priority-v1`

The policy recognizes the primary domestic cups of the top-five countries as one shared major-cup review band:

- `ENG + FA Cup` -> FA Cup;
- `ESP + Copa del Rey` -> Copa del Rey;
- `ITA + Coppa Italia` -> Coppa Italia;
- `GER + DFB Pokal` -> DFB-Pokal;
- `FRA + Coupe de France` -> Coupe de France.

All five use review rank `9` / tier `3`. Primeira Liga, Süper Lig and Eredivisie are reviewed before that cup band; Belgian Pro League, Scottish Premiership and Greek Super League are reviewed after it. Unreviewed secondary cups and Super Cups do not inherit the tier merely because they are cups.

## Exact Saturday evidence

The exact PR #199 current-head capture is:

- source PR head: `b879b2140d0bc3fb64fa8fec4c73c735240a3b41`;
- workflow run: `32455713912`;
- artifact: `9437181220`;
- artifact digest: `sha256:360aac588f049fe6b0437c43e060b317edd12aaf4672db93ebe2fca42de00589`.

The raw Saturday source universe contains **670 fixtures**.

Under the first league-centric source identity policy, **39** fixtures matched the domestic league priority list and **631** remained unprioritized. The raw source simultaneously contained **11 `GER|DFB Pokal` fixtures**.

Replaying those exact same PR38→PR40 bytes through `athena-competition-review-priority-v1` produces **50 serious first-pass competition-review fixtures**:

| Review rank | Competition | Fixtures |
|---:|---|---:|
| 1 | Premier League | 5 |
| 2 | La Liga | 3 |
| 3 | Serie A | 4 |
| 4 | Bundesliga | 0 |
| 5 | Ligue 1 | 5 |
| 6 | Primeira Liga | 3 |
| 7 | Süper Lig | 3 |
| 8 | Eredivisie | 4 |
| 9 | **DFB-Pokal** | **11** |
| 10 | Belgian Pro League | 3 |
| 11 | Scottish Premiership | 6 |
| 12 | Greek Super League | 3 |

There are no FA Cup, Copa del Rey, Coppa Italia or Coupe de France fixtures in this exact Saturday capture, so those entries change the reusable policy but do not change this snapshot's count. The current snapshot therefore remains `50` prioritized fixtures and `620` still-unprioritized fixtures.

That count is a review-pool fact only; it is not a prediction, selection or BET claim.

## Why the major-cup band exists

The old policy was league-centric and would leave primary domestic cup ties at rank 999. The corrected policy says ATHENA should not bury major national cup fixtures below Belgium/Scotland/Greece simply because they are not league fixtures.

It also does **not** mean every cup tie is equally attractive. Each tie still has to survive its own team-level, rotation, lineup, motivation, model, market, freshness, price and correlation gates. The five major cups share one review rank so exact fixture quality, not an arbitrary FA-vs-Copa-vs-DFB prestige ordering, decides which tie is inspected first inside that band.

## Priority inventory

The v2 Saturday report records, per source fixture:

- `FOTMOB:<source_match_id>` identity candidate;
- source competition IDs/name/country code;
- source home/away team IDs and names;
- exact UTC kickoff;
- PR40 review status;
- canonical competition review name/rank/tier/kind only after exact source identity resolves;
- the explicit source-identity match/basis state.

Summary counts remain separated so same-name foreign competitions cannot be merged into a prioritized total:

- `source_competition_counts` keys every observed source competition as `CCODE|literal-name`;
- `prioritized_competition_counts` contains only exact reviewed source-identity matches;
- `unprioritized_source_competition_counts` keeps rejected source identities visible as `CCODE|literal-name`.

## Authority

Every downstream authority flag remains false:

- candidate review;
- fixture catalog admission;
- fixture intelligence;
- model features and probability;
- SportyBet reconciliation and canonical market mapping;
- fresh bookmaker price and pricing;
- selection;
- accumulator authorization;
- BET.

The next work after this priority boundary is to review/promote the fixtures required by the competition-exhaustion path, then obtain fresh fixture intelligence and exact SportyBet evidence close enough to kickoff to satisfy their own freshness rules.
