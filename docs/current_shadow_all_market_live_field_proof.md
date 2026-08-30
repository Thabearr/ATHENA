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
had already started or finished; PR243 correctly approved none. PR F therefore
introduced a fixed three-date UTC search horizon rather than accepting a caller
fixture list or weakening PR243's recency/kickoff-lead policy.

A later exact-head field run (`33334343547`) exposed a second, narrower fixture-
universe defect in that implementation. The runner stopped as soon as the first
policy-approved nonempty date was found. Late on `20260830`, that reduced a
`target_size=20` request to exactly one reviewed FotMob fixture while the same
bounded horizon still contained later UTC dates that had never been examined.
The run observed 38 current SportyBet events, obtained zero exact reconciliations,
and truthfully returned `RESEARCH_NO_CODE_INSUFFICIENT_SUPPORTED_MARKETS`.

The current runner now scans **every date in the same fixed three-date UTC
horizon**, retaining every date that independently passes the frozen PR243
policy before any provider reconciliation. Each retained date is reconciled
through the unchanged exact SportyBet boundary; no alias, fuzzy team matching,
kickoff tolerance, nearest event, manual provider ID, or caller-supplied odds is
introduced. Cross-date duplicate reconciliation of either a provider event or a
FotMob fixture fails closed. The receipt preserves the searched dates, every
policy-approved current FotMob source identity, per-date reconciliation SHA and
disposition counts, and the exact matched provider IDs. Expensive PR151 fresh-
history/model work is constructed only for date sources that actually earn an
exact provider reconciliation, preserving source ancestry while avoiding work
that cannot enter Price-all.

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

The following exact-head run (`33279866310`) reached the current source chain
but correctly failed PR151 lineage replay because the workflow had supplied the
PR branch head as the expected GitHub `main` identity. Those are different
proof domains. The runner now records the actual checked-out commit as its code
identity and separately passes a read-only, API-resolved `main` SHA to the
reviewed PR151 audit. The audit still fetches and requires exact equality with
that main SHA; this does not accept the PR head as historical lineage and does
not weaken the fresh-holdout gate.

The later exact-head run `33288774115` on
`5e03adf63f9d8ac0c7c07731061fc9fbab0c31a6` reached current SportyBet event
discovery and truthfully returned `RESEARCH_NO_CODE_SOURCE_INCOMPLETE`. The
retained cause was `SportyBetCurrentEventDiscoveryError: provider home team must
be an exact non-empty trimmed string`; no provider row was authorized, no leg
was selected, shortfall remained 20, no share code was created, and no wager
was placed.

A bounded anonymous diagnostic then reproduced the provider condition across
12 consecutive page-1 observations: live event `sr:match:72474924` was returned
with `homeTeamName` equal to `Comunicaciones FC ` (one trailing space),
`bookingStatus=Booked`, `status=1`, and `matchStatus=H2`. The row was therefore
not a prematch-bookable fixture and was ineligible for exact fixture
reconciliation authority. The current discovery lane now preserves a bounded
non-empty raw source team string for such nonbookable evidence without trimming,
normalizing, aliasing, or fuzzy matching it. Exact trimmed team strings remain
mandatory for every prematch-bookable event and every reconciliation-authorized
row. Missing/non-string team identity also fails closed instead of being coerced
through `str(...)`. The narrow hardening and its three regression tests passed
all eight synthetic test shards plus syntax/tree validation in Patch Bridge run
`33289331074` before the reviewed patch was pushed.

The later exact-head live run `33296875635` on
`b389cda48a97d2ce844303b864560db34778ee53` completed the hosted workflow and
uploaded a durable no-code receipt, but the research chain correctly stopped
before SportyBet discovery with `RESEARCH_NO_CODE_SOURCE_INCOMPLETE`. The
retained cause was a frozen PR39 schema rejection reached during the UTC-native
fresh-history/xG shadow replay after the same current FotMob capture had already
passed the reviewed current PR87/PR89 adapter. This demonstrated two stale
current-source replay boundaries rather than a reason to broaden accepted
FotMob schema.

The current shadow prediction lane now reuses the reviewed current candidate
bundle and a current-only PR149 provider-native qualification bridge. The bridge
keeps PR149 dependency verification and exact provider fixture/competition/team/
kickoff/capture-lineage checks, while avoiding a second replay of the already-
reviewed current capture through frozen PR39. Unknown current additive schema
still fails at the reviewed current adapter, and rows excluded by the narrow
UTC request-date projection cannot re-enter provider-native qualification.
Patch Bridge run `33309953121` proved the candidate-subset regression across
syntax/tree and all eight synthetic test shards; Patch Bridge run `33311370535`
then proved the shadow-prediction wiring cannot fall back into frozen PR149's
`qualify_capture_fixtures()` path, again with all eight synthetic shards green.

The exact-head rerun of workflow run `33328629573` on
`a9cce1d55fa8f28261d2680fd21ac489e56ffdec` demonstrated that the prior
25-minute worker budget could terminate during `PRICE_ALL_ROUTER`. The hosted
entrypoint already carries a bounded 50-minute worker supervisor; PR F widened
the surrounding GitHub Actions job ceiling from 30 to 60 minutes so that the
supervisor, rather than the outer job, remains the reviewed fail-closed runtime
boundary. Exact-head run `33334343547` on
`7bf614cd4c33aacab46b4140aae9d86726e143e2` then completed normally in about
29 minutes, proving that the outer hosted ceiling no longer caused the terminal
state. Its durable artifact was `9738955502` with ZIP SHA-256
`fb846332d53a9826bab1a70f09a9d687bad59eff9504f81e5c27f7295d6e0e24`.
That run still had zero exact FotMob↔SportyBet reconciliations, which is the live
evidence that drove the bounded multi-date fixture-universe correction above.

`wager_placed=false` is invariant.
