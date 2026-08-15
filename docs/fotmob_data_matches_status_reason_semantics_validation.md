# Reviewed FotMob `status.reason` semantics validation

PR #91 executes the exact `status.reason` gate pre-registered by PR #90 against the preserved PR #85 capture pair. It is evidence-only and does not promote source capabilities or authorize downstream model, probability, pricing, selection, production, or betting behavior.

## Exact ancestry

Execution starts from merged main `37b1d69c6543104b390d341b343588617c101902` and binds the reviewed PR83 protocol blob `25f8045524badcb90239df59ac9c47f36fcffe34`, PR85 evidence blob `7b74e9893071ef47ea425b4f106d92b0c5e1ddc2`, PR89 implementation blob `f33dd31aedcd92b5691a3503914ed184d601b493`, PR90 protocol blob `f9546ff05cddfe366d278d4dbdf1020bb7666951`, and source-capability blob `ffd9730d6675a7dbcc9e8622d6e9844b772b6f96`.

PR90 canonical protocol identity remains `08bbc2d1e53cfb1268ba71745ae80d9bc32f4bfad0f02d52225df936c7634f23`, 5602 bytes.

## Exact capture pair

The request identity remains `20260814 / UTC / NGA`.

Capture A is `a18e843fabe5aca74846b160`, raw SHA-256 `fbcf24729973dbe7153c87fe9f37bd988aaca14ad10cce6b260ac7df650ff80f`, manifest SHA-256 `27bfb5dc90c67a305bdb045a7ff33010d87c4109925384d3e6d2a6e058d7b302`, 114920 bytes, observed `2026-08-14T17:12:02.437509Z`.

Capture B is `e28d9ce746c1ef9102995517`, raw SHA-256 `175c6f94788fbf676e08a288ff0c46a995cd8798d60e4bc5044076e3c9713f8d`, manifest SHA-256 `d60501a5b7b1b4e5c810a0a0463bdcecb3a0b806110ad4542c314f8fe536824e`, 114964 bytes, observed `2026-08-14T17:17:13.043248Z`.

The exact separation is 310.605739 seconds, above PR83's 300-second minimum. Both captures must first revalidate through PR89 as `QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN`.

## Deterministic result

PR91 independently reconstructs PR83 candidates using source fixture/team/league identity, kickoff, strictly post-kickoff observation, `finished=True`, `started=True`, `cancelled=False`, exact nonnegative integer scores, and identical identity/score pairs across the two captures.

The exact result is 29 stable finished identity-and-score pairs. Applying only PR90's exact reason policy gives:

- 28 `QUALIFIED_PR83_REASON_GATE_ORDINARY_FT_SOURCE_LABEL`
- 1 `BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS`
- 0 candidates in every other PR90 blocker class

The 28 qualified candidates use exactly `FT / fulltime_short / Full-Time / finished`, with `status.awarded` absent or false and `penScore` absent on both endpoints in both captures. This clears only the PR83 reason-label gate for source-reported finished-score semantics. It does not establish regulation-time, extra-time, penalty, or bookmaker-settlement meaning.

## Penalty candidate

Fixture `5844873` remains blocked. Its source home/away score is `1-1`, endpoint `penScore` values are `5-6`, `eliminatedTeamId=6576`, and its exact reason tuple is `Pen / penalties_short / After penalties / afterpenalties`.

PR91 does not decide which of those fields governs any football or settlement interpretation.

## Safety and receipt

Execution state is `EXECUTED_ORDINARY_FT_REASON_GATE_QUALIFIED_PENALTY_BLOCKED`.

The ordinary FT gate has qualified candidates, but global `status.reason` semantics remain unqualified because the penalty path is unresolved. Penalty-score semantics and final-result semantics remain false. `full_time_score` remains `NOT_CAPTURED`; `historical_coverage` remains `UNKNOWN`; every downstream authority flag remains exact false.

Canonical receipt: SHA-256 `3e8537a4ddfd2d558a493ace74bd302a7d9f835c4768dc05049682e8ddf94abf`, 3307 bytes.

## Next boundary

`EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FINAL_RESULT_SEMANTICS_VALIDATION_WITH_REVIEWED_REASON_GATE`

That boundary must use only reason-qualified ordinary FT candidates, preserve the penalty candidate as blocked, and remain fail-closed on source capability and downstream authority unless separately reviewed.