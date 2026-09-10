# Canonical Router / Coherence Migration Interface

## Mission

P1.4 promotes ATHENA's strongest reviewed routing semantics behind a stable canonical contract without creating another selector.

The permanent target name is `domain.market_router`, but that module is still the supported Phase-8/v1 Router and has existing callers. P1.4 therefore uses the temporary, explicit migration boundary:

```text
domain.market_router_canonical_adapter
```

A later dedicated caller-migration/rename PR may claim `domain.market_router`. P1.4 does not overwrite, delete or retire the existing v1 module.

## Input and output

The canonical replay entry point is:

```text
route(price_all_evaluation, fixture_state=..., evaluation_time=...) -> RouterDecision
```

`price_all_evaluation` must be an exact P1.3 `domain.price_all.PriceAllEvaluation`. The adapter verifies it, unwraps the exact delegated Price-all-v3 evaluation, and lets reviewed `domain.market_router_v3_current_provider` reconstruct source ancestry, Router-time freshness, Fixture State context and frozen value eligibility.

`route_current(...)` is a compatibility lane for exact `LIVE_CURRENT` Price-all ancestry; Router-v3 retains wall-clock ownership. `verify_router_decision(...)` reconstructs the original source Router decision and rejects canonical-field drift.

## One Router authority

P1.4 does not stack a separate coherence selector after Router-v3. Router-v3 supplies the exact source/value/context eligibility floor. The canonical adapter then applies the reviewed comparable-confidence and deterministic identity rules to the same opportunities and issues one final Router decision.

A source-v3 `REJECTED` opportunity can never become canonical `ELIGIBLE`.

The fixture-level selection limit is exactly one. P1.4 authorizes no same-game combination and no cross-fixture portfolio selection.

## Comparable prediction confidence

Comparable confidence is derived from model/calibration probability evidence, never from bookmaker odds:

- ordinary scalar event markets: selected model event probability;
- Draw No Bet: `P(WIN) + P(PUSH)`;
- Asian Handicap: `P(WIN) + P(HALF_WIN) + P(PUSH)`.

The reviewed minimum comparable confidence is `0.55`.

The reviewed minimum exact decimal odds is `1.09`. Odds are an eligibility floor only. They are not a ranking/tie key and cannot act as model confidence.

## Deterministic selection

Among canonically eligible opportunities, rank authority is:

1. settlement-aware robust net expected value, descending;
2. comparable prediction confidence, descending;
3. quote-independent canonical prediction identity `(market_id, outcome_id, normalized line)`.

Quote age, quote hash, provider identifiers, observed-at timestamps and source snapshot identities are not final tie authority.

Two eligible priced opportunities with the same canonical prediction identity fail closed instead of letting alternate quote identity decide the winner.

## Counterfactual evidence

Every decision records:

- selected opportunity or first-class `NO_BET`;
- runner-up when one exists;
- strongest counterfactual;
- source Router-v3 selected/runner-up/counterfactual identities;
- exact canonical Price-all and source Router-v3 contract/decision identities.

This preserves the evidence trail when canonical selection differs only because P1.4 applies the reviewed comparable-confidence/quote-independent policy.

## Coherence grouping

Coherence is diagnostic policy inside the Router contract. It does not create additional selection authority.

P1.4 groups only logical relationships derivable from canonical market settlement semantics:

- shared regulation-result atoms across compatible result, Double Chance, Result-or-Over and Win-to-Nil selections;
- shared `Over 2.5` atoms across Total Goals and positive Result-or-Over selections;
- shared `BTTS No` atoms across BTTS No and positive Win-to-Nil selections;
- nested Total Goals Over lines;
- nested Total Goals Under lines.

Each coherence group records all members, the group-local winner, group-local runner-up, whether the globally selected opportunity belongs to the group, and a reason/status for every member.

P1.4 does **not** infer correlation from market names. DNB, Asian Handicap, Win Either Half, and 1UP/2UP early-payout markets receive no invented joint-probability relationship. `joint_probability_supported` remains false and same-game combination authority remains false.

## Preserved Router-v3 gates

The canonical adapter delegates unchanged Router-v3 behavior for:

- exact Price-all-v3 source reconstruction;
- current-provider ancestry binding;
- source freshness and kickoff lead checks;
- Fixture State identity/context checks;
- frozen minimum event probability;
- strictly positive net EV / robust net EV;
- robust edge;
- complete fair-probability partition requirements;
- explicit source rejection and `NO_BET` behavior.

P1.4 does not change football formulas, calibration formulas, de-vig, settlement-return mathematics, provider mapping, or portfolio caps.

## Architecture Boundary CI

Because `domain.market_router_canonical_adapter` is a new member of the protected Router authority family, P1.4 registers accepted `ADR-002`. The frozen P0.4 baseline is not rewritten.

ADR-002 approves exactly the temporary adapter and no wildcard/new Router generation. Architecture Boundary CI must continue to reject an unapproved `domain.market_router_v4`, `market_router_next`, or equivalent parallel authority.

## Safety and authority

P1.4 performs no provider acquisition and no Current Shadow execution. It does not create/reload share codes, log in to SportyBet, access cookies or wallet state, calculate stakes, or place wagers. It grants no portfolio, accumulator, production-model, or wagering authority.

## Validation

Focused replay and policy tests:

```text
git pull --ff-only && PYTHONPATH=. python -m pytest tests/test_market_router_canonical_adapter.py tests/test_market_router_v3_current_provider.py tests/test_architecture_boundaries.py -q
```

Architecture boundary validation:

```text
git pull --ff-only && PYTHONPATH=. python scripts/validate_architecture_boundaries.py --policy config/architecture/architecture-boundary-policy-v1.json --ref HEAD
```

The hosted `Tests` workflow on the exact final PR head is the repository-wide acceptance gate. No live provider, Current Shadow, fresh-holdout, SportyBet transport or wager action is required for P1.4.

## Rollback

Rollback is a revert of the P1.4 merge. Existing v1, v2 and v3 Router implementations remain untouched, so rollback requires no provider/data migration. Retirement remains separately sequenced and evidence-gated.
