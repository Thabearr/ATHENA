# FotMob source-history adapter and completeness assessment

## Scope

This boundary executes the exact PR #81 / PR #99 source-history completeness contract after the previously reviewed FotMob history work:

- PR #108 qualified the eleven source-scoped `primaryId` competition-family mappings;
- PR #110 qualified the special/non-ordinary result semantics and preservation dispositions;
- PR #112 qualified the 250 rearranged source-fixture chronologies;
- PR #114 qualified the PR #69-equivalent empty-1500 Elo initialization floors.

The assessment uses only the preserved campaign artifact `9249856559` (`7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`, 61,886,753 bytes). It does not acquire new football data, mutate any source or competition registry, construct model features, or authorize pricing, selection, production, or BET.

## Result

The result is intentionally fail-closed:

`BLOCKED_RESULT_EVIDENCE_GAP`

Historical coverage remains unproven and zero source-history rows are authorized.

This is not a regression of the mapping, special-result, chronology, or Elo-initialization work. Those gates all revalidate successfully. The new evidence shows that the **prospective** reusable ordinary-FT adapter is not an admissible historical source-history adapter for this campaign as currently frozen.

## What passed

The preserved acquisition itself is complete for its frozen envelope:

- 2,205 UTC request dates from 2020-08-01 through 2026-08-14;
- 4,410 valid capture manifests, exactly two per date;
- all 2,205 capture pairs have distinct manifest lineages and at least 300 seconds of observation separation;
- 21,640 target-family fixture/date pairs and 43,280 A/B raw target rows;
- zero same-date target relevant-field conflicts;
- exact PR #114 accounting: 10 pre-boundary ordinary-FT occurrences + 21,326 ordinary-FT candidates on/after the family floors + 304 reviewed special-state occurrences = 21,640;
- the 21,326 ordinary-FT candidate counts still match the eleven PR #114 family totals exactly.

The raw target corpus also gives a reproducible display-time observation: all 43,280 target rows have `match.time` equal, at minute precision, to `status.utcTime` converted through `Europe/Oslo`. This is recorded only as a property of this frozen corpus. PR #115 does **not** promote it into a global FotMob timezone guarantee or PR #80 constructor authorization.

## Why the existing reusable adapter blocks

PR #99 requires every admitted historical result to pass the reusable reviewed ordinary-FT finished-score adapter. That adapter was reviewed for prospective repeated captures and has two requirements that the historical campaign does not satisfy.

### 1. Pair-lineage mismatch

The adapter requires both the manifest SHA and the raw-response SHA to differ between the two observations in a pair.

The campaign has:

- 2,205 distinct manifest pairs;
- **2,204 pairs whose raw response bytes are identical**;
- only one distinct-raw pair, on `2025-07-12`.

Byte-identical historical responses are unsurprising for old completed dates, but PR #115 does not weaken the frozen adapter contract after seeing that fact. A representative identical-raw pair is rejected with:

`BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY`

Because the sole distinct-raw date contains no fixture from the frozen eleven model families, all 21,326 potential ordinary-FT historical rows lie on dates that fail this pair-lineage prerequisite.

### 2. Historical payload-schema mismatch

PR #115 also executes the existing adapter on the sole distinct-raw pair rather than assuming that raw distinctness is enough. It is rejected with:

`BLOCKED_STRUCTURAL_REVALIDATION`

The underlying frozen PR #89 structural chain encounters historical `status.halfs` keys outside its reviewed schema. This shows a second, independent reason not to reuse the prospective adapter as a historical adapter by assertion.

The structural blocker occurs on the only pair that reaches that stage. The other 2,204 pairs fail earlier at the exact raw-lineage gate, so PR #115 does not claim that every historical payload would necessarily fail the same structural check.

## Safety consequence

PR #115 deliberately does not turn the 21,326 potential ordinary-FT candidates into model history. In particular:

- `source_history_adapter_approved = false`
- `source_history_completeness_proven = false`
- `historical_coverage_proven = false`
- `ordinary_ft_history_rows_authorized = false`
- `history_rows_materialized = 0`
- `pr80_constructor_input_authorized = false`
- model training, expected-goals transformation, probability inference, calibration, pricing, market activation, selection, production approval, and BET all remain false.

The source-capability registry also remains unchanged. The derived source continues to have scoped finished-score and fixture-identity capability, while `historical_coverage` remains `UNKNOWN`.

## Why we do not simply loosen the adapter

The prospective adapter's pair-lineage and structural-schema rules are reviewed safety boundaries. Silently changing either requirement inside a completeness execution would make the result depend on what the campaign happened to contain and would erase the distinction between prospective evidence and historical static evidence.

The historical corpus needs its own pre-registered adapter semantics. That review can decide, before execution, whether independently timestamped manifests may legitimately provide two observations when the underlying immutable historical response bytes are identical, which historical payload fields are allowed or projected, how exact ordinary-FT semantics remain inherited from the reviewed chain, and how raw provenance is preserved without broadening any current/source capability globally.

## Next boundary

The smallest next reviewed boundary is:

`PRE_REGISTER_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_ADAPTER_PROTOCOL`

That protocol must remain narrow. It must not infer cross-source fixture/team identity, must not silently coerce special results into ordinary regulation-time results, must preserve every raw capture and reviewed chronology, and must not authorize PR #80 or downstream modelling until the new historical adapter is itself qualified and the completeness assessment is rerun successfully.
