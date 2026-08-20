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

The frozen provider receipt is jurisdiction-specific. It binds SportyBet
Nigeria's official [football rules](https://lite.sportybet.com/ng/help?nav=sports)
and the raw preserved Nigeria capture `www_sportybet_com 2.html`; Ghana and
Tanzania help surfaces are not used. A canonical tracked source-evidence
manifest records the rendered Nigeria clauses and the raw capture's exact
118,608-byte / SHA-256 identity.

- `one_x_two_one_up`: source market `1` -> provider mapped market `60200`;
- `one_x_two_two_up`: source market `1` -> provider mapped market `60100`.

Both captured entries require `preMatch=true`, `live=true`, football sport ID
`sr:sport:1`, and their corresponding provider settlement-feature list
(`[[1,60200]]` / `[[1,60100]]`). The receipt therefore proves more than the
configuration-key names.

Exact evidence identities are:

| Evidence | Bytes | SHA-256 |
|---|---:|---|
| Canonical Nigeria source-evidence manifest | 1,856 | `f09f96d906a6afe9e349660043dd85325b375916adf13bfc5c0c4f1ff881e8ba` |
| Official Nigeria rendered-help section inside manifest | 922 | `87a1a4b56a9349b0987b6a38c85cadf4dd2ccd18066c916659351c75345f3b13` |
| Preserved raw Nigeria site configuration | 118,608 | `c27ea6ee2eff74eb1f6ca8c90d241d63ece333171196225439c0e97a2faf86c7` |

The canonical settlement receipt is 2,279 bytes with SHA-256
`acdefca105e53d55a3dfad767cfc9a4b0b2731f720b8256d12f55effbc452152`.
Changed Nigeria clauses, raw-capture anchors, mappings, enablement state,
receipt objects, or receipt bytes fail closed.

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
Supplying the exact receipt and bytes permits only when the source-replayed
selection also has provider market ID `60200` for 1UP or `60100` for 2UP:
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
