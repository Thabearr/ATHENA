# Price-all v2 direct-provider quote consumption

## Status

This boundary is the explicit consumer required by PR #247:

`PRICE_ALL_V2_DIRECT_PROVIDER_QUOTE_CONSUMPTION_REQUIRED`

It is a separate Price-all lane. It does not mutate or reinterpret the frozen
Phase 7 v1 user-controlled SportyBet Lite HTML quote-source contract.

## Source ancestry

The only accepted quote source is an exact
`SportyBetDirectProviderPriceAllQuoteSource` issued by
`domain/sportybet_price_all_direct_provider_quote_adapter.py`.

Before any value record is issued, Price-all v2 reconstructs that source back
through the retained PR #246 live mapped quote bundle. This preserves the
reviewed chain:

1. public anonymous SportyBet FactsCenter event GET;
2. exact raw response bytes and SHA-256;
3. live provider-native event inventory;
4. reviewed canonical SportyBet mapping;
5. fixture reconciliation receipt;
6. PR #246 current mapped quote bundle;
7. PR #247 direct-provider Price-all quote-source adapter;
8. PR #248 Price-all v2 value evaluation.

The v2 result retains the quote-source canonical SHA-256, PR #246 source-bundle
SHA-256, adapter contract SHA-256, legacy Price-all v1 contract SHA-256, and v2
contract SHA-256.

Provider-native quote timestamp and provider snapshot identity remain `null`.
The observation authority remains:

`ATHENA_DIRECT_PROVIDER_RESPONSE_COMPLETION_NOT_PROVIDER_QUOTE_TIMESTAMP`

No later boundary may relabel that response-completion time as a provider quote
timestamp.

## Frozen dependencies

Price-all v2 validates all of these before evaluation:

- PR #247 adapter contract:
  `6813c74ca286f139f5cb0ac40a78147fd3762d76ca1e637aa0b7d6c5282bc903`;
- frozen legacy Price-all v1 contract:
  `1fb0a6c891adccd76b4864a6197e55d22154176a4191f57ce92cde13501535aa`;
- Price-all v2 direct-provider contract:
  `b5e3c063ac8b4e9fc1521cabbfe1da873a67b70efc67bc08d8ada61f2024e599`.

The v2 contract intentionally reuses the reviewed v1 de-vig and settlement
return policy identities while changing the quote-source ancestry.

## Evaluation-time freshness

PR #247 preserves the original live observation time and explicitly says that
Price-all must recheck age. PR #248 does that at its own evaluation time.

Frozen defaults:

- maximum quote age: `900` seconds;
- minimum kickoff lead: `120` seconds.

Callers may tighten the maximum age below 900 seconds. They may not increase it
above 900 seconds.

Callers may increase the kickoff lead requirement above 120 seconds. They may
not reduce it below 120 seconds.

The evaluation time must not predate the live source issuance time.

This matters because a quote that was valid when PR #246 issued its
`LIVE_CURRENT` bundle can become stale or too close to kickoff before Price-all
uses it.

## Candidate matching

Every input must be an exact `CalibratedValueCandidate` issued from the frozen
Phase 6 calibration ancestry.

For each candidate, Price-all v2 requires the same:

- fixture ID;
- SportyBet event ID;
- canonical market;
- canonical outcome;
- canonical line.

A different fixture/event is explicitly `UNPRICED_SOURCE_MISMATCH`.

A candidate in the correct fixture/event with no current mapped quote is
`UNPRICED_NO_EXACT_QUOTE`.

ATHENA does not substitute a nearby market, another line, another outcome, an
old mapping price, or a different provider selection.

## Settlement-aware EV

The value calculation preserves the reviewed Phase 7 settlement-return
semantics.

Unit-stake profit returns are:

- `WIN`: decimal odds minus one;
- `HALF_WIN`: half of decimal odds minus one;
- `PUSH`: zero;
- `HALF_LOSS`: minus one half;
- `LOSS`: minus one.

The candidate's calibrated settlement probability representation is used
directly. Draw-no-bet, Asian handicap, integer totals, quarter lines, and
ordinary win/loss markets retain their reviewed settlement distinctions.

`net_expected_value` is the expected unit-stake profit. `ev_percentage` is that
value multiplied by 100.

Bookmaker prices never enter the football probability model.

## De-vig

Ordinary proportional de-vig is performed only when the current direct-provider
source contains a complete mutually exclusive/exhaustive partition with the
same reviewed ancestry.

A partition must share the exact:

- fixture and event;
- SportyBet source;
- provider market ID and specifier;
- canonical market and line;
- live inventory SHA-256;
- source bundle SHA-256;
- source manifest SHA-256;
- raw response SHA-256;
- reviewed mapping SHA-256;
- fixture reconciliation SHA-256.

Match Result, BTTS, exact half-goal totals, reviewed result-or-totals YES/NO
markets, and win-to-nil YES/NO can expose proportional fair probabilities when
the partition is complete.

Double Chance and early-payout families are overlapping events and therefore do
not receive a false ordinary de-vig.

Draw No Bet, Asian Handicap, and push/split totals do not receive a false
ordinary de-vig.

An incomplete current partition remains priced for settlement-aware EV when an
exact quote exists, but `fair_probability` remains unavailable.

## Missing and unavailable provider rows

PR #246 audits reviewed mapping rows that are absent from the current event or
currently unavailable.

PR #247 preserves those audits and emits no guessed quote.

PR #248 carries those mapping audits into the evaluation bundle. A candidate
whose reviewed row is currently absent therefore remains explicitly unpriced.
No replacement quote is invented.

## Output and authority

`PriceAllV2DirectProviderEvaluation` contains:

- source/evaluation timing;
- kickoff timing;
- effective freshness policy;
- full source and contract identities;
- one deterministic result for every candidate;
- preserved PR #246 mapping audits;
- explicit authority flags;
- `wager_placed=false`.

The output grants only:

- verified direct-provider price consumption;
- Price-all value-record computation.

It does **not** grant:

- football probability generation;
- model promotion;
- Market Router authority;
- final-selection authority;
- accumulator authority;
- SportyBet execution;
- staking;
- BET authority.

The evaluator does not rank candidates and does not force a leg.

## Builder-only reconstruction

Public result/evaluation constructors are disabled.

`verify_price_all_v2_direct_provider_evaluation(...)` rebuilds the entire output
from the retained exact candidate tuple and exact verified quote-source
ancestry. Public-field relabelling or source tampering fails closed.

## Next boundary

The exact next boundary declared by this module is:

`MARKET_ROUTER_V2_DIRECT_PROVIDER_VALUE_CONSUMPTION_REQUIRED`

The existing Market Router v1 remains bound to Phase 7 v1
`SportyBetExactQuote` / `PriceAllValueResult` identities and must not silently
consume the new direct-provider v2 result type.

A later reviewed Router v2 boundary must explicitly adopt this Price-all v2
contract and preserve NO BET as a first-class decision.
