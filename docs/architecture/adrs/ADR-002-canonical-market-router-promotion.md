# ADR-002 — Canonical Market Router / Coherence Promotion

## Status

Accepted

## Context

The ATHENA Architecture Remediation Master Implementation Specification v2 requires P1.4 to promote the strongest current routing semantics without creating a fourth selector. The permanent canonical target is `domain.market_router`, but that path is already occupied by the supported Phase-8/v1 Router and still has live repository callers. Overwriting it in the ownership PR would conflate interface promotion with caller migration and would destroy the ability to prove replay compatibility.

P1.3 established `domain.price_all` as the canonical pricing boundary. The reviewed `domain.market_router_v3_current_provider` already owns exact Price-all-v3 reconstruction, source freshness rechecks, Fixture State context gating, frozen value thresholds, one-fixture selection and counterfactual recording. Current Shadow Router V3 additionally provides the reviewed comparable-confidence and quote-independent tie semantics needed by the P1.4 target contract.

Architecture Boundary CI protects the `domain.market_router*` family. A temporary public migration adapter therefore requires an explicit accepted ADR instead of bypassing the guardrail with an unrelated module name.

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

## No second selector

This ADR does not approve a standalone `market_coherence_engine`, another Router generation, or a fourth selection authority. Coherence grouping is diagnostic policy inside `domain.market_router_canonical_adapter`; global selection remains a single deterministic Router decision.

The existing `domain.market_router`, `domain.market_router_v2_direct_provider`, `domain.market_router_v3_current_provider`, and Current Shadow Router remain historical/transitional dependencies until separately sequenced caller migration and retirement evidence exist. This ADR grants no deletion authority.

## Authority boundary

The adapter may consume canonical Price-all, reconstruct source Router-v3 evidence, recheck source freshness, route one fixture, group coherence relationships, select at most one market, and record counterfactuals.

It may not generate football probabilities, calibrate models, recompute Price-all value, promote models, optimize a cross-fixture portfolio, construct a share code, execute SportyBet actions, access login/cookies/wallet state, calculate stakes, or place a wager.

Current Shadow remains research-only. P1.4 does not promote it to MAIN or production authority.

## Existing v1 name conflict

`domain.market_router` remains unchanged in P1.4. Its current callers must migrate in later bounded work before the permanent canonical name can be claimed. After caller migration, a dedicated rename/retirement PR may move the canonical adapter contract to `domain.market_router` and remove this temporary coexistence exception only when runtime reachability and preserved evidence permit it.

## Alternatives considered

Overwriting `domain.market_router` now was rejected because supported v1 callers still depend on it and the controlling specification explicitly requires resolving the name conflict before final canonical naming.

Creating `domain.market_coherence_engine_v1` was rejected because the specification requires coherence inside or immediately adjacent to the canonical Router and forbids another selection authority.

Copying Router-v3 source/value formulas into a new implementation was rejected because P1.4 is an ownership/interface PR. Exact source/freshness/value semantics remain delegated and replay-auditable.

Retaining Router-v3 quote age or quote-derived opportunity identity as the final tie authority was rejected because P1.4 requires quote-independent tie-breaking where prediction-first/comparable-confidence ranking applies.

## Replay and exit gate

P1.4 is acceptable only when replay tests prove the canonical adapter preserves Router-v3 decisions on ordinary reviewed corpus cases, including successful selection and fail-closed NO_BET paths, while explicit adversarial tests prove the newly canonicalized comparable-confidence, quote-independent tie and logical-coherence semantics.

No live provider acquisition or Current Shadow execution is required for this interface proof.

## Rollback / revisit trigger

If exact-head hosted tests fail, ordinary replay diverges from Router v3 without an explicit P1.4 semantic reason, source-v3 rejection can be upgraded, quote data regains tie authority, coherence creates a second selector, or any downstream authority expands, revert P1.4.

Revisit this ADR when old `domain.market_router` v1 callers have migrated and a dedicated PR can claim the permanent canonical module name without destroying supported behavior or evidence.
