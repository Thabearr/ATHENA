# PR69 Primary Time-Basis Semantic Qualification V2

## Result

**State:** `EXECUTED_PRIMARY_EVIDENCE_ADMISSIBLE_DIRECT_TIME_BASIS_UNRESOLVED`

**Primary status:** `BLOCKED_NO_EXPLICIT_CSV_TIME_BASIS_OR_HISTORICAL_EFFECTIVE_SCOPE`

The reconciled V2 acquisition campaign succeeded and produced a complete, stable, provenance-bound primary evidence bundle. The evidence is now admissible for semantic review under the frozen PR122/PR124 rules. It still does **not** establish a deterministic source-local clock rule for the historical football-data.co.uk CSV `Time` field.

This qualification therefore narrows the blocker. The problem is no longer missing primary capture. The remaining problem is semantic: the captured primary bytes do not explicitly connect the CSV `Time` field to UTC, a fixed offset, a named timezone, or another deterministic civil-time rule, and they do not prove the effective historical period of such a rule across the exact 2020-21 through 2025-26 PR69 corpus.

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

The outer artifact digest was independently reproduced from the downloaded ZIP before semantic extraction. The package digest was independently reproduced from the preserved tar.

## Capture completeness

All eight frozen slots succeeded. Every A/B pair was byte-identical and every pair separation was within the frozen 300-3600 second window.

| Target | Raw SHA-256 | Size | A/B identical | Separation |
|---|---|---:|---|---:|
| `NOTES_TXT` | `6ecd41a98ad2751372817e7e6f1709bfeb433c53dd9aeda330fd926a5471452d` | 7,686 | yes | 317.882937s |
| `DATA_OVERVIEW` | `2dde0990feec3aa626c922f588a16897920061482c0e8b44f0644be91d1fc7ed` | 45,576 | yes | 318.093548s |
| `HISTORICAL_DOWNLOAD_OVERVIEW` | `94922a8099dd04983f72123da2f1afdacffa293032ce27e65eff6f852d7e50af` | 104,882 | yes | 318.213764s |
| `FIXTURES_OVERVIEW` | `62793b3461420db06c176e1fa6b1b55b0cde46f5846ff73bcd1e5ad89bf0365f` | 33,148 | yes | 318.093185s |

There was no capture drift to resolve.

## Admissible semantic findings

### `notes.txt`

The primary dictionary establishes:

- line 8 / bytes 448-476: `Date = Match Date (dd/mm/yy)`
- line 9 / bytes 478-507: `Time = Time of match kick off`

These statements are admissible primary field semantics. They prove what the fields represent. They do **not** define the timezone, offset, daylight-saving rule, or historical effective period of the `Time` value.

### `matches.php`

The primary fixture page establishes that the downloadable fixture list contains match dates and times. It also uses `British Standard Time` for the timing of odds collection and `UK time` for a fixture-upload timestamp.

Those statements are admissible primary **site-clock context**. Under the frozen PR124 contract, they cannot be promoted into the CSV `Time` field rule because the captured bytes never explicitly make that connection.

### Historical/data overview pages

The preserved pages establish dataset lineage and historical-download context, including links between historical downloads and the current notes dictionary. They do not state that the current field dictionary's unstated clock basis was unchanged across all six frozen PR69 seasons, and they do not provide an explicit timezone/offset/DST rule for historical `Time` values.

## Direct-route decision

The direct PR122 resolution route fails closed:

- explicit CSV timezone/offset/source-defined civil-time rule present: **false**
- explicit DST transition semantics present: **false**
- historical effective scope proven for 2020-21 through 2025-26: **false**
- relevant PR69 rows deterministically mapped: **0 / 21,226**
- unresolved PR69 rows: **21,226 / 21,226**

No country, league, venue, FotMob clock, result fit, search snippet, generic UK-time wording, or current-site convention is used to fill the gap.

A primary-source web discovery pass was also performed after reviewing the artifact. It did not find an explicit official statement tying historical CSV `Time` values to a clock rule. Those search results are **not** included as qualification evidence because they were not part of the frozen preserved V2 bundle.

## Formal invariance route

The formal invariance route is **not executed by this PR**. PR122 requires its assumptions to be proven from admissible evidence and requires every PR80 time-sensitive operation to be covered. The present evidence does not yet bound the unknown PR69 clock transformation tightly enough to claim that proof without adding a separately pre-registered protocol.

## Strategic consequence

PR69 remains a valid, frozen historical research lineage, but its unresolved source-local clock should no longer be allowed to hold the entire successor programme hostage.

The next reviewed product path should therefore pre-register a **FotMob-native successor feature time basis** that uses FotMob's already-qualified canonical UTC history directly, preserves the six conceptual pre-match features, and validates a new successor model without claiming PR69/PR80 source-local equivalence. A separate PR69 invariance route can still be pursued later if worthwhile.

This is not a silent rewrite of PR80 and does not retroactively authorize PR80 inputs. It is a new reviewed successor path intended to remove an external legacy-source ambiguity from the critical path.

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

Canonical receipt SHA-256: `9676fce4ecf755a85022d74a6514c8dd395cb8e1f204f588a2917bf28d8f6e48`

Canonical receipt size: `5,443` bytes.
