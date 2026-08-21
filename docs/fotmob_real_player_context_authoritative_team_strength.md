# Real FotMob authoritative team-strength bridge

## Boundary

PR #197 closes the authority gap deliberately left by PR #194 for the exact real
prospective FotMob observation captured by PR #192 and semantically admitted by
PR #193.

The boundary does **not** weaken the generic PR #191 array contract to fit one
provider response. The real FotMob response has no generic `isHome` boolean in
its lineup records or lineup team containers, while PR #193 already reviewed the
exact `homeTeam`/`awayTeam` semantics for this observation. Rather than invent a
boolean or broaden a reusable contract, PR #197 keeps PR #191 unchanged and
replays the PR #193/PR #194 exact source while independently establishing the
same required Fixture Intelligence/model-feature ancestry from the exact same
raw bytes.

## Exact source

The source remains the frozen PR #192 evidence artifact:

- workflow run `32410775191`;
- artifact `9422055017`, `fotmob-prospective-player-context-evidence`;
- artifact digest `sha256:db5dc12b8863cbac15f210e018ddf0af9b9011a6ad8c3958a473a597254f44b5`;
- source head `46f76e8033d3d498131c6f893111b437b6b459a9`;
- fixture `FOTMOB:5795367`;
- Nottingham Forest (`10203`) vs Leeds United (`8463`);
- kickoff `2026-08-22T14:00:00Z`;
- raw match-details SHA-256 `7b6fe187ae3dd175721f51be107f822a89359f8c6891854f4035b07b449a8e99`;
- PR53 structure SHA-256 `8ac7b767caedf427e32c142ed91dd71ab2bd64444513f906ab949f88f361bcea`.

PR #193 admission SHA-256 remains
`acf53d913ee3d7a6c4f357860aa2730b5122ad8a169f4a38bcc4ab882c6d4ad8`.

PR #194 candidate SHA-256 remains
`cc48bbcea5a17ff57a39cc951c5e69005008d857366359528aaf46f979c30745`.

## Same-raw PR52 -> PR66 ancestry

PR #197 independently replays PR52 and PR53 from the exact preserved bytes and
then admits one narrow scalar from that exact observation through the existing
PR54 -> PR66 chain:

`/content/lineup/lineupType = "predicted"`

The scalar is reviewed as `IntelligenceCategory.LINEUP`, field `lineup_type`.
This mapping is exact-observation only and is already independently supported by
PR #193's semantic review. It is not a source-wide FotMob qualification.

The scalar is then carried through:

1. PR54 explicit scalar semantics;
2. PR55 unverified candidate extraction;
3. PR57 unverified Fixture Intelligence fact;
4. PR58 exact-observation evidence qualification;
5. PR60 explicit freshness policy;
6. PR61 classification at the exact PR193 classification instant;
7. PR62 fact-status materialization;
8. PR63 exact candidate set;
9. PR64 explicit whole-set admission;
10. PR65 Fixture Intelligence snapshot;
11. PR66 model-feature handoff.

The bridge verifies that the admitted PR62 member uses the same raw SHA-256 and
the same PR53 structure SHA-256 as PR193. This reproduces PR191's critical
ancestry discipline: team-strength authority cannot be created from a detached
player-context object whose underlying raw observation is absent from the
admitted Fixture Intelligence lineage.

`lineup_type` is not a PR31 generic model feature. Therefore PR66 must keep all
six generic mapped model features `MISSING`; PR #197 does not use this scalar as
a hidden xG input.

## Team-strength authority

After both independent proofs are true:

- exact PR193/PR194 source replay reconstructs the frozen PR190 candidate; and
- exact same-raw PR52 -> PR66 ancestry is rebuilt and admitted;

PR #197 grants:

`team_strength_feature_authorized = true`

for **this exact observation boundary only**.

The only AVAILABLE PR190 candidate resolutions remain:

- `home_unavailable_player_count = 1.0`;
- `away_unavailable_player_count = 5.0`.

No additional player or lineup feature becomes AVAILABLE.

The nested PR190 candidate itself remains all-false, exactly as designed. The
new authority exists only in the source-replayed wrapper which proves the
missing ancestry.

## What remains deliberately unavailable

The real observation still has no reviewed bench root. Missing bench is not a
zero-player bench and aggregate lineup-dependent features remain blocked or
missing.

PR #193 did not authorize `positionId`, `usualPlayingPositionId`, `marketValue`,
or expected-return semantics. PR #197 therefore does not create position groups,
player-quality values, star-player weights, or medical return estimates.

No reviewed historical player starts, minutes, ratings, or complete historical
schedule population is introduced here.

## Freshness

PR #193 froze player-state freshness at its exact classification instant. PR
#197 preserves:

`prospective_reuse_after_source_freshness_authorized = false`

Therefore this authority proof does **not** say the Thursday injury/predicted-XI
state is current for Saturday. The Saturday prospective pipeline must obtain a
new reviewed capture and pass the corresponding evidence/authority gates.

## Probability/model consequence

PR #197 does not change expected-goal rates and does not introduce an injury
coefficient. The fact that one side had one unavailable player and the other had
five is not, by itself, a scientifically validated xG adjustment.

The next xG champion/challenger boundary may use team/player context only if the
context effect is trained/evaluated with defensible historical evidence. Where
such evidence is absent, context may increase uncertainty or block stronger
authority but must not receive an arbitrary probability movement.

## Authority summary

True only for the exact source-replayed observation:

- exact-observation team-strength feature authority;
- team-strength feature authority.

False/not used:

- source-wide team-strength authority;
- prospective reuse after the exact freshness instant;
- bench semantics;
- position/player-quality semantics;
- historical player evidence;
- xG/probability inference;
- probability adjustment;
- pricing;
- selection;
- production approval;
- BET.
