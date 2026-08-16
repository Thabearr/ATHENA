# PR69 Primary Time-Basis Semantic Qualification V2

## Result

**State:** `EXECUTED_PRIMARY_EVIDENCE_ADMISSIBLE_DIRECT_TIME_BASIS_UNRESOLVED`

**Primary status:** `BLOCKED_TIME_BASIS_SCOPE_OR_EFFECTIVE_PERIOD_AMBIGUOUS`

The reconciled V2 acquisition campaign succeeded and produced a complete, stable, provenance-bound primary evidence bundle. The evidence is now admissible for semantic review under the frozen PR122/PR124 rules. It still does **not** establish a deterministic source-local clock rule for the historical football-data.co.uk CSV `Time` field.

The blocker has therefore narrowed. Primary capture is no longer missing. The remaining direct-route problem is that the captured primary bytes do not explicitly connect the CSV `Time` field to UTC, a fixed offset, a named timezone, or another deterministic civil-time rule, and they do not prove the effective historical period of such a rule across the exact 2020-21 through 2025-26 PR69 corpus.

The primary status above is taken from PR122's pre-registered qualification vocabulary. No result-specific blocker vocabulary is invented after observing V2.

## Exact execution lineage

- authorized `main`: `4a2ca10af4b14194253ba6fc84bca780e2b03d58`
- V2 GitHub Actions run: `31974333489`
- V2 artifact ID: `9270750452`
- V2 artifact name: `pr69-primary-time-basis-evidence-campaign-v2-31974333489`
- V2 artifact SHA-256: `186188a0cec4e3febc8971c0f69eb1feb7dec6d2f35052ce48d2913c37265a6c`
- V2 artifact size: `428,972` bytes
- preserved evidence tar SHA-256: `2212663bece44296494a0aff1edbdb1574e940685588f73829ac80f58a6791c5`
- preserved evidence tar size: `419,840` bytes
- PR122 semantic protocol SHA-256: `d3bf061ade81bb1b60f38e98f5fa3c8c21ba5bf6652879f2cc19e151b53aee4a`
- PR124 acquisition protocol SHA-256: `28ec0a0208858ce3258a584bad1361577a0e202e5cbdb8eb9b13cdd47d7455a3`
- PR123 prior blocked receipt SHA-256: `a3736753862781efc9d8ce6c15aa814185b73ed14fea82c4e8ebaa10a3ab656c`

The GitHub artifact metadata independently reports the exact artifact digest, size, run ID, branch and authorized main SHA above. The preserved evidence tar digest is frozen separately inside the V2 package.

## Capture completeness

All eight frozen slots succeeded. Every A/B pair was byte-identical and every pair separation was within the frozen 300-3600 second window.

| Target | Raw SHA-256 | Size | A/B identical | Separation |
|---|---|---:|---|---:|
| `NOTES_TXT` | `6ecd41a98ad2751372817e7e6f1709bfeb433c53dd9aeda330fd926a5471452d` | 7,686 | yes | 317.882937s |
| `DATA_OVERVIEW` | `2dde0990feec3aa626c922f588a16897920061482c0e8b44f0644be91d1fc7ed` | 45,576 | yes | 318.093548s |
| `HISTORICAL_DOWNLOAD_OVERVIEW` | `94922a8099dd04983f72123da2f1afdacffa293032ce27e65eff6f852d7e50af` | 104,882 | yes | 318.213764s |
| `FIXTURES_OVERVIEW` | `62793b3461420db06c176e1fa6b1b55b0cde46f5846ff73bcd1e5ad89bf0365f` | 33,148 | yes | 318.093185s |

There was no A/B capture drift to resolve.

## Admissible semantic findings

### `notes.txt`

The captured primary dictionary establishes:

- line 8 / bytes 448-476: `Date = Match Date (dd/mm/yy)`
- line 9 / bytes 478-507: `Time = Time of match kick off`

These statements prove what the two fields represent. They do **not** define the timezone, offset, daylight-saving rule, or historical effective period of the `Time` value. PR124 explicitly pre-registered that `Time = Time of match kick off` is insufficient by itself to establish those clock semantics.

### `matches.php`

The captured fixture page establishes that its downloadable fixture list contains match dates and times. It also contains:

- line 183 / bytes 13753-13774: `British Standard Time`
- line 194 / bytes 14268-14317: `Latest fixtures uploaded: 14/08/26 11:26 UK time.`

Those statements are admissible primary **site-clock context** only. PR124 explicitly pre-registered that UK/BST site wording cannot be promoted into the CSV `Time` rule unless the primary bytes explicitly make that connection. They do not.

### Historical/data overview pages

The preserved data and historical-download pages establish current dataset lineage/context. They do not prove that an unstated clock basis was unchanged across all six frozen PR69 seasons, and they do not provide a deterministic historical timezone/offset/DST rule for the CSV `Time` values.

## Direct-route decision

The direct PR122 resolution route fails closed:

- explicit CSV timezone/offset/source-defined civil-time rule present: **false**
- explicit DST transition semantics present: **false**
- historical effective scope proven for 2020-21 through 2025-26: **false**
- relevant PR69 rows deterministically mapped: **0 / 21,226**
- unresolved PR69 rows: **21,226 / 21,226**

No country, league, venue, FotMob clock, result fit, search snippet, generic UK-time wording, or current-site convention is used to fill the gap.

## Formal invariance route

PR122 pre-registered a second route if direct primary semantics cannot be recovered: formal operational invariance across every admissible reference transformation, with the assumptions themselves proven and every PR80 time-sensitive operation covered.

That route is **required next under the PR122 lineage but is not executed by this qualification**. No invariance result is inferred from equal observed feature outputs or from the V2 primary capture.

**Next PR122 boundary:** `PRE_REGISTER_REVIEWED_PR69_FORMAL_OPERATIONAL_INVARIANCE_QUALIFICATION_PROTOCOL`

## Parallel product work is separate

This qualification does not prevent ATHENA from opening a separate, explicitly pre-registered FotMob-native successor lineage that uses already-qualified FotMob UTC history. Such a path would be a new reviewed product/model lineage; it would **not** resolve PR69, retroactively authorize PR80, or count as execution of the PR122 invariance route.

Keeping those lines separate allows product progress without rewriting the frozen historical evidence result.

## Safety

All downstream authority remains false:

- PR69 source-local time basis resolved: false
- FotMob/PR69 source-local semantic equivalence qualified: false
- PR80 constructor input authorized: false
- model training authorized: false
- expected-goals production authorized: false
- score matrix authorized: false
- probability inference authorized: false
- pricing authorized: false
- selection authorized: false
- production approval authorized: false
- BET authorized: false

## Canonical receipt

`artifacts/research-manifests/pr69-primary-time-basis-semantic-qualification-v2.json`

Canonical receipt SHA-256: `cbdf0bbf9e31d44e0d00125bd10d714272ac6046386cf52f1d9d27b3ab84bb8d`

Canonical receipt size: `5,422` bytes.
