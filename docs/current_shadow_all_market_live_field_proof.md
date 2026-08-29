# Current Shadow all-market live field proof (PR F)

PR F is the final field-proof and narrow-hardening stage of master issue #261.
It exercises the merged research-only chain against current provider evidence;
it does not create production Phase-6 authority and it never places a wager.

## Mandatory source checkpoint

Before implementation or live execution, the following canonical sources were
re-read at main `2303c2df05c9bb2ed585b9a036deadaed8108fc3`:

- master issue #261 and its six-PR Shadow mission order;
- the ATHENA Expansion Blueprint / Master Roadmap architecture preserved by
  #261: shared fixture and goal/score state, specialist models only where
  required, price every eligible market before routing, disciplined portfolio
  shortfall, then exact provider verification;
- merged PR B (#264), including the 15-market semantic registry and explicit
  unavailable/unproven provider state;
- merged PR C (#265), including full settlement distributions and fail-closed
  current WEH inputs;
- merged PR D (#266), including source-replayed Price-all and all-market Router;
- merged replacement PR E (#268), including the frozen Portfolio policy and
  one current research runner;
- current SportyBet discovery, event-detail evidence, exact reconciliation,
  mapping, quote, semantic resolution, and anonymous create/reload boundaries;
- current PR151 durable fresh-history and UTC-native xG source contracts; and
- the production Phase-6 request/confirmation contracts.

The checkpoint confirmed these invariants:

1. No bookmaker price enters football inference.
2. Every compatible exact quote is priced before the Router selects or returns
   `NO_BET`.
3. Portfolio target size is never a minimum and weak legs are never padded.
4. Provider identity uses exact event/market/outcome/specifier/line semantics;
   no fuzzy or nearest-line fallback is permitted.
5. Anonymous create/reload is transport verification only. Login, cookies,
   wallet, stake, wager and BET authority remain absent.
6. Production Phase 6 remains blocked until the reviewed fresh-holdout
   confirmation boundary is satisfied.

## Field-proof status

The durable final field-proof receipt and current 15-market reality matrix are
produced only by the hosted live workflow on the exact final PR head. A verified
share code may appear only after exact create/reload equality. A truthful no-code
terminal state is an equally valid field-proof result.

`wager_placed=false` is invariant.
