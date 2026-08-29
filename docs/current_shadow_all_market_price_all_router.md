# Current Shadow Price-all + all-market Router (PR D)

**Master issue:** #261 Track E  
**Boundary:** research / Shadow only  
**Production / selection / Portfolio / execution authority:** false

## Current source lane

PR D does not accept a caller-authored PR-C scan, xG pair, provider-status map,
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

PR D does **not** modify `CurrentAllMarketShadowFixtureScan`; PR-C canonical
serialization/hash semantics therefore remain the merged PR-C contract.

## Exact provider identity

Canonical market/outcome/line come only from typed PR-B observations. Odds and
native IDs/names/specifier come only from the exact replayed SportyBet inventory.
The join is exact on event ID, market ID, specifier and outcome ID, and also checks
market/outcome names plus raw/manifest/inventory SHAs. There is no fuzzy matching,
case-fold fallback, nearest line or cross-snapshot join.

For Asian Handicap, PR-B's provider `hcp=` is the HOME line. PR D preserves that
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
partitions remain explicit price audit rows but are Router-ineligible.

Double Chance and 1UP/2UP are overlapping event sets and are never normalized as
an ordinary partition. DNB uses WIN/PUSH/LOSS unit-stake settlement EV. Asian
Handicap uses WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS unit-stake settlement EV. DNB/AH
do not mint fake ordinary fair probabilities or fake scalar event probabilities.

Priced rows preserve PR-C scan/assessment ancestry, sealed xG/history identity when
present, PR-B registry/observation identity, exact provider raw/manifest/inventory,
current fixture reconciliation, current mapping rebind, bridge bundle, score-matrix
audit and specialist evidence where applicable.

## Router

Router input is only the builder-issued `ShadowPriceAllBundle`; it is replayed from
its retained source context before selection, so a caller cannot route a hand-picked
subset of rows.

Frozen conservative thresholds remain:

- scalar-event model probability ≥ **0.55**;
- net EV > **0**;
- robust net EV > **0**;
- robust edge > **0** where ordinary fair probability is identifiable;
- ordinary partitions require complete same-snapshot de-vig.

Ranking is deterministic: robust EV, then identified robust edge, then scalar-event
probability floor, then stable opportunity ID. The result retains selected (if any),
runner-up eligible and strongest rejected/counterfactual. `NO_BET` is a successful
terminal research result.

## Explicitly outside PR D

No Portfolio/target-20/caps, final current runner, share-code create/reload, login,
cookies, wallet, stake or wager. All production/execution flags remain false and
`wager_placed=false`. PR E is the later Portfolio/current-runner mission; PR F is
the later live all-market field-proof/hardening mission.