# Real FotMob player-context authoritative team-strength bridge

## Boundary

PR #197 closes the authority gap left deliberately by PR #194.

PR #194 proved that the exact PR #193 real player-context admission maps into the PR #190 team-strength candidate with exactly two AVAILABLE current-context resolutions:

- Nottingham Forest unavailable-player count = `1`;
- Leeds United unavailable-player count = `5`.

It correctly kept `team_strength_feature_authorized = false` because the exact real observation had not yet been carried through the admitted PR #65 Fixture Intelligence / PR #66 model-feature ancestry required by PR #191's authority discipline.

PR #197 adds only that missing reviewed ancestry. It does not add a player-impact model, expected-goals coefficient, probability, bookmaker price, selection, or BET authority.

## Exact real source

The bridge accepts only the five frozen PR #192 evidence byte streams:

1. `campaign-receipt.json`;
2. `match-details/manifest.json`;
3. `match-details/response.json`;
4. `match-details/persisted-evidence-receipt.json`;
5. `match-details/structure-assessment.json`.

Those bytes are the exact successful prospective capture for:

- fixture `FOTMOB:5795367`;
- Nottingham Forest vs Leeds United;
- kickoff `2026-08-22T14:00:00Z`;
- raw SHA-256 `7b6fe187ae3dd175721f51be107f822a89359f8c6891854f4035b07b449a8e99`;
- PR #53 structure SHA-256 `8ac7b767caedf427e32c142ed91dd71ab2bd64444513f906ab949f88f361bcea`.

The hosted proof downloads the exact PR #192 artifact from run `32410775191`, artifact `9422055017`, source head `46f76e8033d3d498131c6f893111b437b6b459a9`.

No new FotMob request occurs in PR #197.

## Why the generic PR #191 array adapter is not called directly

PR #191's generic repeated-player-array contract requires an explicitly reviewed source-side boolean through `is_home_pointer`.

The exact PR #192/PR #193 `content.lineup.homeTeam` and `content.lineup.awayTeam` objects do not contain such a boolean. PR #193 established the HOME/AWAY identities directly from the exact fixture/team object structure instead.

Inventing a boolean merely to satisfy a generic adapter would weaken the source contract.

PR #197 therefore preserves PR #191's **authority discipline** rather than forging PR #191's generic input type:

- PR #193 is fully replayed to establish exact player-array/team-side semantics;
- PR #194 is fully replayed to reconstruct the exact PR #190 candidate;
- the exact same raw SHA and PR #53 structure are independently carried through a complete admitted PR #54→PR #66 scalar lineage;
- only after both branches agree on exact fixture/source/kickoff/classification identity does the wrapper set `team_strength_feature_authorized = true`.

## The lineage sentinel

The exact raw observation already reviewed by PR #193 contains:

`/content/lineup/lineupType = "predicted"`

PR #197 uses that one scalar as a lineage sentinel:

- category: `LINEUP`;
- field: `source_lineup_type`;
- exact value: `predicted`.

The sentinel is explicitly reviewed, qualified only for this exact observation, freshness-bound only through PR #193's classification instant, materialized as one SUPPORTED Fixture Intelligence fact, admitted as the whole one-member candidate set, and then carried through PR #65 and PR #66.

It is **not** a PR #31 model feature. The PR #197 builder requires every generic PR #31 resolution produced from the sentinel-only snapshot to remain `MISSING`. If that ever changes, the bridge fails closed.

The sentinel exists only to prove that the exact PR #192 raw/PR #53 observation has crossed the existing admitted Fixture Intelligence/model-feature ancestry.

## Candidate authority

The nested PR #190 candidate is byte-identical to PR #194's frozen candidate SHA:

`cc48bbcea5a17ff57a39cc951c5e69005008d857366359528aaf46f979c30745`

The only AVAILABLE team-strength candidate features remain:

- `home_unavailable_player_count = 1.0`;
- `away_unavailable_player_count = 5.0`.

No additional current, historical, lineup-depth, position, rating, rest, continuity, replacement-quality, or player-quality feature becomes AVAILABLE.

The wrapper may now state:

`team_strength_feature_authorized = true`

for this exact classification instant because both the semantic branch and the PR #65/PR #66 ancestry are fully replayed from the same source observation.

The nested PR #190 candidate safety map remains all false, as designed.

## Predicted lineup and missing bench

PR #193 admits the `starters` arrays as an EXPECTED starting XI because source `lineupType` is exactly `predicted`.

The captured observation contains no reviewed bench/substitute root. PR #197 therefore preserves PR #194's aggregate team lineup state as:

`UNVERIFIED_LINEUP_STATE`

It does not infer an empty bench, complete squad depth, or confirmed XI.

## Position and player quality

PR #193 preserves source numeric position IDs and market-value fields but does not authorize their football/model meanings.

PR #197 does not introduce those semantics. Player components remain position `UNKNOWN`, source position is absent from the PR #190 candidate, and no market-value or star-player score is used.

## Historical evidence

No historical player starts, minutes, ratings, replacement performance, or complete schedule-history population is created by this bridge.

Historical player-dependent PR #190 features remain MISSING/BLOCKED.

## Freshness

PR #193 froze:

`STATE_FRESH_UNTIL = CLASSIFIED_AT = 2026-08-20T20:24:00Z`

PR #197 preserves that exact boundary and records:

`prospective_reuse_after_source_freshness_authorized = false`

Therefore the bridge proves that the model chain **can legally consume a fresh reviewed player-context observation when one exists**. It does not claim that Thursday's exact observation remains current for Saturday.

The Saturday prospective pipeline must obtain/review a newer observation and pass the same authority discipline before treating current player context as current.

## Probability discipline

`team_strength_feature_authorized = true` does not mean an unavailable-player count may be translated into expected goals.

PR #197 grants no:

- probability inference;
- probability adjustment;
- expected-goals adjustment;
- calibration authority;
- pricing;
- selection;
- production approval;
- BET authority.

A later xG challenger may consume only context variables for which a training/evaluation mechanism is scientifically justified. There is no rule such as "five unavailable players = minus X expected goals".

## Hosted proof

The dedicated hosted proof must establish on the exact PR head:

- exact PR #192 artifact provenance;
- exact PR #193 semantic replay;
- exact PR #194 candidate replay;
- exact same raw SHA/PR #53 structure through the one-fact PR #65 snapshot;
- exact PR #66 handoff;
- zero AVAILABLE generic PR #31 model features from the lineage sentinel;
- exact PR #190 candidate SHA and only the two unavailable-count AVAILABLE resolutions;
- `team_strength_feature_authorized = true`;
- `prospective_reuse_after_source_freshness_authorized = false`;
- probability/pricing/selection/BET authority false.

Failure of any identity, hash, chronology, source-artifact, candidate, PR #65, or PR #66 condition fails closed.
