# DNB and Asian Handicap settlement-probability protocol

## Purpose

This boundary puts the next two score-matrix-derived market families in order without pretending ATHENA is production-ready. It specifies deterministic, regulation-time settlement probabilities for Draw No Bet and Asian Handicap from an already-constructed normalized `ScoreMatrix`.

This boundary does **not** refit expected goals, approve the fresh FotMob successor, acquire bookmaker prices, de-vig odds, calculate edge, calculate Kelly stakes, select bets, construct slips, or authorize `BET`.

## Shared score-matrix basis

Both markets consume the same normalized regulation-time score distribution used by ATHENA's reviewed score-matrix markets. No new football model is introduced here. Unknown scores outside the retained adaptive matrix are not invented; the existing tail-tolerance and normalization audit remain authoritative.

For a selected side, define the regulation-time score margin before handicap as:

- Home: `home_goals - away_goals`;
- Away: `away_goals - home_goals`.

All settlement probabilities are exact sums over mutually exclusive retained scorelines.

## Settlement probability states

The shared settlement representation contains five mutually exclusive states:

- `full_win`;
- `half_win`;
- `push`;
- `half_loss`;
- `full_loss`.

Their probabilities must be finite, non-negative, and sum to one within the numerical discipline of the normalized score matrix.

For a quoted decimal price `o`, the unit-stake expected profit implied by a settlement distribution is:

`full_win * (o - 1) + half_win * 0.5 * (o - 1) - half_loss * 0.5 - full_loss`.

The probability mass that carries winning exposure is:

`effective_win_mass = full_win + 0.5 * half_win`.

The probability mass that carries losing exposure is:

`effective_loss_mass = full_loss + 0.5 * half_loss`.

Where their sum is positive, the settlement-adjusted break-even probability is:

`effective_win_mass / (effective_win_mass + effective_loss_mass)`.

The corresponding fair decimal odds are its reciprocal. These are probability/settlement research quantities only; this boundary does not compare them with bookmaker prices.

## Draw No Bet

For Home DNB:

- home regulation win -> `full_win`;
- regulation draw -> `push`;
- away regulation win -> `full_loss`.

Away DNB is the exact mirror.

Therefore the settlement-adjusted Home DNB probability is:

`P(Home win) / (P(Home win) + P(Away win))`.

The draw is never silently converted into a loss or removed from the audit. It remains explicit push probability. If the matrix contains only draw probability, the settlement-adjusted win probability and fair odds remain unavailable rather than being invented.

## Asian Handicap

The canonical selected-side line is **added to that selected side's regulation score** before comparison. Thus Home `-0.5` means `home_goals - 0.5` is compared with `away_goals`; Away `+0.5` means `away_goals + 0.5` is compared with `home_goals`.

Only standard quarter-goal grid lines are supported: exact multiples of `0.25`. Non-quarter lines fail closed.

### Half-goal lines

Half-goal lines cannot push with integer football scores. They produce only `full_win` or `full_loss`. The pre-existing `ScoreMatrix.asian_handicap_cover()` remains the compatibility reference for half-goal cover probabilities; the new settlement engine's `full_win` must equal it exactly within numerical tolerance.

### Integer lines

Integer lines produce `full_win`, `push`, or `full_loss` according to the adjusted selected-side score.

### Quarter-goal lines

Quarter lines split the stake equally across the two adjacent half-step lines. Examples:

- `-0.25` -> `-0.5` and `0.0`;
- `+0.25` -> `0.0` and `+0.5`;
- `-0.75` -> `-1.0` and `-0.5`;
- `+0.75` -> `+0.5` and `+1.0`.

Two component wins -> `full_win`.
One component win plus one push -> `half_win`.
One component loss plus one push -> `half_loss`.
Two component losses -> `full_loss`.

A direct win/loss component pair is not a valid result for adjacent quarter-line components and fails closed if it is ever observed.

## Authority boundary

After this work, DNB and full standard Asian Handicap settlement probabilities may be used by a later **shadow/research** prediction surface. This boundary alone does not change current selection authority.

In particular:

- `DRAW_NO_BET` remains disabled in the production/selectable registry until push-aware pricing/value integration is reviewed;
- existing Asian Handicap candidate export may remain narrower than the new settlement core until a later integration boundary;
- no bookmaker odds become fresh or trusted because these calculations exist;
- no production/model/BET gate is granted.

## Next boundary

After this settlement core is implemented and reviewed, the next model-house boundary is prospective Win Either Half inference from reviewed current-history inputs. Pricing/value integration for push/split-settlement markets remains a separate trust boundary.
