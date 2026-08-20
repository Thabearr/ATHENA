# ATHENA 15-market analytical capability contract

## Purpose

This boundary separates **having a model that can produce an analytical market
prediction** from every downstream bookmaker authority.

ATHENA's weekend target is the complete canonical `MarketId` registry: all 15
market houses must ultimately produce a real analytical output for one upcoming
fixture.  That target does **not** mean that all 15 are already production
approved, freshly priced, selectable, or BET-authorized.

The authority dimensions are independent:

1. analytical model availability;
2. settlement representation;
3. calibration/evidence state;
4. pricing authority;
5. selection authority;
6. BET authority.

This PR keeps pricing, selection, and BET authority false in the new canonical
analytical projection layer.

## Common ScoreMatrix houses

`domain/score_matrix_market_probabilities.py` consumes an already-built,
normalized `ScoreMatrix`.  It does not calculate expected-goals rates itself.

It provides the common projection family for:

- Match Result;
- Total Goals on exact half-goal lines;
- Double Chance;
- BTTS;
- Draw or Over 2.5;
- Away or Over 2.5;
- Home or Over 2.5;
- Draw No Bet;
- Home Win to Nil;
- Away Win to Nil;
- Asian Handicap on exact quarter-goal grid lines.

Draw No Bet and Asian Handicap preserve the complete settlement distribution
from `domain/score_matrix_settlement.py`; they are not flattened into a fake
binary event probability.

Total Goals is intentionally restricted to half-goal lines in this common
projection boundary.  Integer and quarter-goal totals can carry push/split
settlement mass and must not be represented by `over + under = 1` until their
own exact settlement implementation is reviewed.

Double Chance is explicitly tagged as `OVERLAPPING_EVENTS`: 1X, X2 and 12 are
not mutually exclusive and are not required to sum to one.

## Specialized houses

The common ScoreMatrix projector refuses to proxy the specialized model
families:

- Home Win Either Half;
- Away Win Either Half;
- Match Result 1UP;
- Match Result 2UP.

Win Either Half already has reviewed research models.  The frozen Stage 4B
interpretation keeps the selected `logistic_l2_c0.1_v1` base configuration for
both targets, with selected isotonic calibration for Home and identity
calibration for Away.  Those research models need a dedicated prospective
runtime inference wrapper; they must not be replaced by full-time score-matrix
win probabilities.

1UP and 2UP remain the genuinely unfinished analytical family.  They require
exact provider promotion semantics plus a lead-path probability model.  The
existing SportyBet canonical mapping preserves the market identifiers but
explicitly says provider promotion-rule equivalence is unproven.  A full-time
win proxy is forbidden.

## Registry compatibility

`domain/model_status.py` now records analytical availability, settlement shape,
and calibration/evidence status independently from downstream authority.  The
old `selectable` property is retained temporarily as a compatibility name for
legacy analytical-candidate code; it is **not** the new selection-authority
field and must not be used as proof that a SportyBet selection or BET is
authorized.

The migration of old runtime consumers to the explicit authority fields is a
separate integration boundary so this capability PR does not silently change
legacy decision behavior while the 15-market prediction stack is assembled.

## Weekend acceptance criterion

The final fixture orchestrator must satisfy:

```text
set(predicted_market_ids) == set(MarketId)
```

for a valid upcoming fixture, with every prediction naming the actual model
family that produced it.  No 50/50 placeholder, full-time proxy, silent default,
or fabricated probability may be used to achieve 15/15 coverage.

The remaining sprint boundaries are:

1. upcoming fixture evidence/features -> reviewed xG rates -> ScoreMatrix;
2. prospective Win Either Half inference wrapper around the frozen reviewed
   research models;
3. exact 1UP/2UP provider-rule and lead-path model;
4. one fixture-level orchestrator that composes all 15 analytical houses.

Fresh SportyBet quote/snapshot authority, value, selection, staking, and BET
remain independent later gates.
