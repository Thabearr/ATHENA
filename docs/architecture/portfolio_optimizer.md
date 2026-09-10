# Canonical Portfolio Interface — P1.5

## Mission

P1.5 promotes ATHENA's reviewed cross-fixture Portfolio-v3 behavior behind the stable, unversioned `domain.portfolio_optimizer` interface. It is an ownership and contract migration, not a formula rewrite.

The controlling output is `SelectedPortfolio`. That object is the Portfolio evidence boundary that later delivery services consume.

## Input boundary

The canonical optimizer accepts exact P1.4 canonical `RouterDecision` values. Each decision is verified before Portfolio construction, and the retained source Router-v3 decision is replayed only to recover the exact current-provider reconciliation and source ancestry required by the already-reviewed Portfolio-v3 policy.

Portfolio never invents fixture-market candidates and never reinterprets football probabilities. A canonical Router `NO_BET` decision cannot become a Portfolio leg.

## `target_legs`

The public requested-size parameter is `target_legs`.

- minimum: 1
- maximum: 50
- semantic: maximum desired selected-leg count, not a quota

If fewer opportunities satisfy Router eligibility, Portfolio freshness and exposure constraints, the correct output is the smaller selected set plus truthful `shortfall`.

`target_total_odds` is not accepted by the P1.5 optimizer API. Combined decimal odds may appear in `SelectedPortfolio` only as a diagnostic product of the already-selected legs. It is not an optimization target.

Kelly sizing is also outside P1.5. No stake is calculated.

## Preserved Portfolio-v3 policy

P1.5 preserves the reviewed Portfolio-v3 policy through exact delegation of the existing policy helpers rather than copying or changing formulas. The preserved controls are:

- maximum team appearances;
- competition concentration share/cap;
- market-family concentration share/cap;
- fragility share/cap;
- Portfolio-time quote freshness and kickoff lead;
- settlement-aware survival handling for ordinary markets, Draw No Bet and Asian Handicap;
- marginal selection ordering;
- reserve ordering and reserve reasons;
- truthful shortfall.

The source policy remains `PRESERVE_FROZEN_PORTFOLIO_V2_CAPS_MARGINAL_ORDER_AND_SHORTFALL_V1` during this migration window.

## `SelectedPortfolio`

A canonical `SelectedPortfolio` records:

- exact canonical Portfolio contract identity;
- exact canonical Router contract identity;
- retained Portfolio-v3 contract identity;
- evaluation time and proof mode;
- `target_legs` and selected count;
- selected legs with Router/provider/source ancestry;
- reserve legs with exclusion reasons;
- per-fixture Router admission audit;
- optimization status and shortfall;
- exposure counts and all configured caps;
- the cap reasons that actually bound reserve candidates;
- settlement-survival baseline;
- combined decimal-odds product as diagnostic-only evidence;
- explicit dependence status;
- explicit authority booleans.

The object is immutable/builder-only and can be reconstructed from retained verified Router evidence. Reconstruction must reproduce the same canonical payload.

## Binding-cap visibility

The exposure summary always records the complete cap configuration and selected exposure counts. `binding_caps` additionally records any team, competition, market-family or fragility constraint that actually excluded a reserve candidate.

This makes a shortfall explainable rather than merely reporting a selected count.

## Dependence semantics

P1.5 does not fabricate a statistical joint-dependence model. It preserves:

`NO_VALIDATED_JOINT_CORRELATION_MODEL_V1`

`expected_slip_survival`, when present, is the existing independence-baseline diagnostic over selected settlement-survival floors. `statistical_correlation_coefficients` remain absent/`None` until a separately validated dependence model exists.

## Replay compatibility gate

P1.5 is acceptable only when the replay corpus demonstrates that the canonical adapter preserves the reviewed Portfolio-v3 selected legs and shortfall for equivalent Router-v3 decisions. Tests also cover `NO_BET`, stale Portfolio-time evidence, cap/reserve behavior, exact reconstruction, and the explicit no-padding target contract.

The canonical P1.4 Router may differ from source Router-v3 only where P1.4 explicitly introduced reviewed comparable-confidence/quote-independent routing semantics. In that case, P1.5 builds the leg from the exact source-v3 opportunity corresponding to the canonical selection; it does not silently fall back to the older source-v3 selected opportunity.

## Architecture Boundary CI

`domain.portfolio_optimizer` is inside the protected Portfolio public-authority family. ADR-003 approves exactly this canonical owner. The frozen baseline family list is not rewritten and the guardrail remains active against any additional `portfolio_optimizer_v4`, rewrite, or equivalent public authority without a separately accepted ADR.

## Authority and safety

P1.5 grants Portfolio-construction authority only inside this canonical contract. It does not grant or trigger:

- football probability generation or calibration;
- Price-all value computation;
- market routing;
- target-total-odds optimization;
- Kelly optimization or staking;
- statistical joint-dependence authority;
- provider acquisition;
- Current Shadow execution;
- SportyBet share-code creation/reload;
- login or cookies;
- wallet access;
- wager placement.

All such authority fields are explicitly false in `SelectedPortfolio`. P1.6 owns the later non-wager SportyBet share-code delivery extraction.

## Migration / retirement status

Portfolio v2, Portfolio v3 and Current Shadow Portfolio remain in the repository after P1.5. Their existence is transitional architecture evidence and does not grant permanent ownership, but P1.5 does not delete, rename, retire or reclassify them. Caller migration and evidence-backed retirement are separate later remediation work.
