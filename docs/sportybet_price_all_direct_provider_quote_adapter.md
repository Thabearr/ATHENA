# SportyBet direct-provider Price-all quote source adapter

## Purpose

PR #247 is the explicit source adapter required after the reviewed direct current SportyBet evidence boundary merged in PR #246.

PR #246 can issue an exact `SportyBetLiveMappedQuoteBundle` from ATHENA's reviewed public anonymous SportyBet FactsCenter event read. That bundle proves which provider-native prices ATHENA observed, preserves the exact raw/manifest ancestry, and rebinds those current native identities to an existing reviewed canonical market mapping.

The existing Phase 7 Price-all v1 contract cannot consume that evidence honestly without another boundary. Phase 7 v1 is frozen to `SportyBetUserControlledNativeInventory` produced from user-controlled SportyBet Lite HTML evidence with `USER_ATTESTED_NOT_PROVIDER_TIMESTAMP` observation authority.

This adapter therefore creates a **new direct-provider quote-source representation** without changing or reinterpreting Phase 7 v1.

## Source requirement

The only admissible input is an exact verified PR #246 bundle with:

- dataset `athena-sportybet-live-mapped-quote-bundle-v1`;
- status `CURRENT_DIRECT_PROVIDER_ODDS_EVIDENCE_VERIFIED`;
- proof mode `LIVE_CURRENT`;
- direct-provider observation authority `ATHENA_DIRECT_PROVIDER_RESPONSE_COMPLETION_NOT_PROVIDER_QUOTE_TIMESTAMP`;
- exact reviewed canonical mapping rebind;
- `current_observation_freshness_proven = true` at the source bundle's issuance time;
- `price_all = false` and `bet = false` at the source boundary.

A deterministic `REPLAY_AS_OF` bundle is intentionally rejected by this current-source adapter. Replay remains useful evidence, but it cannot be relabelled as a live-current acquisition path.

Before adaptation, the complete PR #246 bundle is reconstructed from its retained evidence bytes, mapping, inventory and paths by `verify_mapped_quote_bundle()`.

## What is preserved

Each adapted quote preserves:

- FotMob fixture identity;
- SportyBet event identity;
- exact provider market ID;
- exact provider specifier;
- exact provider outcome ID;
- canonical market/outcome/line identity;
- exact live inventory SHA-256;
- exact PR #246 source bundle SHA-256;
- exact event manifest SHA-256;
- exact raw provider response SHA-256;
- exact reviewed canonical mapping SHA-256;
- exact fixture-reconciliation receipt SHA-256;
- ATHENA response-completion observation time and its narrow authority;
- exact current provider odds observed in the PR #246 response;
- reviewed settlement-equivalence authority;
- null provider-native quote timestamp;
- null provider snapshot identity.

The adapter does not reuse the old odds contained in the original mapping evidence. The current price is still the direct-provider price supplied by PR #246.

## Freshness semantics

`LIVE_CURRENT` proves that PR #246 captured and issued the source under its frozen live-current freshness policy at issuance time. This adapter does **not** invent a second observation time and does not claim that the quote remains current forever.

It preserves both the source `observed_at` and source `evaluation_time`. A future Price-all v2 consumer must evaluate quote age again against its own frozen evaluation time and freshness policy.

That rule is frozen in the adapter contract as:

`PRESERVE_SOURCE_OBSERVED_AT_AND_LIVE_ISSUANCE_PROOF_PRICE_ALL_MUST_RECHECK_AGE`

## Phase 7 v1 remains unchanged

The existing Phase 7 v1 contract SHA-256 remains:

`1fb0a6c891adccd76b4864a6197e55d22154176a4191f57ce92cde13501535aa`

This PR does not modify `_price_all_contracts.py`, does not add a second constructor to the v1 `SportyBetExactQuote`, and does not feed direct-provider evidence into `price_all_candidates()`.

The adapter explicitly records:

`legacy_price_all_v1_consumption_authorized = false`

That is deliberate. Direct FactsCenter ancestry and user-controlled Lite HTML ancestry are different evidence contracts and must not be collapsed merely because they expose similar provider IDs and odds.

## Empty current quote sets

A verified current event may legitimately contain none of the previously reviewed mapped selections, or a mapped selection may currently be unavailable. PR #246 records those cases as mapping-audit dispositions.

The adapter preserves those audit rows and permits an empty quote tuple. It never invents a replacement market or outcome to avoid an empty result. A future Price-all consumer can therefore return an explicit unpriced state rather than silently substituting another quote.

## Tamper resistance

Adapted quote and quote-source objects are builder-only. Verification rebuilds the complete adapter output from the retained exact PR #246 source bundle and compares the deterministic representation.

Changing a quote, source hash, status, authority flag, or ancestry field without changing the exact verified source therefore fails reconstruction.

## Authority boundary

A successful PR #247 adapter output may prove only that an exact reviewed PR #246 direct-provider quote bundle has been transformed into a dedicated, source-qualified representation suitable for a future Price-all v2 contract.

It does **not** grant:

- Phase 7 v1 consumption authority;
- Price-all value computation;
- de-vig or EV authority;
- Market Router authority;
- final fixture-market selection;
- Accumulator Optimizer authority;
- SportyBet code generation or execution;
- staking, wallet, or wager authority;
- `BET`.

The exact next boundary is:

`PRICE_ALL_V2_DIRECT_PROVIDER_QUOTE_CONSUMPTION_REQUIRED`

That next boundary must version the Price-all quote-source contract explicitly, preserve the legacy v1 identity for historical reproducibility, recheck direct quote age at Price-all evaluation time, and only then allow the existing settlement-aware pricing mathematics to consume this direct-provider source.
