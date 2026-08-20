# Real FotMob player-context team-strength candidate handoff

## Boundary

PR #194 takes the exact real player-context semantic admission established by PR #193 and carries only the semantics actually supported by that exact observation into the PR #190 team-strength candidate schema.

The boundary is intentionally narrow. It is a **candidate-mapping proof**, not team-strength feature authority, not an expected-goals adjustment, and not a claim that the Thursday observation remains current for Saturday.

## Exact source ancestry

The public builder does not accept a caller-constructed PR #193 wrapper. It accepts only the five frozen PR #192 evidence byte streams and invokes the PR #193 builder again:

1. `campaign-receipt.json`;
2. `match-details/manifest.json`;
3. `match-details/response.json`;
4. `match-details/persisted-evidence-receipt.json`;
5. `match-details/structure-assessment.json`.

PR #193 therefore replays PR52/PR53 and re-establishes the exact `FOTMOB:5795367` semantic admission before any team-strength candidate is built.

PR #194 also freezes the canonical PR #193 admission identity and the exact reconstructed PR #190 candidate identity. A different source admission or a different candidate cannot pass the handoff invariants merely by supplying syntactically valid hashes.

The dedicated hosted proof downloads the exact successful PR #192 artifact:

- run `32410775191`;
- artifact `9422055017`;
- artifact digest `sha256:db5dc12b8863cbac15f210e018ddf0af9b9011a6ad8c3958a473a597254f44b5`;
- source head `46f76e8033d3d498131c6f893111b437b6b459a9`.

No new FotMob request occurs in this PR.

## Exact candidate result

Only the exact current unavailable-player completeness admitted by PR #193 is eligible to become AVAILABLE inside this frozen PR #190 **candidate**.

For the frozen observation:

- Nottingham Forest unavailable-player count = `1`;
- Leeds United unavailable-player count = `5`.

These are the only two PR #190 candidate `AVAILABLE` feature resolutions:

- `home_unavailable_player_count`;
- `away_unavailable_player_count`.

PR #194 verifies this exact source-replayed candidate mapping but keeps:

`team_strength_feature_authorized = false`

The nested PR #190 candidate also remains all-false, as designed.

## Why this does not bypass PR #191

PR #191 established ATHENA's authoritative team-strength adapter as a full-replay boundary over reviewed array evidence **plus** the admitted PR65 Fixture Intelligence snapshot and PR66 model-feature handoff.

The real PR #192 artifact contains the fixture/bootstrap evidence and the PR52/PR53 match-details evidence used by PR #193, but it does not contain the required PR65/PR66 artifacts for this exact observation.

PR #194 therefore must not create a parallel feature-authority path. It proves the exact mapping only. A later narrow boundary must establish/replay the missing admitted Fixture Intelligence/model-feature lineage and then use the PR #191 authority discipline before current player context can carry team-strength feature authority.

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

This means the Thursday observation proves the evidence-to-candidate mapping, but it is not automatically reusable as current player context for a later Saturday decision. A later prospective pipeline must obtain a newer reviewed observation rather than silently carrying the old lineup/injury state forward.

## Authority

Verified at this boundary:

- exact source replay through PR #193;
- exact canonical PR190 candidate reconstruction;
- only the two unavailable-player count resolutions are AVAILABLE in that candidate.

Explicitly false/not used:

- team-strength feature authority;
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
