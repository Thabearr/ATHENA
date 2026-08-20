# Prospective FotMob player-context evidence campaign

## Boundary

This PR captures and structurally inventories real prospective FotMob
player-context evidence. It does not approve football semantics for discovered
player arrays, authorize team-strength model features, adjust expected goals or
probabilities, or authorize bookmaker pricing, selection, or BET.

The campaign exists because PR #191 correctly found no admissible preserved
PR52/PR53 observation containing player arrays. PR #192 closes only the
operational acquisition gap:

```text
transparent /api/data/matches capture
→ exact PR39 structural assessment
→ exact PR40 target candidate
→ explicit PR41 review
→ explicit PR45 admission and PR48 bootstrap
→ transparent prospective /api/matchDetails capture
→ durable PR52 verification
→ PR53 structural inventory
→ neutral player-context review candidates
```

Capture is not review. The next boundary must explicitly review the observed
exact source semantics before PR #191's authoritative team-strength adapter can
consume them.

## Frozen target and exact resolution

The campaign is bound to the 2026-08-22 request date and compares only against
the exact source candidate:

- home: `Nottingham Forest`;
- away: `Leeds United`;
- kickoff: `2026-08-22T14:00:00Z`.

These values are comparisons, not fixture authority. The source match ID and
`FOTMOB:<id>` fixture identity are recovered from the verified dataMatches
capture. Matching is exact against the reviewed `home_long_name` and
`away_long_name` candidate fields; source display names such as `Nottm Forest`
and `Leeds` are preserved in the candidate but are not target selectors. There
is no case folding, trimming, aliasing, nearest-time selection, fuzzy name
comparison, public-page ID, or SportyBet input. Zero or multiple exact
candidates fail closed.

## Explicit review continuation

The workflow is triggered before merge by an owner-authored `pull_request:
edited` control block on draft PR #192. This avoids GitHub's rule that a
`workflow_dispatch` file must already exist on the default branch. The control
block is exact-head, same-repository, branch, PR-number, base-SHA, and actor
bound.

`CAPTURE_FIXTURE` accepts no review fields. It preserves the real dataMatches
response, manifest, PR39 assessment, and PR40 candidates, then returns
`FIXTURE_REVIEW_NOT_GRANTED`.

A `CONTINUE_EXACT_FIXTURE_ARTIFACT` run can reach match details only when the
owner supplies all of:

1. the exact canonical PR40 candidate SHA printed in the first receipt;
2. `fixture_review_disposition=APPROVED`;
3. `catalog_admission_disposition=ADMITTED`;
4. the exact first-run workflow run ID and artifact ID, size, and SHA-256
   digest.

GitHub metadata must prove that artifact came from a successful run of this
exact campaign at the same exact PR head. The continuation downloads it,
strictly reconstructs the canonical campaign receipt, verifies every listed
file SHA/size, replays the exact PR38 manifest/raw bytes through PR39 and PR40,
and requires byte equality with the preserved derived files. It then
materializes that same source evidence under the reviewed capture root for
PR41. It performs no second dataMatches request. Thus the reviewed candidate
SHA names the same exact source observation that crosses PR41 through PR48.

The GitHub actor and run identity become audit evidence. There is no
`APPROVE_WHATEVER_WAS_RETURNED` mode and no arbitrary match-ID input. The
runner reconstructs PR41 through PR48 before the match-details capture API can
build its request plan. If the target is no longer prospective, the request is
not sent.

Initial PR-body control block:

```text
<!-- ATHENA_FOTMOB_PLAYER_CONTEXT_CAMPAIGN_V1 -->
campaign-mode: CAPTURE_FIXTURE
repository-head-sha: <exact PR head>
confirm: CAPTURE_EXACT_FOTMOB_FIXTURE_CATALOG
<!-- /ATHENA_FOTMOB_PLAYER_CONTEXT_CAMPAIGN_V1 -->
```

Continuation uses the same delimiters with the exact fields frozen by the
workflow: `campaign-mode`, `repository-head-sha`, `source-run-id`,
`source-artifact-id`, `source-artifact-size`, `source-artifact-digest`,
`fixture-candidate-sha256`, both explicit dispositions, and the exact
`REPLAY_EXACT_ARTIFACT_AND_CAPTURE_MATCH_DETAILS` confirmation.

## Reviewed match-details route migration

During the real prospective campaign, the historical reviewed route `/api/matchDetails` returned a non-200 response. A separate transparent discovery-only hosted diagnostic at the same exact PR head and source match id observed:

- `/api/matchDetails?matchId=<id>` → HTTP 404, HTML;
- `/api/data/matchDetails?matchId=<id>` → HTTP 200, `application/json; charset=utf-8`.

The PR #49 live request builder is therefore migrated to `/api/data/matchDetails` for prospective requests. Historical pre-migration plans remain audit-replayable under a strict timestamp cutoff. No X-Mas header, cookie, browser impersonation, bypass client, or semantic inference was introduced. The diagnostic itself is discovery evidence only; the trusted evidence path still begins only when the exact PR #50 response is durably captured and replayed through PR #52/53.

## Transparent acquisition

Both live calls reuse existing reviewed ATHENA capture paths. They use
`www.fotmob.com`, the fixed transparent headers, and the reviewed routes. The
campaign does not use X-Mas, cookies, a user session, browser or mobile
impersonation, private credentials, TLS fingerprinting, a proxy, the legacy
advanced scraper, or a bypass client.

The match-details request is derived only from the exact verified PR48
bootstrap and is rejected at or after kickoff. Complete response bytes are
published durably under the existing ignored research roots and independently
read back for PR52 verification.

## Neutral structural report

The player-context report is derived only from PR53 `StructuralField` records.
It lists exact pointer patterns, JSON kinds, occurrence counts, parent pointers,
raw identity, fixture identity, observation time, and the structure-assessment
identity. Paths are sorted deterministically.

Name-based discovery is intentionally neutral. A path containing `playerId`,
`lineup`, `bench`, `position`, `injury`, or a similar token is classified only
as `PLAYER_CONTEXT_REVIEW_CANDIDATE`. It does not become PLAYER_ID, STARTER,
BENCH, CONFIRMED_LINEUP, INJURED, HOME, or a position group. PR53 records
wildcard path occurrence counts but not each array's individual cardinality;
the report says so and does not infer a cardinality.

PR #192 never invokes PR #191 to create a qualified real array artifact or a
reviewed team-strength context.

## Artifact and receipt

The workflow uploads `fotmob-prospective-player-context-evidence`. Depending on
the fail-closed stopping point, it contains the committed stages among:

```text
campaign-receipt.json
fixture/response.json
fixture/manifest.json
fixture/schema-assessment.json
fixture/fixture-candidates.json
fixture/review-decision-ledger.json
fixture/catalog.json
fixture/catalog-manifest.json
fixture/admission.json
fixture/bootstrap.json
fixture/bootstrap-verification-receipt.json
match-details/response.json
match-details/manifest.json
match-details/persisted-evidence-receipt.json
match-details/structure-assessment.json
player-context-review-candidates.json
```

Every evidence file is listed by normalized relative path, exact byte size,
and SHA-256 in the canonical receipt. The receipt also records the exact
repository head SHA and independent hashes for every completed fixture,
review/bootstrap, match-details, PR52, PR53, and discovery-report stage.
Completed files cannot exist without their corresponding receipt identity.
A terminal success requires the complete fixture → bootstrap → match-details
→ PR52 → PR53 → report chain; a later-stage failure retains every earlier
completed identity. Canonical JSON is sorted-key, compact, UTF-8,
`allow_nan=False`, with exactly one final LF.

## Failure is evidence

Acquisition, schema, identity, review, timing, JSON, persistence, and structure
failures are explicit campaign result states. A fail-closed run still uploads
the stages it durably completed. It never manufactures a success or retries by
changing the target.

## Authority

Every receipt and discovery report keeps these exact false:

- array semantics;
- automatic review and source-wide qualification;
- intelligence facts and model features;
- team-strength features;
- probability inference and adjustment;
- pricing;
- selection;
- production approval;
- BET.

No model, ScoreMatrix, market, expected-goals coefficient, calibration,
SportyBet mapping, pricing, value, Kelly, selection, accumulator, or execution
code is changed by this PR.
