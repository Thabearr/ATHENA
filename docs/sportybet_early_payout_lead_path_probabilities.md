# SportyBet 1UP/2UP settlement and lead-path analytics

## Boundary

This boundary makes `MATCH_RESULT_1UP` and `MATCH_RESULT_2UP` analytically
callable from an already-built normalized `ScoreMatrix`. It does not build
fixture features or expected goals, fetch SportyBet, accept odds, estimate
abandonment frequency, de-vig prices, rank selections, or emit a bet.

The model identifier is
`independent_poisson_conditional_goal_order_lead_path_v1`. Both markets remain
`EXPERIMENTAL`. Analytical prediction is available; fresh-price, pricing,
value, market-activation, selection, execution, production-approval, and BET
authority remain false.

## Provider evidence

The frozen provider receipt uses exact review projections from SportyBet's
official [football rules](https://www.sportybet.com/gh/help?nav=sports) and
[early-payout help](https://www.sportybet.com/tz/help?nav=others), plus the
reviewed canonical projection of the captured site-configuration keys:

- `one_x_two_one_up` -> `MATCH_RESULT_1UP`;
- `one_x_two_two_up` -> `MATCH_RESULT_2UP`.

Exact source projection identities are:

| Evidence | Bytes | SHA-256 |
|---|---:|---|
| Official football-help clauses | 691 | `aeaed927e27acc4b288e17e07f6929ac72233a05a0da561fcb8f003b682e925a` |
| Official early-payout clauses | 502 | `9be284608bae3f551a71d42c5f1f17331e35b499c8e7e0969cb7d9d63547851a` |
| Captured site-configuration key projection | 40 | `30a9b91af55a66610ede5731bfb03648ccc3c1cc9a0280b388124c24b0478240` |

The canonical settlement receipt is 2,029 bytes with SHA-256
`123868403511a175d3eccba8613f5681c56ddcb3cdb304aa132104dd90e0ca10`.
Changed source text, configuration keys, receipt objects, or receipt bytes fail
closed.

SportyBet defines ordinary 1X2 as selecting the regulation-time match winner
and describes 1UP/2UP as an earlier payout in the dedicated 1X2 products. The
reviewed contract is therefore the union of ordinary full-time team victory
and the irreversible lead trigger. This matters for 2UP: a 1-0 final Home win
is a winning Home selection even though Home never led by two. Draw remains
the ordinary full-time draw result.

The official evidence also preserves that an already-triggered early payout
stands after abandonment. ATHENA models no abandonment probability. The
analytical probabilities are explicitly normal-completion regulation-time
football probabilities; the unmodelled abandonment process prevents any
selection or BET authority.

Historical PR166 mapping receipts remain byte-compatible: without the new
exact settlement receipt they retain `PROVIDER_PROMOTION_RULES_UNPROVEN`.
Supplying the exact receipt and bytes permits only
`REVIEWED_SPORTYBET_EARLY_PAYOUT_SETTLEMENT_EQUIVALENCE`; it still grants no
fresh-price, pricing, selection, execution, or BET authority.

## Exact conditional path model

For final score `(h, a)`, the independent homogeneous Poisson model implies
that all `C(h+a, h)` Home/Away goal-label orderings are equiprobable conditional
on those counts. `conditional_lead_hit_probabilities` uses an integer dynamic
program to count four disjoint path classes:

- Home threshold only;
- Away threshold only;
- both thresholds;
- neither threshold.

It divides only after exact counts are complete. There is no Monte Carlo,
chronology proxy, or full-time-win substitution.

For 1UP:

- Home = Home ever reaches lead `+1`;
- Away = Away ever reaches lead `-1`;
- Draw = final score is level.

Any full-time team win necessarily contains the corresponding one-goal lead,
so the ordinary fallback is already contained mechanically.

For 2UP:

- Home = Home ever reaches `+2` **or** wins at full time;
- Away = Away ever reaches `-2` **or** wins at full time;
- Draw = final score is level.

The conditional probabilities are integrated over every retained cell in the
normalized `ScoreMatrix` using `math.fsum`. The projection records a canonical
fingerprint of the exact normalized and raw matrix cells consumed.

## Topology

Home, Draw, and Away are `OVERLAPPING_EVENTS`. For example, Home may trigger
1UP, Away may later trigger 1UP, and the final result may be Draw. Their three
probabilities need not sum to one and are never renormalized. Ordinary 1X2
de-vig mathematics is not valid for this topology.

This boundary does not alter ScoreMatrix normalization or any other canonical
market projection.
