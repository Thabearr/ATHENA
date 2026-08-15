# FotMob ordinary-FT finished-score source-history completeness assessment

## Purpose

PR #100 executes the source-history completeness protocol frozen by PR #99
against the exact registered derived FotMob ordinary-FT finished-score source.

This is a static evidence-only execution. It does **not** acquire historical
network data, materialize a history adapter or corpus, construct successor
features, or authorize modelling, probability inference, pricing, selection,
production behavior, or betting.

## Exact ancestry

The assessment binds merged PR #99 `main`:

- repository main: `43fb4aa09df0255bd76ddde0b02786a73f758771`;
- PR #99 protocol blob:
  `3dd38f5f61c20c10900fa0bee9a30a69a58a3006`;
- PR #99 canonical SHA-256:
  `edddd7445bb9bb6ed2db4778b6ab48da9489ae6efac822b6e6c139992275bf87`;
- PR #99 canonical size: `5,741` bytes;
- PR #98/current registered source-capability blob:
  `37b919eb5efa0c931e1bf10d3f845865567ef0c4`;
- reusable reviewed ordinary-FT adapter blob:
  `868563206e09010fce74b4ba7954028930baad54`.

The canonical PR #100 receipt is sorted compact UTF-8 JSON plus a final newline:

- SHA-256:
  `069a66ac3c10d6d1f7da24cd0219fc178328b3327cd1446efaaff3dfec9cffb3`;
- size: `4,720` bytes.

## Executed result

The assessment state is:

```text
EXECUTED_FAIL_CLOSED_HISTORICAL_COVERAGE_NOT_QUALIFIED
```

The primary result is:

```text
BLOCKED_HISTORICAL_COVERAGE_UNPROVEN
```

No network acquisition is performed. No source-history adapter is materialized,
and the number of materialized history rows is exactly zero.

## What now passes

Unlike the older PR #82 parent-source assessment, final-score semantics are no
longer the first blocker.

The separately registered source:

```text
fotmob_data_matches_reviewed_ordinary_ft_finished_score
```

revalidates with:

```text
full_time_score            = CONFIRMED
reliable_fixture_identity  = CONFIRMED
historical_coverage        = UNKNOWN
```

The reviewed validation ancestry remains exactly 29 terminal candidates, 28
qualified ordinary-FT finished-score observations, and penalty fixture `5844873`
excluded.

Therefore the `DERIVED_SCORE_CAPABILITY` gate is `PASSED`. This does **not**
broaden the meaning of `CONFIRMED`: it still means only source-reported finished
score for fixtures passing the exact reviewed ordinary-FT gate.

## Remaining blockers established without inventing history

The static execution establishes three current blockers:

```text
BLOCKED_HISTORICAL_COVERAGE_UNPROVEN
BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN
BLOCKED_LEAGUE_MAPPING_UNPROVEN
```

They mean:

1. there is no reviewed provenance-complete daily derived-source history corpus
   and no approved source-history adapter for that corpus;
2. no reviewed derived-source history boundary has yet been proven equivalent to
   the frozen PR #69 Elo replay initialization boundary; and
3. no explicit reviewed FotMob competition mapping has yet been established for
   all eleven frozen model leagues:
   `B1, D1, E0, F1, G1, I1, N1, P1, SC0, SP1, T1`.

The score capability itself does not clear any of these requirements.

## Gates deliberately not claimed as observed failures

The following corpus-specific statuses are not asserted as observed failures:

```text
BLOCKED_REQUIRED_DATE_GAP
BLOCKED_RESULT_EVIDENCE_GAP
BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW
BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT
```

Those checks require a real reviewed candidate history corpus. Without one,
ATHENA cannot truthfully say which calendar dates are missing, whether a
particular finished fixture lacks evidence, which non-ordinary result states
occur in the required interval, or whether a cross-season identity/chronology
conflict exists.

The corresponding gates therefore remain `NOT_REACHED`.

## No cross-source substitution

The PR #99 rule remains intact: legacy `fotmob_historical`,
football-data.co.uk, football-data.org, or any other source cannot silently fill
missing dates or results for this derived reviewed FotMob history boundary.

Those sources may remain useful elsewhere in ATHENA, but they do not prove this
source-scoped completeness contract.

## Smallest next reviewed boundary

The next engineering boundary is frozen as:

```text
PRE_REGISTER_REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_PROTOCOL
```

That boundary should be registered **before** any historical acquisition runs.
It should freeze, at minimum:

- the exact initialization/start boundary and target end/as-of boundary;
- the exact source-local timezone and `ccode3`;
- the complete required calendar-date schedule;
- the repeated-capture requirements needed by the reviewed ordinary-FT adapter;
- exact raw capture/manifests and SHA-256 lineage;
- explicit mapping for all eleven frozen model leagues;
- no target-team-only filtering;
- explicit treatment of failed/missing daily captures;
- explicit disposition of penalty, awarded, postponed, cancelled, abandoned,
  rearranged, or any other non-ordinary finished state;
- source-local/UTC chronology and source-scoped team/fixture identity checks;
- no substitution from another source;
- fail-closed stop conditions before completeness can be claimed.

Only after that acquisition protocol is reviewed should ATHENA perform the
bounded network campaign needed to discover whether the required historical
coverage can actually be established.

## Safety

Every downstream authorization remains exact `false`, including:

- source-history adapter approval;
- source-history completeness;
- PR #80 constructor-input authorization;
- successor live-input qualification;
- successor model approval;
- expected-goals transform/production use;
- score-matrix and probability inference/adjustment;
- production calibration;
- pricing and market activation;
- selection;
- production approval; and
- betting.

## What PR #100 does not conclude

PR #100 does not conclude that FotMob cannot supply the required historical
results. It concludes only that ATHENA has not yet acquired and reviewed the
source-scoped history needed to prove the frozen completeness contract.

That distinction preserves ATHENA's rule that unknown evidence remains unknown.
