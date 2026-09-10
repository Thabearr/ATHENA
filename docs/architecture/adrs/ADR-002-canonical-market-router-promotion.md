# ADR-002 — Canonical Market Router / Coherence Promotion

## Status

Accepted

## Context

The ATHENA Architecture Remediation Master Implementation Specification v2 requires P1.4 to promote the strongest current routing semantics without creating a fourth selector. The permanent canonical target is `domain.market_router`, but that path is already occupied by the supported Phase-8/v1 Router and still has live repository callers. Overwriting it in the ownership PR would conflate interface promotion with caller migration and would destroy the ability to prove replay compatibility.

P1.3 established `domain.price_all` as the canonical pricing boundary. The reviewed `domain.market_router_v3_current_provider` already owns exact Price-all-v3 reconstruction, source freshness rechecks, Fixture State context gating, frozen value thresholds, one-fixture selection and counterfactual recording. Current Shadow Router V3 additionally provides the reviewed comparable-confidence and quote-independent tie semantics needed by the P1.4 target contract.

Architecture Boundary CI protects the `domain.market_router*` family. A temporary public migration adapter therefore requires an explicit accepted ADR instead of bypassing the guardrail with an unrelated module name.

## Evidence

Controlling design evidence is ATHENA Architecture Remediation Master Implementation Specification v2, Part V / 54. It requires a canonical Router/coherence interface, preservation of current value gates/comparable-confidence/counterfactual semantics, quote-independent tie-breaking, explicit overlap/coherence tests, and Router-v3 replay parity. It also requires the existing `domain.market_router` v1 name conflict to be resolved before the final canonical rename.

Live repository evidence at P1.4 start is main `78a2531847923573917b178821322e5f8e5e4a7c`. On that exact state, `domain.market_router` is still imported by supported v1 callers including `domain.accumulator_optimizer` and `scripts.evaluate_market_router`, while `domain.market_router_v3_current_provider` remains the reviewed current-provider source/value/context Router. Its frozen contract SHA-256 is `61a90a29495399668e19ae4a149527abea98c172d7bdacf1a1b521776b4d771a`.

The reviewed Current Shadow source-aligned Router V3 establishes comparable confidence as scalar event probability, DNB settlement survival `WIN + PUSH`, and Asian Handicap settlement survival `WIN + HALF_WIN + PUSH`, with a `0.55` confidence floor and a `1.09` decimal-odds eligibility floor. Its final prediction-first tie identity is canonical market/outcome/line rather than quote identity. P1.4 adopts those semantics without importing Current Shadow orchestration or production authority.

## Decision

Approve exactly `domain.market_router_canonical_adapter` as the temporary canonical Router/coherence migration interface for P1.4.

The adapter must:

- consume canonical `domain.price_all.PriceAllEvaluation`;
- delegate exact source reconstruction, source freshness, Fixture State context and frozen value eligibility to `domain.market_router_v3_current_provider`;
- never upgrade an opportunity rejected by source Router v3;
- require comparable model-derived prediction confidence, using scalar event probability, DNB `WIN + PUSH`, and Asian Handicap `WIN + HALF_WIN + PUSH` semantics;
- preserve the reviewed decimal-odds floor of `1.09` as eligibility only, never as ranking authority;
- rank eligible opportunities by settlement-aware robust net expected value, then comparable prediction confidence, then quote-independent canonical prediction identity;
- fail closed when two eligible priced opportunities resolve to the same canonical prediction identity;
- record selected opportunity, runner-up and strongest counterfactual;
- produce explicit logical-overlap/coherence diagnostics inside the same Router authority boundary; and
- default to at most one selected market per fixture because P1.4 does not authorize same-game-combination construction.

The coherence contract is conservative. It may group only exact logical relationships grounded in canonical market settlement semantics: shared regulation-result atoms, shared Over-2.5 atoms, shared BTTS-NO atoms, and nested Total Goals Over/Under lines. It must not infer correlation from market names or grant joint-probability authority to DNB, Asian Handicap, Win Either Half, or early-payout markets without reviewed evidence.

This ADR does not approve a standalone `market_coherence_engine`, another Router generation, or a fourth selection authority. Coherence grouping is diagnostic policy inside `domain.market_router_canonical_adapter`; global selection remains a single deterministic Router decision.

## Alternatives considered

Overwriting `domain.market_router` now was rejected because supported v1 callers still depend on it and the controlling specification explicitly requires resolving the name conflict before final canonical naming.

Creating `domain.market_coherence_engine_v1` was rejected because the specification requires coherence inside or immediately adjacent to the canonical Router and forbids another selection authority.

Copying Router-v3 source/value formulas into a new implementation was rejected because P1.4 is an ownership/interface PR. Exact source/freshness/value semantics remain delegated and replay-auditable.

Retaining Router-v3 quote age or quote-derived opportunity identity as the final tie authority was rejected because P1.4 requires quote-independent tie-breaking where prediction-first/comparable-confidence ranking applies.

Bypassing the protected `domain.market_router*` family with an unrelated adapter name was rejected because it would evade Architecture Boundary CI rather than document the temporary migration state.

## Consequences

For a bounded migration period, ATHENA retains the supported v1/v2/v3 Router modules while adding one explicit canonical migration adapter. This coexistence is recorded and does not imply multiple promoted selection authorities.

The adapter may consume canonical Price-all, reconstruct source Router-v3 evidence, recheck source freshness, route one fixture, group coherence relationships, select at most one market, and record counterfactuals. It may not generate football probabilities, calibrate models, recompute Price-all value, promote models, optimize a cross-fixture portfolio, construct a share code, execute SportyBet actions, access login/cookies/wallet state, calculate stakes, or place a wager.

Current Shadow remains research-only. P1.4 does not promote it to MAIN or production authority. Existing Router modules receive no deletion disposition from this ADR.

## Migration plan

P1.4 introduces and proves `domain.market_router_canonical_adapter` while leaving `domain.market_router` v1 and all current callers unchanged. The adapter consumes the P1.3 canonical Price-all boundary and delegates reviewed source/value/context reconstruction to Router v3.

Subsequent bounded migration work may move supported Router consumers to the canonical contract. Only after the old `domain.market_router` v1 callers have migrated and runtime reachability/evidence gates are satisfied may a dedicated PR claim the permanent `domain.market_router` name and remove the temporary ADR exception. That rename/retirement step is not authorized by P1.4.

P1.5 remains separately responsible for canonical portfolio ownership; P1.4 must not change portfolio caps or cross-fixture selection.

P1.4 is acceptable only when replay tests prove the canonical adapter preserves Router-v3 decisions on ordinary reviewed corpus cases, including successful selection and fail-closed NO_BET paths, while explicit adversarial tests prove comparable-confidence, quote-independent tie and logical-coherence semantics. No live provider acquisition or Current Shadow execution is required for this interface proof.

## Rollback / revisit trigger

If exact-head hosted tests fail, ordinary replay diverges from Router v3 without an explicit P1.4 semantic reason, source-v3 rejection can be upgraded, quote data regains tie authority, coherence creates a second selector, or any downstream authority expands, revert P1.4.

Revisit this ADR when old `domain.market_router` v1 callers have migrated and a dedicated PR can claim the permanent canonical module name without destroying supported behavior or evidence.
