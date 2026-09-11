# Canonical SportyBet Share-Code Service (P1.6)

## Purpose

`domain.sportybet_share_code` is ATHENA's P1.6 canonical non-wager delivery boundary for anonymous SportyBet share-code creation and reload verification. It promotes the already reviewed semantic-resolution and direct create/reload behavior behind one reusable interface rather than creating a new browser or authenticated automation path.

The canonical input is a verified P1.5 `SelectedPortfolio` plus an exact `SportyBetProviderBinding` for every selected leg. Bindings are verification evidence, not caller selection authority: `build_provider_bindings()` derives them from the selected portfolio, and execution reconstructs the same set before any provider bridge can run.

## Canonical result contract

The service returns exactly one of:

- `VerifiedShareCode` when semantic resolution and provider create/reload reproduce the exact expected selection set; or
- `ShareCodeFailure` with a typed failure code and stage when the selected set cannot be safely verified.

A string code alone is never sufficient. Verification requires exact event, provider market/outcome identity, specifier, semantic names, odds, accepted counts and create/reload equality. Provider safety receipts must also prove login, cookies, wallet, stake and wager fields are all false.

A truthful portfolio shortfall does not forbid a research share code. If the canonical `SelectedPortfolio` requested 25 legs but contains 14 eligible legs with shortfall 11, those exact 14 may be create/reload verified and the resulting `VerifiedShareCode` retains `target_legs=25`, `selected_leg_count=14`, and `shortfall=11`. The service never pads the portfolio or lowers Router eligibility.

## Transport ownership and reuse

P1.6 deliberately reuses the reviewed implementation surfaces already present on `main`:

- `scripts.sportybet_semantic_share_bridge.resolve_live_intents()` for fresh semantic resolution from event/team/market/outcome/specifier intent; and
- `scripts.sportybet_direct_share_bridge.create_and_roundtrip()` for anonymous create/reload transport.

The canonical service reuses the reviewed verification helpers in `domain.current_sportybet_accumulator_execution` for semantic/native/odds equality and create/reload equality. It does not add Selenium, Playwright, browser automation, authentication, login, cookies, wallet access, staking or wagering.

Provider-native market/outcome IDs remain downstream verification facts. The bridge intent supplied to semantic resolution never contains caller-supplied native market IDs, outcome IDs, odds, a preselected slip or a wager.

## Freshness and failure semantics

Before provider semantic resolution, the service reconstructs the P1.5 portfolio and rechecks each selected leg against the exact retained Price-All freshness and kickoff-lead policy. LIVE_CURRENT delivery repeats that freshness check immediately before create/reload. A stale quote or insufficient kickoff lead returns typed `REPRICE_REQUIRED` and no code.

Provider semantic drift returns `PROVIDER_CHANGED`. A transport-level create/reload error returns `CREATE_RELOAD_FAILED`. A verified transport response that omits a usable share code or URL returns `VERIFIED_RESPONSE_INCOMPLETE`. A portfolio with zero selected legs returns `NO_SELECTED_LEGS`. Structural tampering or unreplayable canonical evidence raises `SportyBetShareCodeError` before provider transport.

`create_verified_share_code_as_of()` exists for deterministic replay and synthetic transport tests. It does not make historical provider state magically replayable; tests must provide synthetic/mock provider bridges. `create_verified_share_code()` is the LIVE_CURRENT anonymous provider-verification lane and is not exercised by the P1.6 remediation test run.

## Current Shadow migration seam

P1.6 changes `domain.current_shadow_all_market_runner` to import the canonical `domain.sportybet_share_code` delivery module. The canonical module exposes a temporary one-way compatibility entrypoint named `create_verified_shadow_all_market_share_code()` that delegates the already reviewed Current Shadow fresh-fallback delivery behavior and then enforces the canonical non-wager safety vocabulary.

This seam is intentionally temporary. Current Shadow still owns profile-specific Price-All/Router/Portfolio structures at this point; converting those profile-core objects to P1.3/P1.4/P1.5 canonical types belongs to the later P2 shared-core migration wave. The compatibility entrypoint cannot independently select, price, route or wager.

## `bookie_automator` disposition

P1.6 does **not** delete, deprecate or rewrite `workers/bookie_automator.py`. Current live reachability evidence still shows `api/export.py` importing `BookieAutomator`, and the P0 architecture inventory did not grant a delete disposition. The master doctrine remains promote -> migrate callers -> prove replacement -> retire. Any later retirement requires explicit reachability and migration evidence.

## Authority

The canonical service permits only selected-portfolio consumption, exact provider-binding verification, provider semantic verification, anonymous share-code generation and create/reload verification. It explicitly denies upstream source acquisition, browser automation, football probability generation, calibration, Price-All, routing, portfolio optimization, login, cookies, wallet, staking, betting and wagering.

## P1.6 exit evidence

The dedicated regression corpus includes a Run #231-equivalent synthetic fixture: target 25, selected 14, shortfall 11. It must return a `VerifiedShareCode` for exactly those 14 selections only after exact semantic/native/odds create/reload equality, with `wager_placed=false`.

Hosted CI is the required execution evidence for this remediation PR. No real provider acquisition, Current Shadow run, live share-code creation, login, wallet, stake or wager is required or authorized for P1.6 validation.
