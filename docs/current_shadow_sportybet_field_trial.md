# Current ATHENA -> SportyBet research shadow field trial

## Purpose

This lane exists so ATHENA can collect prospective real-world decision evidence while the formal production model/Phase 6 promotion gate remains closed. It is intentionally separate from `current_sportybet_accumulator_request.py`; the production request continues to return `NO_CODE_CURRENT_PHASE6_AUTHORITY_REQUIRED` until the reviewed promotion evidence exists.

The shadow lane is not a way to relabel research probabilities as production probabilities. It is a research field trial with explicit source replay, current-provider pricing, first-class `NO_BET`, portfolio shortfall, and optional anonymous SportyBet share-code verification. It never logs in, touches a wallet, submits a stake, or places a wager.

## Canonical source chain

A research decision is admitted only when all of the following can be re-proved:

1. `CurrentLatestDurableFreshHistoryHandoff` proves the latest applicable successful PR151 archive and a complete current durable fresh-history prefix.
2. The exact current shadow row is `SEALED_COMPLETE_CASE` and retains the reviewed PR149 calibrated home/away expected-goals rates.
3. `CurrentDirectProviderCanonicalMarketMappingRebind` is replayed from its retained PR251/legacy reviewed sources.
4. The complete-current shadow handoff and the PR252 mapping share the exact same FotMob capture manifest SHA-256 and raw SHA-256 ancestry.
5. The exact retained current SportyBet event-detail inventory is replayed and equals the PR252 event/inventory/manifest/raw identity.

The execution-capable package adds another boundary: `VerifiedResearchDecisionSource` and `VerifiedResearchShadowPortfolio` are builder-only objects that retain those exact source objects and rebuild every decision and the portfolio before the canonical share-code wrapper can perform network work.

## Initial market surface

PR258 deliberately starts with exact reviewed `TOTAL_GOALS` half-goal partitions only. The normal path remains exact PR252-mapped semantics: both Over and Under sides must retain the same reviewed provider market ID and exact specifier, both sides must remain current/bookable, and the retained current event inventory must reproduce the same provider IDs and labels.

The real-provider proof established one current provider display-label change on native market ID `18`: the frozen reviewed source label is `Total Goals`, while the current SportyBet label is `Over/Under`. Frozen PR252 is not changed and continues to reject that label drift. PR258 adds one research-only reviewed reconciliation policy, `PR258_REVIEWED_MARKET18_TOTAL_GOALS_TO_OVER_UNDER_EXACT_NATIVE_ID_SPECIFIER_OUTCOME_LABEL_V1`, which may admit the renamed current label only when all of the following remain exact:

- PR252 source replay succeeds and the row is explicitly audited as `CURRENT_PROVIDER_LABEL_DRIFT_REJECTED`;
- native market ID is exactly `18`;
- reviewed market label is exactly `Total Goals` and current market label is exactly `Over/Under`;
- native outcome ID and exact specifier are unchanged;
- current outcome label exactly equals the reviewed outcome label;
- canonical market remains `TOTAL_GOALS`, canonical outcome remains Over or Under, and the canonical line is the exact half-line encoded by the specifier;
- the retained current inventory SHA-256 is exactly the inventory bound by PR252;
- the exact provider-native `(market ID, specifier, outcome ID)` still exists in that retained inventory and is bookable; and
- an exact Over/Under two-way pair exists for the same market ID, specifier, and line.

This is not a general `Total Goals`/`Over/Under` alias. `Over/Under` on another native market ID is not admitted, outcome-label drift is not admitted, cross-line substitution is not admitted, and arbitrary current provider markets are not promoted into the research surface.

No arbitrary SportyBet Total Goals line is scanned into the research surface. No fuzzy match, cross-line generalization, or "close enough" provider label is accepted merely to increase coverage. Unreviewed current provider markets can exist in the raw event response without becoming ATHENA research opportunities.

For an admitted two-way Total Goals partition, the lane uses the normalized independent-Poisson `ScoreMatrix` built from the exact sealed PR149 `calibrated_home` and `calibrated_away` rates. Current SportyBet decimal odds are de-vigged only within that exact two-way provider partition. The research value record is:

- event probability = ScoreMatrix Over/Under probability for the exact reviewed line;
- fair probability = proportional de-vig of the exact current Over/Under pair;
- robust edge = event probability - fair probability;
- net EV = event probability x decimal odds - 1.

These are research values. They do not mint a production `CalibratedValueCandidate` or production Phase 6 authority.

## Research routing

The research Router preserves the frozen reviewed Router thresholds rather than inventing easier shadow thresholds:

- event probability must be at least 0.55;
- net EV must be strictly positive;
- robust net EV must be strictly positive;
- robust edge must be strictly positive.

At most one eligible Total Goals opportunity is selected per fixture. If none survives, `NO_BET` is the correct research result. Source evidence older than 900 seconds, future-dated evidence, non-prematch/non-bookable events, and fixtures at or inside the exact 120-second kickoff boundary fail closed.

## Research portfolio

The portfolio keeps the frozen Portfolio-v2 exposure and fragility policy:

- maximum team appearances: 1;
- competition concentration share: 40%, with the reviewed minimum cap behavior;
- market-family concentration share: 50%, with the reviewed minimum cap behavior;
- fragile share: 30%, with the reviewed minimum cap behavior;
- non-fragile reference thresholds remain robust EV >= 0.02 and survival >= 0.60.

The requested leg count is a target, never a requirement. The optimizer rechecks chronology, current quote age, and the exact 120-second kickoff boundary at portfolio time. Rejected selected-fixture candidates are retained as explicit exclusions. Qualified but unselected opportunities are retained as reserves.

Because the initial PR258 surface contains only the Total Goals market family, the frozen 50% market-family cap can itself create a large shortfall. For example, a target of 20 cannot be padded with 20 Total Goals legs merely to satisfy the request; at most 10 such legs can survive that cap. Broader leg counts require separately reviewed additional market surfaces, not weaker concentration rules.

## Canonical anonymous share-code gate

The canonical network-capable entry point is `create_verified_current_shadow_sportybet_share_code()` in `domain/current_shadow_sportybet_verified_share_code.py`. It accepts only `VerifiedResearchShadowPortfolio` and replays every retained decision source and portfolio before delegating to the transport boundary.

For each selected research leg the transport then:

1. rechecks the original priced quote age and kickoff lead at wall-clock transport time;
2. sends only semantic intent to the existing SportyBet semantic bridge: event ID, home/away team, the exact current reviewed market label, outcome name, and exact specifier;
3. does not supply provider market/outcome IDs or odds to semantic resolution;
4. requires the freshly resolved SportyBet market ID, outcome ID, labels, specifier, and decimal odds to equal the exact values that the research field trial priced;
5. if odds changed, returns `RESEARCH_NO_CODE_REPRICE_REQUIRED` before create;
6. if native identity or semantics changed, returns `RESEARCH_NO_CODE_PROVIDER_CHANGED_REBIND_REQUIRED` before create;
7. rechecks quote age and kickoff lead again immediately after semantic resolution and immediately before create;
8. only after those gates calls the existing anonymous SportyBet `create -> reload` share transport;
9. requires zero unavailable outcomes, exact selection counts, exact create/reload native identity, semantic equality, specifier equality, and exact odds equality; and
10. exposes a share code only after the whole round trip verifies.

If the research portfolio has selected legs but preserves a target-size shortfall, a code may still be verified with `RESEARCH_SHADOW_SHARE_CODE_VERIFIED_WITH_SHORTFALL`. No extra leg is invented or substituted. If there are no qualified legs, no provider network request is needed and no code is produced.

## Safety and authority

True authority in this lane is deliberately limited to reviewed research evidence, research value/routing/portfolio construction, exact source replay, and anonymous share-code verification. All of the following remain false throughout PR258:

- production model authority;
- production probability authority;
- Phase 6 authority;
- production Price-all authority;
- production Router authority;
- production Portfolio authority;
- production selection authority;
- production SportyBet execution authority;
- login/cookie/wallet authority;
- staking authority;
- BET authority;
- wager placed.

The reviewed market-18 display-label reconciliation does not change any of those authority flags and does not mutate frozen PR252. A share code is therefore a prospective research artifact. It can be recorded with its exact source/model/quote/decision/portfolio/transport identities and later settled for learning, but it is not evidence that ATHENA's production model has been promoted.

## Current limitations and next reviewed expansions

The first implementation intentionally covers only exact reviewed Total Goals half-lines, including only the narrowly reviewed market-18 `Total Goals` -> `Over/Under` display-label rename described above. Adding 1X2, BTTS, double chance, DNB, Asian Handicap, early-payout products, other provider label changes, or specialist semantics must preserve their own reviewed mapping and settlement rules. In particular, DNB/AH require settlement-aware expected value, and early-payout markets require their reviewed provider promotion-settlement evidence; they must not be squeezed into the simple two-way Total Goals path.

The next useful expansion is therefore coverage, not relaxed validation: add separately reviewed current market surfaces and exact probability/settlement adapters, then measure prospective shadow results by frozen artifact identity. Production promotion remains controlled by the formal untouched holdout and reviewed governance gates.
