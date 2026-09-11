# Shared Canonical Core (P2.0 / P2.1)

## Purpose

P2.0 extracted a pure, profile-aware composition boundary before either execution profile was migrated. `domain.canonical_core` resolves the five registered current-provider champions: provider market semantics, Price-All, Router, Portfolio, and SportyBet share-code transport.

P2.1 makes Current Shadow the first execution profile that is required to resolve that source-controlled shared core before it may proceed into provider acquisition or decision stages. The migration is ownership- and authority-preserving; it is not a football, pricing, routing, portfolio, provider, or delivery-policy rewrite.

## Pure core, not an orchestrator

The core consumes an existing `AuthorityManifest`, source-controlled component registry, and already-acquired evidence. It does not acquire a provider, parse a command, schedule a workflow, write Current Shadow checkpoints, supervise timeouts, persist a run receipt, run football models, or choose a challenger by filename. Main and Shadow orchestration remain outside this module.

## Provider semantics promotion

`domain.provider_market_semantics` is the unversioned façade for the reviewed `domain.current_sportybet_semantic_registry`. It delegates exact native IDs, labels, specifiers, settlement classes, evidence freshness, and retained-source validation. Its contract also pins the delegated implementation's Git filtered-blob identity, so a semantic-code edit cannot be accepted merely because its high-level vocabulary constants still match. It contains no second mapping table, no fuzzy matching, no pricing, routing, portfolio, delivery, or provider acquisition authority.

## Authority resolution

`resolve_canonical_core()` accepts the existing `domain.run_contracts.AuthorityManifest`, a regime, and schema version. Its public authority path always reloads the reviewed source-controlled registry; it accepts no caller-provided in-memory registry. Private test-only helpers may exercise malformed registry fixtures, but cannot become a public authority path. Each resolved record is checked against the live component contract and source Git blob before bindings are returned.

The current `CURRENT_SPORTYBET_PROVIDER` records are `SHADOW`-eligible only and have `main_authority=false`. A `MAIN` resolution therefore fails closed. SHADOW eligibility is not production promotion and does not create an automatic promotion path.

## Reviewed P2.0 identities

The P2.0 provider-semantics contract is `737a463bd26a5333a45fe50aef21fd3b4a76ec3395041e56f3a105f32bd0f830`. It pins delegated implementation blob `646bf93549d0d859f00e1d42ba72aaa17a84a6e7` and façade artifact blob `46eaf64b6704e1b7b47123a9a182346e0403cbe6`. The shared-core contract is `af4a73f8852893e7391ae85bac092105d305fa5b9e77af273809fcdcb3dc4c4a`; the corresponding five-record registry canonical SHA-256 at the P2.0 merge boundary is `7569dea91ba4c690a1121ea252e51566a7e3cacd80e1120774bd706d2b4eab03`.

P2.1 does not edit those five canonical owner records or owner modules, so their contract/artifact identities remain the P2.0 reviewed identities. The Current Shadow migration adapter is not added as a sixth authority record; it is a profile-specific compatibility seam into the existing five-owner core.

## Source-controlled compatibility aliases

P2.1 records the three retained Current Shadow decision-wrapper module identities as one-way component aliases in the existing source-controlled P1.7 registry:

- `domain.current_shadow_all_market_price_all` -> `domain.price_all`;
- `domain.current_shadow_all_market_router` -> `domain.market_router_canonical_adapter`;
- `domain.current_shadow_all_market_portfolio` -> `domain.portfolio_optimizer`.

These aliases are not authority records, do not create additional champions, and do not alter profile eligibility, promotion state, contract identity, artifact identity, or MAIN authority. `domain.current_shadow_canonical_core_adapter` requires every alias to resolve to the exact same `ComponentAuthorityRecord` already selected by `domain.canonical_core` before the retained compatibility implementation may execute. A missing, retargeted, or shadowing alias therefore fails closed instead of allowing a legacy wrapper to become an independent authority path.

The alias layer is temporary migration metadata. It makes the retained implementation/evidence dependency explicit while preserving the P1.7 rule that aliases can only point into reviewed registry authority and cannot decide authority themselves.

## Stage separation

The binding exposes separate replay-stage adapters. It calls the existing canonical interfaces only: `domain.price_all`, `domain.market_router_canonical_adapter`, `domain.portfolio_optimizer`, and `domain.sportybet_share_code`. Delivery replay requires explicit offline semantic and transport callables, so it cannot reach real provider bridges. The stage outputs remain their existing canonical types.

## P2.1 Current Shadow migration

`domain.current_shadow_all_market_runner` no longer directly imports the three profile-specific Price-All, Router, and Portfolio modules. It imports only `domain.current_shadow_canonical_core_adapter` for those three module-shaped seams. The adapter resolves `domain.canonical_core` under an immutable SHADOW `AuthorityManifest`, verifies the exact source-controlled component IDs, and verifies the one-way wrapper aliases before any migrated decision responsibility may execute.

The runner resolves the five-component core before provider acquisition. If registry identity, component contract, Git artifact identity, compatibility-alias target, profile eligibility, or MAIN-authority state drifts, execution fails closed before a provider request is issued.

Current Shadow still carries reviewed profile-specific source/context and terminal receipt shapes. To keep P2.1 behavior-preserving, the adapter temporarily delegates those shapes to the existing Shadow implementation only after the corresponding canonical owner and source-controlled alias have both been proven. This is the transition window explicitly allowed by the v2 specification: the legacy wrappers are retained as implementation/evidence dependencies, but they are no longer the runner's directly imported ownership boundary and cannot independently establish authority. Existing bounded fresh-reprice and reconciliation monkeypatch seams are preserved.

P2.1 does **not** claim that the legacy payload classes have been deleted or that frozen v2/v3 dependencies are gone. Their differential removal remains later P3.2/P3.3 work. It also does not migrate MAIN.

## Behavioral contract

P2.1 must preserve the existing Current Shadow result semantics: same supported fixture/source acquisition, same Price-All/Router/Portfolio policy behavior, same deterministic selection ordering for identical inputs, same reserve handling, same truthful shortfall, same create/reload delivery semantics, and no padding of weak legs. The established 14-of-25 shortfall behavior remains a valid regression target rather than an instruction to force 25 legs.

Pre-merge proof remains synthetic/offline. The controlling v2 specification requires the bounded hosted Current Shadow execution after merge; that post-merge run is the operational checkpoint that proves the canonical stack active under real research orchestration. No provider acquisition or real share-code operation is required or authorized merely to make the P2.1 PR review-ready.

## Safety, formulas, and rollback

P2.1 changes no football, calibration, Price-All, Router, Portfolio, provider-market, or share-code mathematics. It grants no MAIN, login, cookie, wallet, staking, bet, or wager authority and grants no deletion authority. Current Shadow source acquisition remains a SHADOW orchestration responsibility outside the pure core.

Rollback is a source-controlled reversal of the runner import/compatibility migration plus the three one-way alias entries. Because the legacy wrappers remain retained during this transition, rollback requires no evidence deletion, no registry promotion/demotion, and no provider operation.
