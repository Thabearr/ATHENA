# Reviewed FotMob team strength and fixture intelligence

## Boundary

This boundary produces transparent, deterministic candidate features answering
how strong the two teams are expected to be for one fixture. It stops before
expected-goals adjustment or probability inference.

The layers remain separate:

1. **Base team strength** preserves reviewed Elo, form, attack, defence,
   historical xG and venue-performance components independently.
2. **Available team strength** uses exact provider player IDs, explicitly
   expected or confirmed lineups, unavailable-player evidence, strictly-prior
   starts/minutes/ratings, positional groups, continuity and bench coverage.
3. **Fixture context** exposes raw rest and schedule-window counts. Reviewed
   weather or venue values may be retained as
   `SUPPORTED_CONTEXT_NOT_YET_MODEL_FEATURE`; no coefficient is invented.
4. A future PR #191 may compare models and decide empirically whether any
   candidate variable improves expected-goals prediction.

The existing six `ModelFeatureId` values are unchanged. This module defines a
separate team-strength/context namespace and does not relabel player evidence
as form, Elo, fatigue, or freshness.

## Reviewed source-record structures

The module does not parse arbitrary FotMob arrays and does not approve wildcard
paths. No raw lineup/injury JSON path was promoted because the preserved
reviewed evidence at this base does not establish one. The exact supported
boundary is instead the following narrow set of source-anchored semantic record
types; an upstream extractor must establish these records before this builder
can consume them:

- `ReviewedPlayerRecord`: exact team/player IDs, starter/bench/unavailable role,
  explicit lineup state, exact source position and reviewed coarse position,
  unavailability reason, observation time, source reference and evidence hash;
- `HistoricalPlayerAppearance`: completed strictly-prior fixture identity,
  team/player IDs, starter state, minutes, optional rating and venue side;
- `HistoricalTeamFixture`: completed fixture/team identity and kickoff used for
  schedule measures;
- `BaseStrengthComponent`: one reviewed long-term component with its own
  evidence anchor;
- `SupportedContextRecord`: preserved reviewed context that is not yet a model
  feature.

Array order is irrelevant. Exact player IDs anchor identity. Duplicate or
contradictory current records fail closed. Display names are not identity.
Unknown source structures must first receive their own semantics review; the
legacy advanced scraper is not connected.

Availability-list completeness, player-history completeness, and schedule-
history completeness are not inferred from an empty tuple. Each team requires
its own `EvidenceAnchor` receipt for those claims. Without the corresponding
receipt, dependent values remain `MISSING`; contradictory availability is
`BLOCKED`. The canonical snapshot carries every material source reference,
observation time, and evidence SHA, while every feature links to the exact SHA
set that produced it.

## Timing and lineup semantics

Every material observation must be at or before the snapshot `as_of`, and
`as_of` must be strictly before kickoff. Post-kickoff evidence is rejected.
Historical appearances and fixtures contribute only when their kickoff is
strictly before the target kickoff; same-kickoff and future records are
excluded.

Lineup states are exactly `CONFIRMED`, `EXPECTED`, `NOT_AVAILABLE`, or
`UNVERIFIED_LINEUP_STATE`. Proximity to kickoff never upgrades a lineup.
Missing/unverified lineups remain blocked, and missing availability evidence
does not become zero unavailable players.

## Player quality and reliability

No subjective impact weight exists. Immutable per-player records expose
previous-5 and previous-10 starts, minutes and team-minute share; recent XI
participation; minutes-weighted rating; rating observation count; and rating
minutes. The separate team namespace exposes availability shares, XI arithmetic
and minutes-weighted rating, position-group rating components, most-recent and
five-match continuity, retained minutes, replacement counts, replacement
evidence gaps, and bench coverage.

Ratings remain missing when no rating sample exists; they are never zero-filled.
GK, DEF, MID and FWD aggregates remain separate. A source position can be
preserved while its reviewed coarse mapping remains `UNKNOWN`; neither shirt
number nor player name supplies a mapping. Five- and ten-match evidence windows
remain visible rather than one being declared best.

The snapshot resolves the complete, typed 66-member
`TeamStrengthFeatureId` namespace. It never adds to or changes the six generic
`ModelFeatureId` members.

## Authority

`team_strength_feature_authorized=true` means only that this deterministic
feature snapshot may be constructed. Probability inference and adjustment,
pricing, selection, production approval and BET authority are all false.

This PR does not claim that injuries, ratings, continuity, depth or schedule
features improve prediction merely because they are plausible. They are
candidate explanatory variables for the future frozen model competition.
