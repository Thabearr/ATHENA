# FotMob team strength and fixture intelligence candidate

## Boundary

This module preserves transparent, deterministic candidate calculations for
base strength, available-team strength, and fixture context. It stops before
expected-goals adjustment or probability inference.

The reviewed FotMob lineup/injury array lineage required to authorize a real
team-strength snapshot does not yet exist at this repository base. The
caller-constructible result is therefore `TeamStrengthContextCandidate`, with:

- dataset `athena-fotmob-team-strength-fixture-intelligence-candidate-v1`;
- scope `SCHEMA_ONLY_CANDIDATE_PENDING_FULLY_REVALIDATED_FOTMOB_ARRAY_LINEAGE`;
- lineage status `BLOCKED_MISSING_FULLY_REVALIDATED_FOTMOB_ARRAY_LINEAGE`;
- every authority flag, including `team_strength_feature_authorized`, false.

`build_team_strength_context_snapshot(...)` always fails closed. A caller-
supplied SHA, source reference, semantic label, or completeness candidate can
never create an authorized snapshot.

The calculation layers remain separate:

1. **Base team strength** keeps Elo, form, attack, defence, historical xG and
   venue-performance candidates independent.
2. **Available team strength** keeps player identity, lineup, availability,
   starts, minutes, ratings, position, continuity and depth components visible.
3. **Fixture context** keeps raw rest and schedule counts. Supported scalar
   context may be retained as `SUPPORTED_CONTEXT_NOT_YET_MODEL_FEATURE`.
4. Future work may admit the evidence lineage; PR #191 may only test variables
   after that admission exists.

The existing six `ModelFeatureId` values remain unchanged. The separate typed
66-member `TeamStrengthFeatureId` namespace does not relabel player evidence as
form, Elo, fatigue, or freshness.

## Source and semantic status

No raw lineup/injury JSON path is approved here because the preserved reviewed
evidence at this base establishes none. `PlayerRecordCandidate`, historical
appearance/fixture candidates, base components, and context records are schema
objects, not proof that their contents came from FotMob.

Candidate evidence records preserve `SUPPORTED`, `STALE`, `CONFLICTED`, or
`UNVERIFIED` status. Current player evidence also requires `valid_through`.
Stale, conflicted, unverified, or expired evidence blocks affected resolutions.
These status fields remain candidate inputs: only a future full-lineage adapter
may derive them from reviewed artifacts.

Expected versus confirmed lineup state and source-position-to-GK/DEF/MID/FWD
mapping likewise remain unauthorized caller assertions in this candidate
layer. Proximity to kickoff never upgrades a lineup, and neither shirt number
nor player name supplies a position mapping.

The future authoritative adapter must:

1. fully replay the existing PR52→PR65 reviewed match-details chain;
2. mechanically bind exact raw array records and provider/player identities;
3. revalidate reviewed lineup, availability, position and freshness semantics;
4. reconstruct every candidate input from those receipts rather than accepting
   caller values;
5. compare the rebuilt canonical snapshot to the supplied artifact and bytes.

Until that exists, team-strength feature authority remains false.

## Completeness

An empty tuple or plain `EvidenceAnchor` never proves completeness.
`CompletenessReceiptCandidate` binds:

- provider and source dataset;
- exact scope (`CURRENT_AVAILABILITY`, `SCHEDULE_HISTORY`, or
  `PLAYER_HISTORY`);
- target fixture, team and as-of;
- exact time range and fixture identities;
- record count and source evidence set;
- disposition `CANDIDATE_ONLY_UNREVIEWED`.

Counts and identities must reconcile with the supplied candidate records.
Calculations consume only the exact fixture identities and time range covered
by the corresponding receipt. Rows outside that range remain in source
ancestry but cannot affect player or schedule values. A 7/14/28-day schedule
count is missing unless the receipt covers that complete interval through the
candidate `as_of`; it is never calculated from a narrower range. Count-based
player windows use only covered fixtures and expose their contributing count
and fractional 5/10-window coverage.

The typed receipt exposes what was claimed but does not make the claim
reviewed. A future reviewed completeness receipt must be source-bound and
full-replayed before absence or sparse history may create an authorized
zero/count.

## Timing and coverage

`as_of` is strictly before kickoff. Material observations must be at or before
`as_of` and before kickoff. Historical appearances bind to exact completed
fixture identity, kickoff, team and venue and contribute only when strictly
earlier than the target. Same-kickoff and future records are excluded.

Per-player candidate records expose previous-5 and previous-10:

- starts and start share;
- minutes and team-minute share;
- exact contributing fixture count;
- exact window coverage;
- minutes-weighted rating, rating count and rating minutes;
- recent-XI participation.

Thus one contributing match may have candidate `start_share_previous_10=1.0`,
but it also records count `1` and coverage `0.1`; it cannot look like a complete
ten-match sample.

Missing ratings remain missing, not zero. Missing context cannot be labelled
`SUPPORTED_CONTEXT_NOT_YET_MODEL_FEATURE`; supported context requires a
non-null immutable scalar and `SUPPORTED` evidence status.

Input array order is not semantic. Records are identity/time sorted before
arithmetic, and upstream blockers use one frozen precedence:
availability-specific conflict, generic conflict, stale, unverified, then
lineup/missing-sample blockers. Generic conflicted Elo, fixture, appearance, or
record evidence is `CONFLICTED_EVIDENCE`; only an explicit current availability
contradiction is `CONFLICTED_AVAILABILITY_EVIDENCE`.

## Authority

Every authority flag is false:

- team-strength feature authorization;
- probability inference or adjustment;
- pricing;
- selection;
- production approval;
- BET.

The calculations do not establish that injuries, ratings, continuity, depth or
schedule improve prediction. They remain candidate explanatory variables until
reviewed lineage exists and a later frozen competition evaluates them.

This PR does not complete the team-strength integration needed by the expected-
goals champion/challenger competition. The next required boundary is fully
revalidated FotMob lineup/injury array lineage plus an authoritative adapter
that alone may construct the real snapshot.
