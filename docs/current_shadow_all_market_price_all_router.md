# Current Shadow Price-all + Prediction-first all-market Router (PR 3 of #280)

**Master issue:** #280 Shadow hardening
**Boundary:** research / Shadow only
**Production / selection / Portfolio / execution authority:** false

## Current source lane

PR 3 does not accept a caller-authored PR-C scan, xG pair, provider-status map,
quote list, source-lane string, or issuance token.

The current chain is:

1. exact complete PR151 durable fresh-history handoff;
2. PR253 builder-only current direct-provider mapped-quote bundle, replay-verified
   and used as the exact FotMob ↔ SportyBet fixture/event/currentness bridge;
3. PR-B `ProviderEventEvidence`, replayed from its retained raw + manifest and
   required to identify the exact same event/raw/manifest/inventory/kickoff;
4. a fresh PR-B 15-market semantic registry rebuilt from that one event at the
   bridge evaluation time;
5. PR-C `scan_current_fixture_all_markets(...)`, called internally from the real
   history handoff and typed PR-B registry;
6. exact quote issuance from every current/bookable/analytically-eligible PR-B
   observation in that replayed inventory;
7. Price-all over the complete PR-C audit surface;
8. Router over the complete builder-issued Price-all bundle after source replay.

PR 3 does **not** modify `CurrentAllMarketShadowFixtureScan`; PR-C canonical
serialization/hash semantics therefore remain the merged PR-C contract.

## Exact provider identity

Canonical market/outcome/line come only from typed PR-B observations. Odds and
native IDs/names/specifier come only from the exact replayed SportyBet inventory.
The join is exact on event ID, market ID, specifier and outcome ID, and also checks
market/outcome names plus raw/manifest/inventory SHAs. There is no fuzzy matching,
case-fold fallback, nearest line or cross-snapshot join.

For Asian Handicap, PR-B's provider `hcp=` is the HOME line. PR 3 preserves that
provider line and uses PR-C orientation: HOME keeps it; AWAY uses its exact
opposite. Current AH remains unavailable whenever PR-B remains unproven.

## Freshness

Price-all rechecks the reviewed provider policy at the source snapshot evaluation:
observation age must be non-negative and ≤ **900 seconds**, and kickoff lead must
be strictly greater than **120 seconds**. PR-B must also mark the observation
`CURRENT`, bookable and analytically eligible.

## Price-all

All 15 canonical MarketIds survive into the audit. Every analytically-ready
outcome/exact line is priced or explicitly unpriced before routing; negative and
zero EV rows are retained.

Proportional de-vig is permitted only for a complete mutually-exclusive,
exhaustive, same-snapshot ordinary partition. Incomplete/cross-snapshot ordinary
partitions remain explicit price audit rows; they are rejected by the retained
value-first counterfactual, while Prediction-first uses the exact model event
probability and current odds.

Double Chance and 1UP/2UP are overlapping event sets and are never normalized as
an ordinary partition. DNB uses WIN/PUSH/LOSS unit-stake settlement EV. Asian
Handicap uses WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS unit-stake settlement EV. DNB/AH
do not mint fake ordinary fair probabilities or fake scalar event probabilities.

Priced rows preserve PR-C scan/assessment ancestry, sealed xG/history identity when
present, PR-B registry/observation identity, exact provider raw/manifest/inventory,
current fixture reconciliation, current mapping rebind, bridge bundle, score-matrix
audit and specialist evidence where applicable.

## Prediction-first Router V2

Router input is only the builder-issued `ShadowPriceAllBundle`; it is replayed from
its retained source context before selection, so a caller cannot route a hand-picked
subset of rows.

The former value-first Router remains available as an explicit diagnostic
counterfactual, but it has no selection authority. Prediction-first V2 records
both policies and preserves model, quote, value, eligibility, rejection and rank
fields for audit/replay.

Prediction confidence is comparable across the reviewed market semantics:

- scalar event markets: the exact model event probability;
- DNB: `P(WIN) + P(PUSH)`;
- Asian Handicap: `P(WIN) + P(HALF_WIN) + P(PUSH)`.

Incomplete or malformed settlement evidence is not comparable. The common
prediction-confidence floor is **0.55** (inclusive), and the exact current
decimal-odds floor is **1.09** (inclusive). Positive EV, robust EV, robust edge,
fair probability, overround and bookmaker-implied probability remain diagnostics;
they are not Prediction-first eligibility or ranking authority.

Ranking is deterministic: prediction confidence descending, then stable canonical
opportunity ID. The result retains the Prediction-first selection/rank and the
former value-first selected/runner-up/counterfactual outcome. `NO_BET` is a
successful terminal research result.

## Explicitly outside PR 3

No Portfolio/target-20/caps, final current runner, share-code create/reload, login,
cookies, wallet, stake or wager. All production/execution flags remain false and
`wager_placed=false`. Portfolio selection semantics remain the separate PR 4
boundary; this Router output remains source-replayable for existing downstream
consumers.
