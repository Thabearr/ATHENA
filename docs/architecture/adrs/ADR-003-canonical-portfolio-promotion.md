# ADR-003 — Canonical Portfolio Promotion

## Status

Accepted

## Context

ATHENA Architecture Remediation Master Implementation Specification v2 requires P1.5 to promote the reviewed cross-fixture Portfolio-v3 selection and truthful-shortfall behavior behind one unversioned canonical optimizer interface. The public request semantic is `target_legs`: an integer maximum desired leg count from 1 through 50. It is not a quota and it is distinct from any future `target_total_odds` objective.

Architecture Boundary CI protects the `domain.portfolio_optimizer*` family. The current repository already contains grandfathered v2, v3 and Current Shadow Portfolio implementations. Creating the canonical public owner therefore requires an explicit accepted ADR rather than bypassing or weakening the guardrail.

P1.4 established the canonical Router/coherence migration boundary at `domain.market_router_canonical_adapter`. P1.5 must consume that verified Router contract while preserving exact provider/source ancestry and the reviewed Portfolio-v3 exposure, freshness, cap, reserve and shortfall semantics. It must not reinterpret probabilities, invent candidates, lower Router eligibility thresholds, introduce a Kelly objective, or optimize to total odds.

## Evidence

Controlling design evidence is ATHENA Architecture Remediation Master Implementation Specification v2, Part V / 55. P1.5 requires a canonical Portfolio interface using `target_legs`, preservation of team, competition, market-family and fragility caps, reserve-leg recording, truthful shortfall, and replay parity with Portfolio v3. Its output is a `SelectedPortfolio` consumed by later delivery services. Kelly and `target_total_odds` objectives are explicitly out of scope.

Live repository evidence at P1.5 start is main `ae5ee13cde4b4a51a5c23499de8dab2bbb9c5d11`. On that exact state, the canonical P1.4 Router contract SHA-256 is `85b4b5c712154f7d4708eb53e9cadfcb7c65dc21bdb12cd94cf1b8cd48795e32`. The reviewed current-provider Portfolio-v3 contract SHA-256 is `4dc8be4e0a9f607b6c0804048bb326c0aa342d37fe540abbcd3e1b3a5f6a6dad` and its optimization policy is `PRESERVE_FROZEN_PORTFOLIO_V2_CAPS_MARGINAL_ORDER_AND_SHORTFALL_V1`.

The reviewed Portfolio-v3 policy retains maximum team appearances, competition-share caps, market-family-share caps and fragility caps; records reserves with binding reasons; rechecks freshness at Portfolio time; treats requested size as a target rather than a requirement; and exposes `NO_VALIDATED_JOINT_CORRELATION_MODEL_V1` rather than fabricating statistical dependence. Current RunRequest semantics establish `target_legs` bounds 1..50 and keep `target_total_odds` separate.

## Decision

Approve exactly `domain.portfolio_optimizer` as the canonical P1.5 Portfolio ownership interface for responsibility `portfolio_optimizer`.

The canonical interface must:

- consume exact verified P1.4 canonical Router decisions;
- preserve exact source Router-v3 and current-provider reconciliation ancestry needed by the reviewed Portfolio-v3 policy;
- expose `target_legs` as the only requested-size parameter, bounded 1..50;
- preserve Portfolio-v3 freshness behavior, team cap, competition cap, market-family cap, fragility cap, marginal ordering, settlement-survival handling, reserve-leg reasons and truthful shortfall;
- never invent a fixture-market candidate or upgrade a Router rejection;
- output immutable `SelectedPortfolio` evidence containing target, selected count, shortfall, reserves, exposure caps and binding cap diagnostics;
- retain the explicit no-validated-joint-dependence status and avoid claiming exact joint probability;
- keep combined decimal odds, where reported, diagnostic-only rather than an optimization target; and
- keep Kelly, target-total-odds optimization, share-code generation, SportyBet execution, login, cookies, wallet, staking and wager authority false.

P1.5 may delegate the frozen cap/marginal/reserve calculations to the reviewed Portfolio-v3 implementation during migration. That delegation is a temporary implementation seam, not permanent version-suffixed authority. Caller migration and later internalization/retirement remain separate reviewed work.

## Alternatives considered

Creating `domain.portfolio_optimizer_v4` was rejected because it would add another versioned public authority rather than establish the required unversioned canonical owner.

Reimplementing the v3 cap, marginal, reserve, survival or shortfall formulas inside a new module was rejected because P1.5 is an ownership/interface promotion PR and the exit gate requires replay equivalence, not a formula rewrite.

Using Current Shadow Portfolio as the canonical implementation was rejected for this PR because the controlling P1.5 requirement specifically promotes reviewed Portfolio-v3 behavior, while Current Shadow remains a research profile to be migrated in later P2 work.

Adding Kelly staking, a target-total-odds objective, minimum compounded-odds filling, or automatic threshold relaxation was rejected because each would change the requested-size/selection contract and is explicitly out of scope.

## Consequences

P1.5 creates one stable `domain.portfolio_optimizer` interface and `SelectedPortfolio` output for later delivery migration while retaining exact reconstruction back to reviewed source evidence. Existing Portfolio v2, Portfolio v3 and Current Shadow Portfolio modules remain present; this ADR grants no deletion or retirement authority.

Architecture Boundary CI continues to reject any additional public Portfolio authority lacking its own accepted exact ADR. P1.5 does not promote Current Shadow to MAIN, grant production authority, trigger provider acquisition, create a SportyBet share code, authenticate, access cookies or wallet state, calculate a stake, or place a wager.

## Migration plan

1. Establish `domain.portfolio_optimizer` and `SelectedPortfolio` with exact P1.4 Router consumption and replay coverage against Portfolio v3.
2. Keep existing v2, v3 and Current Shadow Portfolio callers unchanged during this ownership PR.
3. Migrate supported callers to the canonical interface in separately bounded, replay-tested PRs.
4. Re-run architecture reachability/runtime evidence after caller migration.
5. Consider retirement of superseded Portfolio generations only when live evidence proves they no longer own supported runtime responsibility; retirement requires its own reviewed mission.

P1.5 itself stops after the canonical interface is review-ready. It does not perform bulk caller migration or deletion.

## Rollback / revisit trigger

Revisit or roll back this ADR if canonical replay changes selected-leg identity or shortfall relative to the reviewed Portfolio-v3 policy for equivalent Router decisions; if P1.4 Router ancestry cannot be reconstructed exactly; if any exposure, freshness, reserve or fragility rule is weakened; if `target_legs` is treated as a quota; if odds/Kelly becomes selection authority; or if the canonical module gains delivery, staking or wager authority.

A later architectural redesign of Portfolio selection, dependence modeling, target-total-odds objectives or Kelly sizing requires separate evidence and change control. It must not be smuggled into this ADR's migration allowance.
