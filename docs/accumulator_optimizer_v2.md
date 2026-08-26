# Accumulator Optimizer v2

Live expansion PR #237 implements ATHENA Phase 9: portfolio construction across
already-reviewed fixture decisions.  It is deliberately downstream of the
Market Router and does not create a football probability, bookmaker price, or
fixture-level market selection.

## Frozen contract

Accumulator Optimizer contract version 1 is pinned at:

`de6578c1a21370a1859901a73e4d3993d1544a66cb0f09384a45a8233a5ce253`

It binds the exact Market Router v1 contract:

`0e4486527b060109852ab56dd76774b2d150cf8326875e44537a3bce2dc656bf`

and both the reviewed SportyBet/FotMob full-UTC reconciliation contract and its
source-replayed receipt contract used to source team, competition, and kickoff
exposure identity.

## Router replay is mandatory

The authoritative Phase 9 entry point does not trust an arbitrary serialized
`MarketRouterDecision`.  For every fixture it accepts only an exact
`AccumulatorFixtureInput` that was builder-issued from exact Phase 6 calibrated
candidates, exact source-issued SportyBet quotes, exact Fixture State v2, and a
verified full-UTC reconciliation receipt/source bundle.  It then replays
`route_market_candidates()` before portfolio admission.

A Router `NO_BET` remains `NO_BET`.  The accumulator cannot replace it with a
runner-up, reserve, legacy verdict, or other market simply to fill the requested
fold size.

## Source-replayed exposure identity

Portfolio correlation and concentration controls need real team and competition
identity.  These are not caller-provided strings, and a caller-constructed
`SportyBetFotMobFullUtcReconciliation` dataclass is not sufficient authority.

`AccumulatorFixtureInput` is builder-only.  Its public issuance path calls the
existing `verify_reconciliation_receipt_directory()` boundary, which rebuilds
the full-UTC reconciliation from the complete preserved SportyBet, Terms,
Sportradar, and FotMob source bundle and requires exact equality with the stored
receipt bytes.

The rebuilt canonical reconciliation SHA-256 must then equal the reconciliation
SHA already bound into every supplied source-issued SportyBet quote.  Fixture
State fixture identity and kickoff, Phase 6 candidate fixture/event identity,
and quote fixture/event identity must all match that same source-replayed
reconciliation before the immutable input is issued.

Only after those checks are the matched FotMob home team, away team,
competition, and kickoff admitted as portfolio exposure metadata.  Relabelling a
team or competition changes the reconciliation bytes and therefore cannot evade
an exposure cap.

## Joint portfolio selection

The requested fold count is a target, not a quota.  The optimizer iteratively
selects the best admissible marginal leg while enforcing hard exposure caps.
It may stop early and report a shortfall.

Version 1 freezes these operational controls:

- no team may appear in more than one selected leg;
- competition concentration is capped at 40% of target size, with a two-leg
  minimum cap for targets of at least two;
- market-family concentration is capped at 50% of target size, with the same
  two-leg minimum;
- fragile legs are capped at 30% of target size, with a one-leg minimum cap.

These percentages are conservative operational v1 policy, **not empirically
optimized correlation coefficients**.  Changing them requires a reviewed
contract version.

Within the admissible pool, deterministic marginal ordering favors lower
current concentration first, then higher conservative survival floor, higher
robust Router EV, legitimate robust edge where available, fresher quote, and
finally canonical leg identity.  There is no team, league, market-family, or
short-odds bonus.

## Fragility

A leg is operationally flagged as fragile when either:

- robust Router net EV is below `0.02`; or
- conservative survival probability is below `0.60`.

These are policy thresholds used for diversification, not claims that the
numbers are statistically optimal.

## Survival reporting

For ordinary markets the leg survival floor is the Router's worst-model
calibrated event-probability floor.

For full-settlement markets it is derived without flattening settlement states:

- Draw No Bet: `P(WIN) + P(PUSH)`;
- Asian Handicap: `P(WIN) + P(HALF_WIN) + P(PUSH)`.

Half-loss and loss states do not count as survival.

The reported `expected_slip_survival` is the product of the conservative leg
survival floors under an **independence baseline only**.  It is explicitly not
a correlation-adjusted joint probability.  ATHENA currently has no validated
joint dependence model, so:

`correlation_adjusted_expected_slip_survival = None`

`joint_dependence_status = NO_VALIDATED_JOINT_CORRELATION_MODEL_V1`

This avoids fabricating Pearson correlations, copulas, posterior dependence, or
other statistics that have not been learned and validated from historical
multi-leg evidence.

## Correlation and concentration audit

The selected portfolio reports exact exposure counts and flags pairs sharing a
competition or market family.  Same-team duplication is blocked by the hard
team cap.  Pair records retain `statistical_correlation=None` because exposure
overlap is a deterministic risk signal, not an estimated correlation
coefficient.

## Reserves and shortfall

Every Router-qualified leg not selected is retained as a reserve with explicit
reasons such as team exposure, competition concentration, market-family
concentration, fragility cap, target already filled, or lower marginal
portfolio priority.

A 20-leg request that yields only 14 admissible legs returns 14 selected legs,
six-leg shortfall, and the reserve/audit record.  It never pads with a Router
NO_BET or a blocked opportunity.

## Authority

Phase 9 grants only:

- accumulator optimization;
- qualified leg-set construction;
- reserve-leg recording.

It keeps false:

- market routing;
- bookmaker pricing;
- slip construction;
- booking-code generation;
- staking;
- bookmaker execution;
- production approval;
- BET authority.

The existing legacy `AccumulatorEngine` remains untouched.  Its historical
free-form dict path does not become the authoritative Phase 9 boundary and the
`MODEL_STATUS_REGISTRY` selection-authority safety brake is not globally
changed.

## Real-current status

No verified current multi-fixture Router corpus is committed for this
implementation:

`NOT_RUN_VERIFIED_CURRENT_ROUTER_CORPUS_UNAVAILABLE`

Synthetic tests prove protocol semantics only; they are not real accumulator
performance evidence.
