# SportyBet current event discovery + exact FotMob reconciliation

## Purpose

PR #251 implements the next boundary declared by the direct-provider Portfolio
Optimizer v2:

`SPORTYBET_CURRENT_EVENT_DISCOVERY_AND_FIXTURE_RECONCILIATION_REQUIRED`

The existing live quote boundary can read a known `sr:match:...` event ID, but
that does not make ATHENA autonomous: a current FotMob fixture still needs a
reviewed way to discover the corresponding current SportyBet event ID.

This boundary adds that missing source/provenance step. It discovers current
football events from a public anonymous SportyBet event-list endpoint, preserves
the exact response pages, exact-matches those provider identities against
reviewed FotMob fixture inputs, and confirms every authorized reconciliation by
replaying the already-reviewed PR #246 direct event-detail source.

It does **not** infer or reuse a canonical market mapping for a new event.

## Frozen identities

- Portfolio Optimizer v2 direct-provider contract:
  `919149759ffc9aabef2fefe7c6e0db72d697ebd1ffe33205054fc3ffb4f785fd`
- direct current event/quote evidence contract:
  `b888cebab6447cd4072d823dab67b56f1f75f72eb72d67b692d47a4378b27555`
- current event discovery/reconciliation contract:
  `ce69058ea61eecb9b5849567746bc0358ee29f2a4798b61190673d436d25b7ae`

The FotMob side remains anchored to the reviewed
`athena-fotmob-fixture-catalog-handoff-v1` contract.

## Discovery endpoint

The runtime request is a public anonymous GET to:

`/api/ng/factsCenter/liveOrPrematchEvents`

with the frozen football/pagination parameters:

- `sportId=sr:sport:1`
- `pageSize=100`
- `pageNum=<1..20>`

No login, cookie, account, wallet, stake, booking-code creation or wager action
is part of the discovery boundary.

The endpoint identity is frozen by this PR, but actual network acquisition is
still runtime evidence: the code grants no event identity merely because the
URL exists. A capture must return HTTP 200, strict UTF-8 JSON and SportyBet
`bizCode=10000` before any event candidate exists.

## Pagination and raw evidence

Discovery starts at page 1 and continues until a page contributes no new event
IDs. Every response is preserved under:

`.cache/athena-research/sportybet-current-event-discovery/<capture-id>/`

with one immutable raw JSON file per page plus a canonical manifest.

The manifest records for each page:

- exact request target;
- ATHENA response-completion observation time;
- raw file name;
- raw SHA-256;
- raw byte size;
- extracted event count.

The observation time is ATHENA's response-completion time. It is not relabeled
as a provider-native event timestamp, quote timestamp or snapshot identity.

If page 20 still adds new event IDs, discovery fails closed rather than silently
claiming a complete universe.

If the same event ID appears on multiple pages with changed home, away,
competition, kickoff or provider status identity, discovery fails closed.

## Provider event extraction

An event candidate requires exact provider fields for:

- `eventId` in canonical `sr:match:<positive integer>` form;
- `homeTeamName`;
- `awayTeamName`;
- numeric millisecond `estimateStartTime`;
- provider status/bookability fields where present.

Competition identity is accepted only when all observed provider competition
labels agree. The extractor can prove the label from a tournament envelope,
`event.tournamentName`, `event.leagueName`, `event.competitionName`, or the
nested `sport.category.tournament.name` structure.

If those fields disagree, competition identity remains unproven and the event
cannot authorize fixture reconciliation.

## Exact FotMob matching

The supplied FotMob catalog handoff is reconstructed before use. The provider
event is then compared with reviewed FotMob inputs using only:

`EXACT_CASE_SENSITIVE_HOME_AWAY_COMPETITION_FULL_UTC_NO_ALIAS_NO_FUZZY_NO_TOLERANCE`

That means:

- exact home team string;
- exact away team string;
- exact competition string;
- exact full UTC kickoff instant.

There is no case folding, alias table, fuzzy matching, home/away reversal,
kickoff rounding or tolerance window in this authority boundary.

Possible dispositions are explicit:

- `UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED`
- `DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE`
- `PROVIDER_COMPETITION_UNPROVEN`
- `NO_EXACT_REVIEWED_FOTMOB_MATCH`
- `AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH`
- `DIRECT_EVENT_DETAIL_CONFIRMATION_FAILED`

No-match and ambiguous-match states are valid fail-closed outputs.

## Direct event-detail confirmation

A unique exact discovery/FotMob match is still not enough for reconciliation
authority.

Before promotion, PR #251 calls the already-reviewed PR #246 event endpoint for
that exact event ID and rebuilds the live event inventory from its preserved raw
response. The detail confirmation must agree exactly with discovery on:

- event ID;
- home team;
- away team;
- full UTC kickoff;
- current prematch/bookable state.

The detail observation must also precede kickoff.

Only after this second exact provider read succeeds does
`fixture_reconciliation_authorized=True`.

The result preserves the PR #246 detail manifest SHA, inventory SHA and raw
response SHA alongside the discovery event SHA and matched FotMob fixture ID.

## Reconstruction

`SportyBetCurrentEventDiscoveryReconciliationBundle` is builder-only.

Verification is offline. It replays:

1. every exact preserved discovery response page;
2. the reviewed FotMob handoff from its candidate/review ancestry;
3. every retained PR #246 event-detail evidence directory;
4. the exact matching and authorization decisions.

Any public-field tamper or source-evidence drift changes the rebuilt result and
fails verification.

## Authority

This PR grants only:

- current provider event discovery;
- exact current provider event-detail confirmation;
- exact reviewed fixture reconciliation.

It grants no authority for:

- canonical market mapping;
- Price-all/value computation;
- market routing;
- portfolio optimization;
- final selection;
- accumulator/slip construction;
- SportyBet execution;
- staking;
- BET.

Every output keeps `wager_placed=false`.

## Why market mapping remains separate

Provider event IDs are event-specific. The existing reviewed canonical mapping
contract also binds exact provider market/outcome/specifier identities and exact
provider labels to a particular reviewed event/native inventory ancestry.

Discovering a new current event must therefore not silently reuse a historical
or different-event mapping object. That would collapse fixture identity and
market-settlement authority into one unreviewed assumption.

The next boundary is intentionally:

`CURRENT_DIRECT_PROVIDER_CANONICAL_MARKET_MAPPING_REBIND_REQUIRED`

That boundary can decide how reviewed provider market semantics may be safely
rebound to newly discovered current events before the already-merged direct
quote -> Price-all v2 -> Router v2 -> Portfolio Optimizer v2 chain is invoked.
