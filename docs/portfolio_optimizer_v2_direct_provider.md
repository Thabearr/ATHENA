# Portfolio Optimizer v2 — direct-provider Router consumption

## Purpose

This boundary is the direct-provider portfolio consumer declared by Market Router
v2:

`PORTFOLIO_OPTIMIZER_V2_DIRECT_PROVIDER_ROUTER_CONSUMPTION_REQUIRED`

It consumes only exact verified
`MarketRouterV2DirectProviderDecision` values and produces a deterministic
cross-fixture qualified leg set or a valid requested-size shortfall.

The existing frozen `domain/accumulator_optimizer.py` / Phase 9 Accumulator
Optimizer v2 is **not** modified or reinterpreted. That older lane remains bound
to Market Router v1 and the legacy user-controlled HTML quote path.

## Contract identities

The new contract pins both reviewed policy ancestry and the new live-price lane:

- Market Router v2 direct-provider contract:
  `071d1246ee285634af5598b66872fb27c683f2d13ab14dc25b31de90b72195de`
- frozen legacy Accumulator Optimizer v2 contract:
  `de6578c1a21370a1859901a73e4d3993d1544a66cb0f09384a45a8233a5ce253`
- Portfolio Optimizer v2 direct-provider contract:
  `919149759ffc9aabef2fefe7c6e0db72d697ebd1ffe33205054fc3ffb4f785fd`

The legacy optimizer contract is retained as policy ancestry for the already
reviewed diversification caps, survival semantics, fragility thresholds,
reserve handling and target-shortfall rule. It does not authorize the legacy
Router v1 quote lane inside this new boundary.

## Builder-only Router inputs

`DirectProviderPortfolioRouterInput` cannot be constructed directly.

`from_source_replayed_receipt()` requires:

1. an exact `MarketRouterV2DirectProviderDecision`;
2. the existing exact full-UTC reconciliation source bundle;
3. the reconciliation receipt directory;
4. the repository root.

The builder first reconstructs the complete Router v2 decision using
`verify_market_router_v2_direct_provider_decision()`.

It then replays the full-UTC reconciliation receipt through the existing receipt
verifier and requires the resulting canonical reconciliation SHA to equal the
`source_reconciliation_receipt_sha256` retained by the exact reviewed mapping
inside the Router's direct-provider ancestry.

Fixture ID, SportyBet event ID and kickoff must agree across:

- the rebuilt Router v2 decision;
- its retained Price-all v2 evaluation;
- its retained reviewed SportyBet mapping;
- the source-replayed full-UTC reconciliation.

Home team, away team and competition exposure labels come from the verified
matched FotMob fixture in that source-replayed reconciliation. They are not
caller-provided portfolio metadata.

## Portfolio-time freshness

A Router decision being current at Router time does not make it current forever.

For every portfolio input, the optimizer recomputes:

- direct-provider source age from the original direct response-completion
  `source_observed_at`;
- remaining kickoff lead.

The effective maximum quote age and minimum kickoff lead are copied from the
Router decision, which already preserves the potentially stricter Price-all v2
policy.

Therefore the portfolio boundary can only preserve or tighten upstream
freshness. It cannot restore a leg that has become stale or too close to kickoff.

A Router `SELECTED` decision that fails this later check is retained in the
route audit but is not admitted as a portfolio leg.

## NO BET

Router `NO_BET` is final for this downstream boundary.

The optimizer never converts a Router `NO_BET` decision into a leg and never
searches the Router's rejected counterfactuals for a replacement.

This keeps market-routing authority inside Router v2.

## Exact direct-provider leg identity

A selected portfolio leg preserves:

- Router decision SHA;
- selected Router opportunity ID;
- ATHENA fixture ID;
- SportyBet event ID;
- canonical market, outcome and line;
- direct-provider quote SHA;
- provider market ID;
- provider outcome ID;
- provider specifier;
- direct-provider quote-source SHA;
- source bundle SHA;
- raw direct-provider response SHA;
- reviewed mapping SHA;
- fixture reconciliation SHA;
- decimal odds;
- Router-time quote age;
- portfolio-time quote age;
- portfolio-time kickoff lead;
- robust lower-envelope EV;
- robust fair-probability edge where the market supports one;
- calibrated event-probability floor where applicable;
- conservative survival floor;
- model count;
- fragility status.

The optimizer verifies that every Router model variant still points to the exact
retained Price-all v2 result and exact direct-provider quote.

## Settlement-aware survival

For ordinary win/loss markets, the portfolio survival floor is the Router's
calibrated event-probability floor.

For Draw No Bet:

`survival = P(WIN) + P(PUSH)`

For Asian Handicap:

`survival = P(WIN) + P(HALF_WIN) + P(PUSH)`

The worst contributing model value is retained.

No fake ordinary fair edge is introduced for push/split markets.

## Diversification policy

The existing reviewed deterministic portfolio policy remains in force:

- maximum requested target size: 50;
- maximum team appearances: 1;
- competition cap: 40% of target, with the reviewed minimum multi-leg cap;
- market-family cap: 50% of target, with the reviewed minimum multi-leg cap;
- fragile-leg cap: 30% of target, with minimum cap 1;
- non-fragile robust EV threshold: 0.02;
- non-fragile survival threshold: 0.60.

Among currently admissible legs, deterministic marginal selection prefers lower
current exposure, then higher conservative survival, higher robust EV, stronger
edge where defined, fresher direct-provider evidence, and finally stable leg
identity.

## Requested size is a target

The optimizer never pads a portfolio to satisfy the requested count.

If only 7 legs survive Router authority, portfolio-time freshness and exposure
caps for a target of 20, the output is a 7-leg qualified set with shortfall 13.

That is a successful disciplined result, not an error.

All Router-qualified but unselected currently admissible legs remain in the
reserve ledger with deterministic reasons such as:

- team exposure cap;
- competition concentration cap;
- market-family concentration cap;
- fragility cap;
- target already filled;
- lower marginal portfolio priority.

## Dependence and correlation

No validated statistical joint-dependence model exists yet.

The optimizer therefore:

- records observable exposure flags;
- applies hard diversification caps;
- reports an independence-baseline conservative survival product;
- leaves `correlation_adjusted_expected_slip_survival` as `null`;
- never fabricates a Pearson correlation, covariance or learned dependence
  coefficient.

The prospective SportyBet shadow campaign remains the required evidence path
before a learned dependence model can be promoted.

## Authority

This boundary authorizes:

- verified direct-provider Router consumption;
- exact Router reconstruction;
- portfolio-time freshness recheck;
- portfolio optimization;
- a qualified cross-fixture leg set;
- reserve recording;
- final cross-fixture selection at the portfolio boundary.

It does **not** authorize:

- football probability generation;
- calibration;
- Price-all value computation;
- market rerouting;
- model promotion;
- learned statistical dependence;
- SportyBet slip construction;
- booking-code generation;
- bookmaker execution;
- staking;
- betting.

Every serialized optimization includes `wager_placed: false`.

## Reconstruction

`verify_direct_provider_portfolio_optimization()` rebuilds the complete
optimization from its exact retained builder-issued Router/source inputs,
requested target size and evaluation time.

Public-field tampering changes the deterministic output and fails
reconstruction.

## Next boundary

The direct-provider chain still begins from known reviewed SportyBet event
identities.

The next declared boundary is therefore:

`SPORTYBET_CURRENT_EVENT_DISCOVERY_AND_FIXTURE_RECONCILIATION_REQUIRED`

That boundary must discover current provider-native events and reconcile them to
ATHENA/FotMob fixtures without weakening any of the reviewed quote, mapping,
Router or portfolio provenance guarantees established here.
