# FotMob fresh-holdout live-capture identity compatibility

## Scope

This boundary fixes the post-PR207 live-capture qualification failure without
changing the frozen PR39 schema, the fresh-holdout core, or the activation
runner.

Scheduled collection run `32583079461` on merged main
`999ec897b6619573ba0e707952cbffac13bc1ebf` proved that lineage restoration was
fixed and reached live acquisition. Three reviewed network captures were made.
The `20260821` and `20260822` captures then failed the old PR39 fixture-candidate
qualification path.

The failure archive was retained as Actions artifact `9478318255`,
`failure-20260822T153700Z-run-32583079461.tar.gz`, and the same failure archive
was verified on release `athena-fresh-holdout-evidence-2026-W34`.

## Exact newly observed structure

The preserved source bytes show two `status.halfs` keys that are not covered by
PR39 or the later PR87 terminal-state extension:

- `firstExtraHalfStarted`
- `secondExtraHalfStarted`

Observed source lineage:

| request date | original manifest SHA-256 | original raw SHA-256 | first extra-half occurrences | second extra-half occurrences |
| --- | --- | --- | ---: | ---: |
| `20260821` | `1cacc67a60889c498dbc0877b2604382c619197c0e68a2e3253bf2739b3bae9d` | `a0273b704e786fdce00abf27487a710a06fbdbeef3b4902a83d9ccf00f9e0176` | 1 | 1 |
| `20260822` | `aaacdc3ec7c7d4dce5b4a9bd1b8bcd3e222f2eb4a696c629bb4e5896457e58ff` | `595e63c57f7b7a3876f9d7f3c6498b8a0fab84c13c7adac275ba30bf3e5a2730` | 3 | 3 |

The values are treated only as opaque exact strings. This boundary does not
interpret extra time, regulation time, score state, or settlement meaning from
them.

## Reviewed compatibility path

`domain/fotmob_fresh_holdout_live_capture_identity_adapter.py` pins the exact
existing implementations for:

1. the frozen fresh-holdout core;
2. PR39 schema assessment;
3. PR87 terminal-state structural extension;
4. PR89 `eliminatedTeamId` structural value-domain extension;
5. PR40 fixture-candidate generation;
6. the PR38 capture contract.

For one original network capture the adapter:

1. verifies the original raw size/SHA against the original network manifest;
2. parses strict UTF-8 JSON with duplicate-key and non-finite constant rejection;
3. permits only the two additional `status.halfs` keys above, each as an exact
   string, and removes only those two keys in a validation projection;
4. re-runs the already-reviewed PR89 -> PR87 -> PR39 chain on that projection;
5. only after that chain succeeds, projects already-qualified terminal fields
   and `eliminatedTeamId` back to the frozen PR39 candidate shape;
6. rebuilds the existing PR40 candidate population;
7. independently extracts provider-native fixture/competition/team/kickoff
   identity from the original source bytes using the exact pinned fresh-holdout
   identity extractor;
8. requires the projected candidate population and original-source identity
   population to agree exactly;
9. returns fixture identity bound to the original network raw SHA and original
   network manifest SHA.

The compatibility projections are validation-only. They are not source
evidence, are not persisted as a replacement for the original bytes, and cannot
supply observation timestamps or source hashes.

## Runtime installation

The scheduled workflow already executes
`scripts/run_fotmob_utc_native_xg_fresh_holdout_tick.py`. That small entry point
now pins the exact adapter blob and the unchanged activation-runner blob, then
temporarily installs the adapter as `fresh.qualify_capture_fixtures` only for
the duration of one tick. A `finally` block restores the frozen qualifier even
when the tick raises.

This scoped installation is necessary because the unchanged activation runner
uses the same fresh qualifier both for live prediction captures and for
post-kickoff settlement identity captures. Neither frozen module is edited.

## Fail-closed rules

The adapter still rejects:

- any unreviewed key other than the two exact extra-half keys;
- null or non-string values for either extra-half key;
- malformed/duplicate-key/non-UTF-8 JSON;
- non-network source manifests;
- raw-size or raw-hash disagreement;
- PR89/PR87/PR39 structural rejection;
- candidate/original identity population disagreement;
- any pinned dependency drift.

No football semantic, source-capability, model-feature, probability, pricing,
selection, production, or BET authority is added.

## Validation target

Hosted GitHub Actions remains authoritative. Focused regression tests cover the
current terminal shape, original-lineage preservation, old-shape compatibility,
unreviewed-key rejection, type rejection, dependency drift, and scoped runtime
installation/restoration. The full hosted `Tests` workflow must be green on the
exact PR head before review completion.
