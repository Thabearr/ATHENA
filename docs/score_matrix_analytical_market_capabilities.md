# ScoreMatrix analytical market capabilities and authority separation

## Boundary

This change separates five questions that the former `ModelStatus` label
conflated:

1. whether an existing normalized `ScoreMatrix` can mechanically derive an
   analytical result;
2. whether that result has ordinary event or full settlement-distribution
   semantics;
3. whether the underlying expected-goals model is calibrated and freshly
   confirmed;
4. whether a current bookmaker price is authorized;
5. whether a selection may be emitted.

The answers are intentionally independent. `ACTIVE` and `EXPERIMENTAL` remain
legacy maturity labels only. `selectable` now derives solely from explicit
`SelectionAuthority`, and every current market is `NOT_AUTHORIZED` for both
pricing and selection.

The reviewed calibration state remains
`MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED`. The fresh
prospective campaign has `ZERO_COMMITTED_OBSERVATIONS`. Mathematical
derivability therefore does not imply fresh calibration, pricing, selection,
production, or BET authority.

## Canonical projection

`domain.score_matrix_market_probabilities` consumes an already-built
`ScoreMatrix`. It does not build fixture features or expected goals and accepts
no bookmaker price. Its immutable, canonical JSON projection grants no pricing,
market activation, selection, production, or BET authority.

Ordinary event projections are available for:

- Match Result: HOME, DRAW, AWAY;
- Total Goals: OVER and UNDER for exact non-negative half-goal lines only;
- Double Chance: 1X, X2, and 12;
- BTTS: YES and NO;
- Draw/Away/Home or Over 2.5: YES and NO;
- Home/Away Win to Nil: YES and NO.

Match Result and ordinary binary pairs are mutually exclusive partitions.
Double Chance is explicitly `OVERLAPPING_EVENTS`: 1X, X2, and 12 are separate
overlapping events and must not be de-vigged or normalized as a three-outcome
partition.

Integer and quarter Total Goals lines are rejected because push/split total
settlement is not implemented here. The projector never discards push mass to
manufacture a complementary binary market.

## DNB and Asian Handicap

PR185's existing `draw_no_bet_settlement` and `asian_handicap_settlement` are
the sole settlement implementations. The projector delegates to them and
preserves:

- full win;
- half win;
- push;
- half loss;
- full loss;
- effective winning, losing, neutral, and active stake mass;
- settlement-adjusted break-even probability where defined;
- fair decimal odds where defined.

Those last two quantities are settlement summaries, not raw event
probabilities. DNB exposes HOME and AWAY win/push/loss distributions. Asian
Handicap accepts an exact quarter-goal HOME line and exposes the AWAY side at
the exact opposite line, preserving integer, half-goal, and quarter-goal
settlement semantics.

## Specialized analytical markets and remaining blocks

`HOME_WIN_EITHER_HALF` and `AWAY_WIN_EITHER_HALF` remain excluded from the
ScoreMatrix projector because full-time score probability is not a half-by-half
proxy. They are analytically available only through the separate frozen WEH
Stage 4A/4B predictor and its exact specialized 74-feature input namespace.
That availability grants no pricing or selection authority.

`MATCH_RESULT_1UP` and `MATCH_RESULT_2UP` are analytically available only
through `domain.early_payout_lead_path_probabilities`. That separate projector
binds the exact reviewed SportyBet settlement receipt and combines conditional
goal-order path counts with the normalized matrix. The events overlap and are
not ordinary 1X2 sums. This generic direct-score projector continues to reject
them so it cannot substitute full-time win probability.

## Legacy runtime containment

Legacy analytical evidence can continue to report ordinary score-matrix
probabilities. It cannot create a viable/ranked selection because the canonical
registry grants no selection authority. The accumulator rejects all direct
inputs without explicit registry selection authority, even when a caller
supplies odds. The generic fixture reasoner likewise treats supplied odds as
analytical-only unless both pricing and selection authority exist in the exact
registry.

Legacy DNB scalar values were removed from `MatchAnalyst`: full-time home/away
win mass is not a DNB probability. Consumers that need DNB analysis must use the
canonical settlement projection.

This boundary fetches no provider data, changes no expected-goals model, does
not touch the fresh-holdout control lane, calculates no Kelly stake, and emits
no BET.
