# Reviewed FotMob team-strength context adapter

## Reviewed authorization handoff

The adapter is the only boundary in this PR that may set
`team_strength_feature_authorized=true`. It first full-revalidates PR52/53 and
the exact reviewed array artifact, reconstructs PR190 inputs mechanically, and
calls the unchanged `build_team_strength_context_candidate(...)`.

It then records and revalidates the exact nested candidate canonical SHA and
size. The nested PR190 candidate remains candidate-only with every safety flag
false. A naked candidate, caller SHA, caller record kind, caller position group,
or caller completeness assertion never becomes authority.

The wrapper grants no authority for probability inference or adjustment,
pricing, selection, production approval, or BET.

## Mechanical mappings

- Reviewed record-set scope determines `STARTER`, `BENCH`, or `UNAVAILABLE`.
- Exact provider team/player IDs become source-scoped
  `FOTMOB_TEAM:<kind>:<id>` and `FOTMOB_PLAYER:<kind>:<id>` identities.
- Exact reviewed lineup and source-position mappings are reused; unknown values
  remain unverified/unknown.
- `SUPPORTED`, `STALE`, `CONFLICTED`, and `UNVERIFIED` are preserved into the
  PR190 evidence status vocabulary.
- A supported exact unavailable-set completeness receipt is projected into the
  PR190 candidate receipt shape solely so the unchanged candidate calculator
  can run. Its reviewed authority remains anchored in the outer array artifact.
- Expected/confirmed lineup state enters PR190 calculations only when both the
  exact starting-XI and bench sets have current reviewed completeness receipts.
  An incomplete set forces `UNVERIFIED_LINEUP_STATE`, so bench counts and every
  other lineup-dependent feature remain non-available.

Contradictory provider player identity fails closed rather than selecting a
winner.

## Feature availability

With an exact qualified, current reviewed observation, these candidate families
can become available where their inputs exist:

- unavailable-player count, including a reviewed complete empty set;
- starter and bench identities;
- available bench count;
- exact source position and reviewed coarse position group.

Lineup-dependent outputs remain blocked when the exact source does not prove an
expected/confirmed state. Stale or rejected evidence cannot become current.

This adapter accepts no historical appearances or historical fixtures. Main has
no reviewed historical player starts/minutes/ratings lineage at this boundary,
so player-history, ratings, continuity and replacement-quality features remain
missing. Schedule completeness is also absent, so rest/load features remain
missing. Base Elo/form could only enter through a future explicit PR66 replay;
this narrow adapter accepts none, so all base components remain missing rather
than being inferred. Attack, defence, historical xG and venue performance are
not synthesized.

No subjective player-impact coefficient, injury weight, xG adjustment,
probability calculation, bookmaker input, price, selection, or bet exists.
