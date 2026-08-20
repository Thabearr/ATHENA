# Real FotMob player-context team-strength handoff

## Boundary

PR #194 takes the exact real player-context semantic admission established by PR #193 and carries only the semantics actually supported by that exact observation into the PR #190 team-strength candidate schema.

The boundary is intentionally narrow. It is a feature-handoff proof, not an expected-goals adjustment and not a claim that the Thursday observation remains current for Saturday.

## Exact source ancestry

The public builder does not accept a caller-constructed PR #193 wrapper. It accepts only the five frozen PR #192 evidence byte streams and invokes the PR #193 builder again:

1. `campaign-receipt.json`;
2. `match-details/manifest.json`;
3. `match-details/response.json`;
4. `match-details/persisted-evidence-receipt.json`;
5. `match-details/structure-assessment.json`.

PR #193 therefore replays PR52/PR53 and re-establishes the exact `FOTMOB:5795367` semantic admission before any team-strength candidate is built.

The dedicated hosted proof downloads the exact successful PR #192 artifact:

- run `32410775191`;
- artifact `9422055017`;
- artifact digest `sha256:db5dc12b8863cbac15f210e018ddf0af9b9011a6ad8c3958a473a597254f44b5`;
- source head `46f76e8033d3d498131c6f893111b437b6b459a9`.

No new FotMob request occurs in this PR.

## What becomes a legal team-strength feature

Only the exact current unavailable-player completeness admitted by PR #193 crosses the boundary.

For the frozen observation:

- Nottingham Forest unavailable-player count = `1`;
- Leeds United unavailable-player count = `5`.

These become the only two PR #190 `AVAILABLE` feature resolutions:

- `home_unavailable_player_count`;
- `away_unavailable_player_count`.

The authoritative PR #194 wrapper sets `team_strength_feature_authorized = true` only for this exact replayed observation and exact candidate.

The nested PR #190 candidate itself remains all-false, as designed.

## Why the predicted starting XI does not make aggregate lineup state available

PR #193 admits the exact `starters` arrays as a predicted/EXPECTED starting XI, but the same source observation has no reviewed `bench` or `substitutes` root.

PR #190 exposes one aggregate lineup state for each side. Marking that aggregate state EXPECTED would make the absent bench appear as a complete zero-player bench and could incorrectly make bench-dependent features AVAILABLE.

PR #194 therefore maps every current player record into the PR #190 candidate with:

`LineupState.UNVERIFIED_LINEUP_STATE`

This deliberately blocks lineup-dependent PR #190 features while preserving the exact PR #193 starting-XI semantics in the source admission lineage.

The handoff does not infer a zero bench.

## Position and player-quality discipline

PR #193 preserves numeric FotMob `positionId`, `usualPlayingPositionId`, and `marketValue` fields but does not authorize their football/model meanings.

PR #194 therefore passes:

- `source_position = None`;
- `position_group = UNKNOWN`;
- no market-value feature;
- no player-quality score.

No `GK`, `DEF`, `MID`, or `FWD` mapping is invented.

No star-player weighting is invented.

## Historical evidence

The frozen source observation does not establish reviewed historical player starts, minutes, ratings, or a complete schedule-history population.

PR #194 passes no:

- `HistoricalPlayerAppearance` records;
- `HistoricalTeamFixture` records;
- player-history completeness receipt;
- schedule-history completeness receipt;
- base-strength component.

All dependent rating, continuity, replacement, rest and historical availability-share features therefore remain visibly `MISSING` or `BLOCKED` under the existing PR #190 rules.

## Freshness

PR #193 deliberately froze:

`STATE_FRESH_UNTIL = CLASSIFIED_AT`

PR #194 preserves that exact boundary.

The wrapper sets:

`prospective_reuse_after_source_freshness_authorized = false`

This means the Thursday observation proves the legal evidence-to-feature mapping, but it is not automatically reusable as current player context for a later Saturday decision. A later prospective pipeline must obtain a newer reviewed observation rather than silently carrying the old lineup/injury state forward.

## Authority

True only at this boundary:

- `team_strength_feature_authorized` for the exact replayed PR #194 handoff.

Explicitly false/not used:

- bench semantics;
- position semantics;
- historical player evidence;
- prospective reuse after the source freshness instant;
- probability inference;
- probability adjustment;
- pricing;
- selection;
- production approval;
- BET.

## Scientific consequence

PR #194 does **not** justify changing expected-goal rates because Nottingham Forest has one unavailable player and Leeds has five.

Raw injury counts are not a validated player-impact model. The next expected-goals champion/challenger boundary may consume only context variables for which a defensible training/evaluation mechanism exists. Unsupported player context may instead contribute to uncertainty or block stronger authority; it must not receive an arbitrary probability coefficient.
