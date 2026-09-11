# Shared Canonical Core (P2.0)

## Purpose

P2.0 extracts a pure, profile-aware composition boundary before either execution profile is migrated. `domain.canonical_core` resolves the five registered current-provider champions: provider market semantics, Price-All, Router, Portfolio, and SportyBet share-code transport.

## Pure core, not an orchestrator

The core consumes an existing `AuthorityManifest`, source-controlled component registry, and already-acquired evidence. It does not acquire a provider, parse a command, schedule a workflow, write Current Shadow checkpoints, supervise timeouts, persist a run receipt, run football models, or choose a challenger by filename. Main and Shadow orchestration remain outside this module.

## Provider semantics promotion

`domain.provider_market_semantics` is the unversioned façade for the reviewed `domain.current_sportybet_semantic_registry`. It delegates exact native IDs, labels, specifiers, settlement classes, evidence freshness, and retained-source validation. It contains no second mapping table, no fuzzy matching, no pricing, routing, portfolio, delivery, or provider acquisition authority.

## Authority resolution

`resolve_canonical_core()` accepts the existing `domain.run_contracts.AuthorityManifest`, a regime, schema version, and a `ComponentAuthorityRegistry`. It resolves exact champions rather than inferring authority from filenames or version suffixes. Each record is checked against the live component contract and source Git blob before bindings are returned.

The current `CURRENT_SPORTYBET_PROVIDER` records are `SHADOW`-eligible only and `main_authority=false`. A `MAIN` resolution therefore fails closed. SHADOW eligibility is not production promotion and does not create an automatic promotion path.

## Stage separation

The binding exposes separate replay-stage adapters. It calls the existing canonical interfaces only: `domain.price_all`, `domain.market_router_canonical_adapter`, `domain.portfolio_optimizer`, and `domain.sportybet_share_code`. Delivery replay requires explicit offline semantic and transport callables, so it cannot reach real provider bridges. The stage outputs remain their existing canonical types.

## P2.0 is not P2.1

Current Shadow still owns its orchestration and profile-specific stage wrappers in P2.0. No Current Shadow caller is migrated here; P2.1 is the dedicated migration. Existing versioned implementations and frozen dependency evidence remain until later differential-proof and rename work (including P3.2/P3.3).

## Safety, formulas, and rollback

This extraction changes no football, Price-All, Router, or Portfolio mathematics and creates no provider request, real share code, login, cookie, wallet, stake, or wager. It grants no deletion authority. Rollback is a source-controlled reversal of the new façade/core and its registry record; it does not require changing Current Shadow callers or deleting prior evidence.
