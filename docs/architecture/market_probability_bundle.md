# Canonical Market Probability Interface

## Mission

P1.2 establishes the unversioned canonical football-probability boundary described by the ATHENA Architecture Remediation Master Implementation Specification v2.

The purpose is narrow: football probabilities must be separable from provider pricing and market routing. This PR does not promote a pricing implementation, router, portfolio optimizer, delivery service, model formula, provider-acquisition path, or production betting authority.

The canonical owner is:

```text
domain.market_probabilities
```

The temporary Current Shadow compatibility adapter is:

```text
domain.current_shadow_market_probability_adapter
```

The adapter is one-way. Existing Current Shadow model output is projected into the canonical contract. The canonical module does not import Current Shadow, SportyBet, Price-all, router, portfolio, delivery, login, wallet, staking, or wager code.

## `MarketProbabilityBundle`

A bundle is immutable and fixture-scoped. It contains:

- exact canonical fixture identity;
- optional score-grid identity when an available market depends on the normalized score grid;
- exactly one probability-distribution row for every canonical `MarketId`;
- explicit specialist-model outputs for specialist markets that are analytically available;
- model-only evidence retained from the source projection;
- an all-false downstream authority map.

It deliberately contains no bookmaker odds, quote identity, provider market binding, expected value, routed opportunity, recommended market, selected market, portfolio selection, staking instruction, or wager state.

## Score-grid identity

When any score-grid-backed market is available, the bundle requires an exact score-grid SHA-256 and the score-grid audit record. Current Shadow already exposes the normalized score-matrix content identity through its reviewed 1UP/2UP specialist evidence; the adapter reuses that existing identity instead of inventing a second score-grid hash.

If Current Shadow cannot prove one exact score-grid identity for available score-grid-derived probabilities, adaptation fails closed.

Win Either Half is not treated as a score-grid derivative. The early-payout 1UP/2UP models use the score grid but retain explicit specialist semantics because their settlement event is not an ordinary final-score partition.

## Probability representations

The canonical interface distinguishes three probability topologies.

### Mutually exclusive partition

Ordinary markets such as 1X2, BTTS, win-to-nil, result-or-total and each exact Total Goals half-line must form a valid probability partition.

For an ordinary partition, mass must sum to one within the canonical tolerance.

### Overlapping events

Double Chance and the reviewed 1UP/2UP early-payout events are explicitly overlapping. Their event probabilities are not incorrectly forced to sum to one.

### Settlement distributions

Draw No Bet and Asian Handicap preserve full settlement probability distributions rather than collapsing push/half-win/half-loss states into a fake scalar probability.

Every selection distribution must partition the settlement mass into:

- full win;
- half win;
- push;
- half loss;
- full loss.

The total mass must equal one within the canonical tolerance.

## Total Goals consistency

For each Total Goals line:

```text
P(OVER line) + P(UNDER line) = 1
```

Across increasing half-goal lines:

```text
P(OVER lower) >= P(OVER higher)
P(UNDER lower) <= P(UNDER higher)
```

This consistency is enforced by the canonical contract rather than delegated to a later router.

## Specialist outputs

An analytically available specialist market must have an explicit `SpecialistModelOutput` whose probability method and input namespace agree with the canonical market row.

Current compatibility mappings are:

- Home Win Either Half -> `WIN_EITHER_HALF_ANALYTICAL_INFERENCE`;
- Away Win Either Half -> `WIN_EITHER_HALF_ANALYTICAL_INFERENCE`;
- Match Result 1UP -> `EARLY_PAYOUT_LEAD_PATH`;
- Match Result 2UP -> `EARLY_PAYOUT_LEAD_PATH`.

Specialist evidence may preserve reviewed model/settlement identities that are part of probability semantics. It may not smuggle quote or bookmaker-price evidence into the probability layer.

## Calibration semantics

Each available market row records the current calibration-status semantic from the existing model registry. Existing concrete model/calibration identities are retained in model or specialist evidence when Current Shadow already exposes them.

P1.2 does not fabricate a calibration artifact identity that the current source contract does not possess. Later component-authority and promotion work remains responsible for stronger champion/challenger registry identity.

## Current Shadow compatibility

`market_probability_bundle_from_current_shadow_fixture_scan()` reconstructs the exact Current Shadow fixture-scan type first so its existing fail-closed invariants are replayed. It then removes the provider-pricing axis and creates the canonical football-probability view.

Provider readiness does not change the football probability bundle. `ANALYTICAL_READY` and `ANALYTICAL_READY_PROVIDER_BLOCKED` therefore project to the same canonical football-probability row when the underlying model output is the same.

The compatibility projection hash intentionally excludes provider semantic status. This prevents a bookmaker outage or provider-registry change from changing the identity of football probability evidence.

Blocked analytical markets remain blocked and carry no invented probability output.

## Price-all migration seam

Current Shadow Price-all now constructs the canonical bundle before iterating market probabilities. For each market, the canonical row is projected through a narrow compatibility adapter back into the legacy pricing-assessment shape so existing source ancestry and provider exact-quote semantics remain unchanged.

This is intentionally transitional. P1.3 will promote the canonical Price-all interface. P1.2 changes the probability source boundary only; it does not change quote matching, freshness, de-vig, settlement return, expected-value mathematics, router policy, or portfolio policy.

The P1.2 exit gate is therefore testable now:

```text
Price-all consumes MarketProbabilityBundle probability values.
Price-all has no dependency on legacy Prediction.recommended_market.
```

## Serialization

Canonical serialization is deterministic UTF-8 JSON with:

- sorted keys;
- compact separators;
- one trailing LF;
- no NaN or Infinity;
- duplicate JSON keys rejected;
- exact schema and policy identities;
- byte-exact round-trip verification.

The canonical SHA-256 is the SHA-256 of those bytes.

## Authority boundary

Every canonical probability bundle fixes these authorities to `false`:

- production probability;
- pricing;
- routing;
- selection;
- staking;
- wager.

P1.2 is an interface/convergence PR. It grants no new operational authority and triggers no provider acquisition, Current Shadow run, SportyBet transport, login, cookies, wallet, staking, or wagering.

## Explicitly out of scope

This PR does not:

- change football formulas;
- retrain or recalibrate a model;
- alter Current Shadow provider acquisition;
- change provider semantic mapping;
- alter quote freshness or minimum-lead rules;
- introduce a canonical Price-all owner (P1.3);
- change router/coherence semantics (P1.4);
- change portfolio caps or target-leg selection (P1.5);
- change share-code transport (P1.6);
- establish the full component authority registry (P1.7);
- delete or retire a legacy module.

No cleanup/deletion authority follows from this PR alone.

## Validation

Focused validation:

```text
git pull --ff-only && PYTHONPATH=. python -m pytest tests/test_market_probabilities.py tests/test_current_shadow_market_probability_adapter.py tests/test_current_shadow_all_market_price_all_router.py -q
```

The hosted `Tests` workflow remains the final repository-wide acceptance gate for the exact review head.
