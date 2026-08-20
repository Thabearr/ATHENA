# Real FotMob player-context array admission

## Boundary

This PR is the first exact semantic review of the real prospective player-context
evidence captured by PR #192. It does not recapture FotMob and does not
generalize one observation into a source-wide schema.

The exact source lineage is frozen to:

- PR #192 head `46f76e8033d3d498131c6f893111b437b6b459a9`;
- workflow run `32410775191`;
- artifact `9422055017`, `fotmob-prospective-player-context-evidence`;
- artifact digest `sha256:db5dc12b8863cbac15f210e018ddf0af9b9011a6ad8c3958a473a597254f44b5`;
- fixture `FOTMOB:5795367`;
- Nottingham Forest (`10203`) vs Leeds United (`8463`);
- kickoff `2026-08-22T14:00:00Z`;
- match-details raw SHA-256 `7b6fe187ae3dd175721f51be107f822a89359f8c6891854f4035b07b449a8e99`;
- PR52 receipt SHA-256 `a6e43fc21f0e3be310c0139746969841a21df35bad2b9c1e009535b3b1070c44`;
- PR53 structure SHA-256 `8ac7b767caedf427e32c142ed91dd71ab2bd64444513f906ab949f88f361bcea`.

The dedicated hosted proof downloads that exact successful artifact, verifies its
GitHub run/artifact metadata, full-replays PR52 and PR53, then rebuilds the exact
semantic admission. It performs no network request to FotMob.

## Semantics admitted for this exact observation

The exact raw response contains `content.lineup` with:

- `lineupType = "predicted"`;
- `source = "enetpulse"`;
- a `homeTeam` object whose exact provider team ID is `10203`;
- an `awayTeam` object whose exact provider team ID is `8463`;
- `starters` arrays containing exactly 11 provider player records per side;
- `unavailable` arrays containing exactly 1 home and 5 away player records.

PR #193 explicitly reviews only these exact-observation meanings:

1. `content.lineup.homeTeam` is the HOME team object for this response and its exact ID/name must reconcile with the same response's fixture identity.
2. `content.lineup.awayTeam` is the AWAY team object under the same rule.
3. `starters` is the provider's predicted starting-XI record set for this exact observation. `lineupType = "predicted"` maps to ATHENA `EXPECTED`, never `CONFIRMED`.
4. `unavailable` is the provider unavailable-player record set for this exact observation.
5. Each admitted record is identified only by the exact positive provider player `id`. Array index is provenance, not identity.
6. For all six unavailable records in this exact observation, `unavailability.type` is exactly `"injury"`, so the exact unavailable subtype is admitted as injury for this observation only.
7. The exact starter and unavailable arrays are reviewed complete for their own exact-observation scopes. This does not establish completeness for any future capture.

Provider player identity is fixture-global. A player appearing in more than one reviewed scope fails closed rather than being silently reconciled.

## What is deliberately not admitted

There is no `bench` or `substitutes` root in the reviewed team objects. Therefore `bench_evidence_status = MISSING_SOURCE_ROOT` is not equivalent to a zero-player bench. Bench semantics remain unauthorized.

The response contains numeric `positionId` and `usualPlayingPositionId` values. PR #193 preserves those exact numbers as raw source fields but does **not** map them to `GK`, `DEF`, `MID`, or `FWD`. No position semantics are authorized.

The response also contains numeric `marketValue` values. They are preserved as raw source numbers only. Currency, unit, valuation methodology and suitability as a model feature are not established here, so market-value semantics remain unauthorized.

No expected-return text is interpreted as a medical prognosis or reliable return date.

## Freshness

The semantic review itself is about immutable exact source bytes. The football state observed in those bytes is not projected forward. The reviewed current-state freshness boundary is deliberately `STATE_FRESH_UNTIL = CLASSIFIED_AT`.

A later Saturday prediction must obtain a newer reviewed capture rather than pretend this Thursday predicted lineup is still current.

## Authority

The authoritative wrapper can be created only by exact replay of the frozen PR #192 evidence. The following exact-observation semantic authorities are true:

- exact-observation array semantics;
- exact provider player identity;
- exact HOME/AWAY team-side semantics;
- exact predicted starting-XI semantics;
- exact unavailable-player semantics.

The following remain false:

- bench semantics;
- position semantics;
- market-value semantics;
- expected-return semantics;
- source-wide FotMob qualification;
- team-strength feature authority;
- probability inference or adjustment;
- pricing;
- selection;
- production approval;
- BET.

This PR therefore does not yet feed player context into the xG model. A later reviewed adapter boundary must decide how these exact-observation semantics can enter the PR #190/#191 team-strength chain without inventing missing bench, position, historical-player or model-effect evidence.
