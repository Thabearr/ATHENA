# Market Router v2 direct-provider value consumption

## Status

This boundary is the explicit consumer required by merged PR #248:

`MARKET_ROUTER_V2_DIRECT_PROVIDER_VALUE_CONSUMPTION_REQUIRED`

It adds a separate Router v2 lane for verified current direct-provider Price-all
values. The frozen Phase 8 Market Router v1 remains unchanged and continues to
bind the legacy Phase 7 `SportyBetExactQuote` / `PriceAllValueResult` path.

## Accepted upstream object

Router v2 accepts only an exact
`PriceAllV2DirectProviderEvaluation` from
`domain/price_all_v2_direct_provider.py`.

Before routing, it reconstructs that evaluation through PR #248. That in turn
reconstructs the PR #247 quote-source adapter and the retained PR #246 live
SportyBet mapped quote bundle. Router v2 therefore does not accept caller-built
value rows, detached prices, mapping odds, or a legacy Phase 7 result relabelled
as direct-provider evidence.

The frozen Price-all v2 contract identity is:

`b5e3c063ac8b4e9fc1521cabbfe1da873a67b70efc67bc08d8ada61f2024e599`

The preserved Market Router v1 policy identity is:

`0e4486527b060109852ab56dd76774b2d150cf8326875e44537a3bce2dc656bf`

Router v2 uses a new contract rather than silently changing either predecessor.

## Router-time freshness

A quote being current when PR #248 priced it is not enough to make it current
forever.

Router v2 recomputes, at its own evaluation time:

- direct-provider source age from the original ATHENA response-completion
  observation time;
- remaining kickoff lead from the reconciled kickoff UTC.

It preserves the exact effective Price-all v2 policy carried by the upstream
evaluation. If Price-all tightened the maximum quote age below 900 seconds,
Router v2 honors that tighter value. Router v2 never increases the maximum age
or reduces the minimum kickoff lead.

If the source is stale at Router time or the remaining lead is at/below the
effective minimum, the decision is first-class `NO_BET`. A previously `PRICED`
value record is not allowed to bypass this later freshness gate.

The observation authority remains the direct-provider response-completion time;
it is not relabelled as a provider quote timestamp. Provider quote timestamp and
provider snapshot identity remain unavailable unless a future reviewed provider
contract supplies them.

## Fixture and source identity

The Router requires:

- exact `FixtureStateV2Snapshot` input;
- Fixture State fixture identity equal to the Price-all v2 fixture;
- Fixture State kickoff equal to the reconciled direct-provider kickoff;
- Fixture State `as_of` not later than Router evaluation time;
- Router evaluation strictly before kickoff;
- every Price-all v2 result, when present, to remain inside the evaluation's
  exact ATHENA fixture and SportyBet event identity.

Identity failures do not get repaired by guessing or substitution. They produce
`NO_BET` and remain visible in the decision reasons.

## Context qualification

Router v2 preserves the currently reviewed strict Fixture State context gate
from Router v1. The gate only uses the currently mappable reviewed context
fields. Missing or blocked required context produces `NO_BET`.

No learned numeric uncertainty buffer is introduced here. The uncertainty
status is explicitly:

`DETERMINISTIC_ROUTER_V2_NO_LEARNED_UNCERTAINTY_META_MODEL`

This keeps learned Router/uncertainty promotion behind later prospective value
evidence rather than pretending that evidence already exists.

## Opportunity grouping and model disagreement

Results are grouped only when they refer to the same exact:

- ATHENA fixture;
- SportyBet event;
- canonical market;
- canonical outcome;
- canonical line;
- direct-provider quote identity.

Contributing model variants must also share compatible calibration component
semantics, one fair-probability identity, and one Price-all v2 source ancestry.

For compatible multi-model opportunities the Router uses the conservative lower
envelope of net expected value. Single-model opportunities are explicitly
labelled as having no model-disagreement evidence rather than claiming perfect
agreement.

## Value gates

Router v2 preserves the reviewed deterministic Router policy:

- every contributing model variant must be `PRICED` by Price-all v2;
- each contributing model variant must have strictly positive net EV;
- robust/worst-model net EV must be strictly positive;
- ordinary event-probability opportunities must meet the reviewed 0.55 floor;
- when ordinary fair probability is available, robust edge must be strictly
  positive;
- ordinary markets requiring de-vig must have a complete current
  direct-provider partition;
- push/split settlement markets such as Draw No Bet and Asian Handicap route on
  settlement-aware EV without inventing an ordinary fair-probability edge;
- specialist markets without reviewed upstream probability authority remain
  blocked.

Bookmaker odds are consumed only as already-reviewed Price-all value evidence.
They do not enter the football probability model.

## Selection and NO BET

Router v2 chooses at most one canonical opportunity for one fixture. Eligible
opportunities are ordered deterministically by:

1. robust net EV descending;
2. robust edge descending where available;
3. calibrated event-probability floor descending where available;
4. Router-time quote age ascending;
5. canonical opportunity ID ascending.

If no opportunity clears all gates, `NO_BET` is a successful valid result.
The Router also preserves the runner-up and strongest rejected counterfactual
where available.

It never forces a requested leg count.

## Provenance retained in the decision

The Router decision preserves:

- exact Price-all v2 evaluation SHA-256 and full evaluation payload;
- source quote-source SHA-256;
- source bundle SHA-256;
- direct quote identity and provider market/outcome/specifier where priced;
- source raw-response SHA-256;
- reviewed mapping SHA-256;
- fixture reconciliation SHA-256;
- source observation time;
- Price-all quote age and Router-time quote age;
- effective maximum quote age and minimum kickoff lead;
- Fixture State SHA-256;
- Price-all v2, legacy Router v1, and Router v2 contract identities;
- deterministic opportunity, model-variant, rejection, runner-up and
  counterfactual records.

`verify_market_router_v2_direct_provider_decision(...)` rebuilds the decision
from the retained exact Price-all evaluation, Fixture State, and Router
evaluation time. Public-field relabelling or upstream tampering fails closed.

## Authority boundary

This PR grants only:

- verified direct-provider value consumption;
- Router-time source freshness recheck;
- per-fixture market routing;
- per-fixture opportunity selection;
- counterfactual recording.

It does **not** grant:

- football probability generation;
- calibration;
- Price-all value computation;
- model promotion;
- final cross-fixture selection;
- portfolio optimization;
- accumulator construction;
- SportyBet execution;
- staking;
- BET authority.

`wager_placed=false` remains explicit.

## Next boundary

The exact next boundary declared by Router v2 is:

`PORTFOLIO_OPTIMIZER_V2_DIRECT_PROVIDER_ROUTER_CONSUMPTION_REQUIRED`

A later reviewed optimizer v2 must consume this Router v2 contract explicitly,
preserve `NO_BET` / shortfall as valid outcomes, and must not silently reinterpret
the frozen Phase 9 optimizer v1 input contract.
