# Market Router v1

Live expansion PR #236 introduces ATHENA's first reviewed fixture-level market
routing boundary. The Router consumes exact Phase 6 calibrated candidates,
source-qualified SportyBet quotes, and one canonical Fixture State v2 snapshot.
Its authoritative entry point invokes Phase 7 `price_all_candidates()` across the
complete candidate set before any candidate can be compared or selected.

## Frozen contract

Market Router contract version 1 is pinned at:

`0e4486527b060109852ab56dd76774b2d150cf8326875e44537a3bce2dc656bf`

The contract binds:

- Phase 7 Price-all contract
  `1fb0a6c891adccd76b4864a6197e55d22154176a4191f57ce92cde13501535aa`;
- Fixture State v2 field-registry version 1 and SHA
  `330e81a3fd8dc88c8fee98544d7f63e9d429c43c5d32ca761da5227e34de588a`;
- canonical market semantics inherited through Phase 7;
- price-before-route ordering;
- strict context qualification;
- deterministic worst-model robust value;
- deterministic ordinary robust edge;
- NO BET and counterfactual policy;
- fixed thresholds and authority flags.

Same-version semantic drift fails closed.

## Price before route

The public Router accepts exact builder-issued `CalibratedValueCandidate`
objects and exact `SportyBetExactQuote` objects. It does not accept arbitrary EV,
edge, confidence, risk, ranking, or baseline-delta scalars. Every candidate is
first sent through Phase 7. The complete Phase 7 result set is retained in the
Router decision audit.

The legacy `global_baseline_delta`, archetype boost, and `ranking_score` path in
`MatchAnalyst` is not an authoritative Router input and is not treated as
bookmaker value.

## Fixture identity and context

One Router operation belongs to one exact ATHENA fixture and one SportyBet event.
Mixed candidate fixture/event identities fail closed to NO BET. Fixture State v2
must match the candidate fixture, must be observed no later than the Router
evaluation time, and routing must occur strictly before kickoff.

Router v1 derives its context denominator from Fixture State fields whose
reviewed source plan is already `CURRENTLY_MAPPABLE`. Today those six fields are
home form, away form, home Elo, away Elo, fatigue, and live-data freshness.

All six must be `AVAILABLE`. A missing reviewed field reduces completeness and a
blocked/stale/unverified/conflicted reviewed field fails the gate. Explicit
future-source/future-adapter Fixture State slots are reported but excluded from
the reviewed denominator; they never masquerade as available evidence.

The frozen minimum reviewed-context completeness is `1.0`.

There is no learned numerical context-risk buffer in v1:

`STRICT_EVIDENCE_GATE_NO_LEARNED_NUMERIC_BUFFER_V1`

`context_risk_buffer = None`

## No fabricated uncertainty

The planned learned uncertainty meta-model is not implemented in this PR.
Router v1 reports:

`DETERMINISTIC_ROUTER_V1_NO_LEARNED_UNCERTAINTY_META_MODEL`

No heuristic is described as a confidence interval, posterior, standard error,
or calibrated uncertainty estimate.

## Model variants and robust value

Multiple calibrated model variants for the same exact canonical opportunity are
grouped by fixture, SportyBet event, market, outcome, line, and exact quote
identity. Their calibration-unit/component semantics must agree.

For one exact opportunity:

`robust_net_expected_value = minimum(model-specific Phase 7 net EV)`

The best EV and EV spread are retained. A single model is explicitly labelled
`SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE`, never "perfect agreement".

For ordinary event opportunities with a legitimate Phase 7 fair probability:

`robust_edge = minimum(calibrated event probability) - fair_probability`

The component meaning is read from reviewed Phase 6 semantics, never guessed by
array position.

DNB and Asian Handicap retain their full settlement distributions and use the
settlement-aware Phase 7 EV. They never receive a fabricated scalar robust edge.
Double Chance likewise receives no fabricated ordinary fair probability because
its offered events overlap; genuine positive settlement/event EV may still be
routable.

Ordinary markets that should have a complete mutually-exclusive/exhaustive
Phase 7 price partition must actually have that complete partition before Router
selection. Missing ordinary de-vig evidence fails closed rather than silently
turning raw inverse odds into a trusted fair comparison.

## Frozen safety thresholds

Router v1 freezes:

- minimum ordinary/scalar event probability: `0.55`;
- minimum model-specific net EV: strictly greater than `0.0`;
- minimum robust net EV: strictly greater than `0.0`;
- minimum ordinary robust edge: strictly greater than `0.0`.

The `0.55` probability threshold is an operational safety carry-forward, not a
claim of empirical optimization. DNB/AH do not receive a fake scalar-probability
gate.

## Routing and NO BET

Eligible opportunities are ordered by robust net EV descending, robust edge
descending where it legitimately exists, conservative event-probability floor
descending where applicable, quote age ascending, then deterministic canonical
opportunity ID.

No market family receives a preferred-market bonus, league stereotype,
short-odds bonus, or archetype boost.

The Router selects at most one opportunity. `NO_BET` is a normal successful
result when identity/context validation fails or no opportunity clears the
frozen positive-value policy. A selected decision retains a runner-up when one
exists. NO BET retains the strongest rejected counterfactual. Every Phase 7
candidate/result remains in the audit record.

## Authority

Router v1 grants only `market_routing`, `fixture_market_selection`, and
`counterfactual_recording`.

It keeps football probability generation, calibration, bookmaker pricing,
accumulator authority, slip construction, booking-code generation, bookmaker
execution, production approval, and BET authority false.

`MODEL_STATUS_REGISTRY` is intentionally unchanged: legacy per-market selection
authority remains `NOT_AUTHORIZED`, so the existing `AccumulatorEngine` cannot
bypass the new Router. The reviewed Router-to-Accumulator boundary belongs to
live PR #237.

## Real-current status

No verified current full routing corpus is committed for this implementation:

`REAL_CURRENT_MARKET_ROUTER_STATUS = NOT_RUN_VERIFIED_CURRENT_ROUTING_CORPUS_UNAVAILABLE`

Synthetic tests prove protocol semantics only and make no claim about current
SportyBet odds, real routing coverage, or betting performance.
