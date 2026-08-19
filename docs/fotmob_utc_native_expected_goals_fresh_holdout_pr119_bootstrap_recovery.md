# Fresh-holdout PR119 bootstrap recovery

## Status

`RESEARCH_ONLY_FAIL_CLOSED_BOOTSTRAP_RECOVERY`

## Evidence that opened this boundary

After PR #174 merged, the next ordinary scheduled fresh-holdout collection run was GitHub Actions run `32236046186` on exact `main` `30520e8b5f451cb505b55fec80b505c18a1b529f`.

PR #174's campaign-origin recovery worked: predecessor restore succeeded, the earlier zero-artifact pre-acquisition failures were mechanically excluded under the reviewed rule, and the run resolved a legitimate nominal slot of `2026-08-19T08:37:00Z`.

The next step then failed before any FotMob acquisition with:

`source ndjson missing from PR119 artifact`

The collection tick and staged-capture reconciliation were skipped. No provider request was made by that run.

The failure-package step also hit the independent Python-scope error:

`NameError: name 'tar_name' is not defined`

The read-only lineage audit remained `PARTIAL_UNVERIFIED_GITHUB_LINEAGE`, because the failed run exposed no canonical Actions artifact.

## Root cause

The preserved PR119 Actions artifact is artifact ID `9249856559`, exact ZIP size `61,886,753` bytes and SHA-256 `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`.

That ZIP preserves the historical campaign research-cache archive and campaign metadata. It does **not** contain a pre-materialized file at:

`database/market_evidence/fotmob_data_matches_epl_historical_raw_features.ndjson`

The fresh-holdout workflow therefore made an invalid assumption about the artifact layout.

The repository already contains the exact reviewed PR119 execution boundary:

`scripts/qualify_fotmob_historical_source_history_completeness_materialization.py`

Frozen blob:

`2409676b4993a25024e2e8554e84e3525e7c5e6e`

That executor accepts the preserved PR119 artifact ZIP directly, replays the reviewed historical adapter/materialization chain offline, and emits the exact frozen PR119 projection.

## Recovery behavior

When the bootstrap Release cache does not already contain the exact reviewed projection, the scheduled workflow now:

1. pins the PR119 materialization executor to the reviewed blob;
2. downloads only preserved artifact ID `9249856559` through GitHub Actions API access;
3. verifies the exact artifact ZIP size and SHA-256 before execution;
4. invokes the reviewed PR119 executor against the ZIP directly;
5. verifies the exact PR119 replay receipt identity;
6. verifies the resulting bootstrap projection identity before collection can proceed;
7. may publish that already-verified projection as the existing bootstrap Release cache.

Frozen materialization identities remain:

- rows: `21,326`;
- projection size: `10,545,099` bytes;
- projection SHA-256: `e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2`;
- PR119 receipt size: `6,810` bytes;
- PR119 receipt SHA-256: `da8037cd9b4a4f91be942a4052e76134b66cc94221ed66e624c14008c9e562a0`.

The workflow no longer extracts the PR119 ZIP with a generic `extractall` call and no longer searches for the nonexistent NDJSON path.

## Failure evidence durability

Once schedule-slot resolution has succeeded, a later bootstrap failure has a legitimate nominal identity even though acquisition has not started.

The existing package step already chooses the `failure-*` asset when the collection tick has no successful exit code, creates the reviewed state root if necessary, and writes the nominal slot/run/release/archive identity into the canonical receipt. The post-PR174 lineage verifier can restore such an archive and preserve its nominal slot as the latest attempted slot without treating it as a committed observation.

PR #175 fixes the independent embedded-Python scope error by reporting `tar_path.name` rather than referencing the shell-only `tar_name` variable as a Python variable.

This does not fabricate a control row, capture, observation timestamp, or `TICK_COMMITTED` event.

## Safety

This boundary does not:

- rerun the failed `08:37` slot;
- backfill any missed observation;
- perform any retrospective FotMob request;
- broaden provider network authority;
- alter the `:07` / `:37` schedule;
- alter xG model or calibration semantics;
- approve the xG successor;
- authorize pricing, selection, execution, or `BET`.

Only the ordinary future scheduled workflow may perform the already-reviewed live FotMob collection step. Any elapsed prospective slots remain missing unless a contemporaneous reviewed observation actually existed.

## Next boundary

`MERGE_THEN_OBSERVE_NEXT_ORDINARY_SCHEDULED_RUN_AND_REAUDIT_LINEAGE`

After merge, do not rerun run `32236046186` and do not manually invoke a missed nominal slot. Allow the next ordinary schedule event to run, then use control issue #172 to read-only audit the resulting Actions/Release lineage.
