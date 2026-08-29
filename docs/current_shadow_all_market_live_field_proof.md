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

## Live defects hardened

The first hosted run on PR F head `4edc010453da95069f7dda38198b5543a0cc2c70`
(Actions run `33278608570`) failed before provider acquisition because the
workflow executed the Python file by path. That made Python search from
`scripts/` and the import of the top-level `domain` package failed. The workflow
now invokes the existing runner as `python -m scripts.execute_current_shadow_all_market`.
This changes no football, semantic, freshness, routing, portfolio, or transport
policy.

The next hosted run (`33278685466`) reached the transparent current FotMob
capture and observed the already-reviewed additive terminal-state fields
(`awarded`, `scoreStr`, `ongoing`, red-card counts and `liveTime`). The frozen
PR39 candidate builder previously called only the base PR39 assessment, so it
rejected those exact reviewed fields. Candidate issuance now tries frozen PR39
first and, only on that precise structural rejection, replays the existing
strict PR87/PR89 extension chain. PR39 itself is unchanged; unknown fields,
wrong types and semantic promotion still fail closed.

That corrected run (`33279000638`) then produced the first durable terminal
receipt. At 22:37 UTC the prior runner requested only `20260829`, whose fixtures
had already started or finished; PR243 correctly approved none. The current
fixture-universe issuer now checks a fixed three-date UTC horizon and chooses
the earliest exact reviewed nonempty catalogue. It does not accept a caller
date, merge hand-picked fixtures, skip a nonempty earlier date, or alter PR243's
recency/kickoff-lead policy.

The next exact-head provider run reached SportyBet discovery. The current
anonymous endpoint returned 29 events for every requested page number even
though the reviewed request asks for 100. Requiring a later empty response made
the capture loop hit its maximum without establishing a terminal condition.
Discovery now records one of two exact, replay-verified termination bases:
`EMPTY_PAGE` or `SHORT_PAGE_BELOW_REQUESTED_PAGE_SIZE`. A nonempty page is a
terminal short page only when its exact extracted event count is strictly less
than the requested page size. A full page still requires a later reviewed
terminal condition and still fails at the page cap. The manifest records the
basis and keeps `terminal_empty_page_observed` truthful; repeated-page detection
is not treated as completeness.

`wager_placed=false` is invariant.
