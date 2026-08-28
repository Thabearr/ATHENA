# Current ATHENA → SportyBet execution chain

## Scope

This change reconnects the merged PR #253 current mapped SportyBet quote
evidence to additive Price-all v3, Router v3, Portfolio v3, and the anonymous
SportyBet semantic create/reload boundary. Frozen v1/v2 modules remain
unchanged.

No wager is placed. No login, cookie, wallet, stake, proxy, third-party booking
service, ParseBot, or BookBet capability is introduced.

## Reviewed chain

The completed downstream composition is:

```text
PR #253 exact current mapped quote bundle
  → Price-all v3 settlement-aware value
  → Router v3 robust one-market-per-fixture decision / NO_BET
  → Portfolio v3 qualified legs, reserves, caps and shortfall
  → final exact source replay
  → semantic intent (no native market/outcome IDs or odds)
  → current SportyBet event semantic resolution
  → derived native event/market/outcome/specifier identity
  → direct anonymous SportyBet share/create
  → direct SportyBet share-code reload
  → exact semantic + native + specifier + odds + count verification
  → CODE_VERIFIED or fail closed
```

Price-all v3 reconstructs #253 before value and retains fixture/event,
provider market/outcome/specifier, canonical market/outcome/line, raw response,
manifest, inventory, #252 mapping and #251 reconciliation identities. Its
production lane owns wall-clock evaluation. The replay lane is explicitly
as-of and cannot claim currentness.

Ordinary de-vig requires one exact provider-native market and specifier plus
identical current evidence/mapping/reconciliation ancestry for every partition
member. DNB and Asian Handicap keep push/split settlement distributions and do
not receive ordinary de-vig.

Router v3 pins and preserves the Router v2 robust lower-envelope thresholds and
tie policy. Portfolio v3 pins and preserves the Portfolio v2 team,
competition, market-family and fragility caps. It derives current exposure by
replaying the exact retained PR #251 bundle; detached caller labels cannot mint
competition or team identity.

## Frozen identities

- PR #253 current mapped quote contract:
  `671e6016093bc3f30141ddd13ab259bebb70086945fb30a588a185703fd128d4`
- Price-all v3:
  `30481bc9ebf442f0e664bcd14d2c6cd18026a42a35083d143db6366837b3d425`
- Router v3:
  `61a90a29495399668e19ae4a149527abea98c172d7bdacf1a1b521776b4d771a`
- Portfolio v3:
  `4dc8be4e0a9f607b6c0804048bb326c0aa342d37fe540abbcd3e1b3a5f6a6dad`
- Current execution:
  `62d0f48942ca28eb9566f4803deea07e61598732198882cc515cd88c6209d359`

## Count and shortfall invariant

The requested fold count is a target. Router `NO_BET`, source staleness,
portfolio caps, and rejected opportunities are never overridden. No reserve or
weaker candidate is inserted after final optimization.

If the target is 20 and 19 legs qualify, the execution result is
`NO_CODE_SHORTFALL` with shortfall 1. Semantic resolution and provider create
are not called. A provider code is returned only when Optimizer-qualified,
semantic-intent, semantic-resolution, create-accepted and reload-accepted
counts are exactly equal.

## Semantic/native round trip

The execution adapter gives the semantic gate only:

- event ID;
- expected home and away names;
- expected provider market name;
- expected provider outcome name;
- exact specifier, when present.

It never passes caller-provided market IDs, outcome IDs, odds, or a preselected
slip as semantic authority. The current SportyBet event response resolves the
native IDs. The selected #253 quote, semantic resolution, provider create, and
provider reload must all agree on fixture, market, outcome, specifier, native
IDs and accepted odds. Native transport success by itself is insufficient.

The durable receipt retains create/load response hashes through the direct
transport receipt and records `wager_placed=false`.

## Fixed request entry point and current blocker

The production-facing command accepts only a bounded target size:

```bash
python scripts/execute_current_sportybet_accumulator.py \
  --target-size 20 \
  --output-dir artifacts/current-sportybet-accumulator
```

The hosted workflow exposes the same target only. It does not accept a Python
factory, event IDs, native IDs, odds, candidate legs, or a slip.

At the current authoritative main, the upstream request cannot truthfully
issue live Phase 6 candidates. The latest reviewed handoff in
`domain/current_fotmob_latest_durable_fresh_history.py` explicitly states that
even complete current durable history grants no production model,
ScoreMatrix, probability, Phase 6, pricing, selection or SportyBet authority.
Its exact next boundary is:

`CURRENT_UTC_NATIVE_MODEL_PRODUCTION_AUTHORITY_REQUIRES_REVIEWED_FRESH_HOLDOUT_CONFIRMATION`

The fixed request therefore returns
`NO_CODE_CURRENT_PHASE6_AUTHORITY_REQUIRED` and does not acquire SportyBet
events or attempt provider execution. This is an internal reviewed-authority
blocker, not a factory/configuration error. Creating candidates from the
research-only shadow prediction would be an authority escalation and is
forbidden.

Consequently:

`REAL_CURRENT_SPORTYBET_END_TO_END_STATUS = NOT_RUN_CURRENT_PHASE6_AUTHORITY_UNAVAILABLE`

The v3 downstream chain and execution proof are structurally ready for exact
source-issued current Phase 6 candidates once that separate reviewed boundary
exists. The request service must then compose that issuer; it must not accept
manual candidate/native input.

## Safety

All new records retain `wager_placed=false`. Price-all v3 cannot route;
Router v3 cannot optimize a portfolio; Portfolio v3 cannot execute SportyBet;
the execution boundary can create only an anonymous share code and cannot log
in, stake, or bet.
