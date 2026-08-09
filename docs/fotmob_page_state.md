# Offline FotMob page-state assessment

## Boundary and reviewed evidence

PR #35 preserved exact raw bytes from the transparently reachable FotMob date
page. Offline research then inspected the exact `450453`-byte capture for
`20260815`, whose SHA-256 is
`49323bb15db3edf101d9e7059254548a2eb04cff0f97622110b212f34a7f439f`.

The page contains 51 script elements: 48 external scripts, two inline
JavaScript blocks, and exactly one inline JSON script with the reviewed
identity:

```html
<script id="__NEXT_DATA__" type="application/json">...</script>
```

The visible server-rendered document is largely navigation, layout, and loading
placeholders. It contains no fixture IDs, home or away teams,
fixture-associated competitions, kickoff timestamps, fixture statuses, or
fixture URLs.

## Exact reviewed state path

The inert JSON payload contains the requested date at:

```text
query.date == "20260815"
```

Version 1 examines exactly one fixture-state path:

```text
props.pageProps.fallback["notableMatches:en:USA"].matches
```

For the reviewed capture, that value is exactly `[]`. The resulting assessment
is therefore:

```text
fixture_availability = NO_FIXTURE_DATA
match_count = 0
```

This means only that the reviewed server-rendered page state does not contain
fixture records in the reviewed container. It does **not** mean that no matches
were scheduled for that date.

## Fail-closed parsing

The assessor first requires exact PR #35 capture ancestry: dataset/schema,
canonical manifest SHA-256, raw SHA-256, raw byte size, observation timestamp,
and request date. The domain function receives bytes and a validated capture
manifest; it performs no filesystem or network work.

Verified HTML is decoded as strict UTF-8 and scanned inertly with Python's
standard-library `HTMLParser`. Exactly one inline
`script#__NEXT_DATA__[type="application/json"]` is mandatory. Duplicate
identity attributes, a `src`, an absent element, or multiple elements fail.
External scripts are neither opened nor retrieved.

The script content is decoded as strict JSON. Malformed JSON, duplicate object
keys, NaN, infinities, non-object top levels, date disagreement, missing path
components, changed types, or another locale key fail closed. There is no
recursive search for another `matches` key.

The only reviewed successful `matches` value is an empty list. A non-empty list
raises `non-empty FotMob notableMatches schema is unreviewed` before any element
is inspected. PR #36 does not extract IDs, teams, competitions, kickoffs,
statuses, or partial fixture candidates.

There is no DOM/CSS/ARIA/href/regex fallback, free-form JavaScript scan,
external chunk retrieval, script execution, API fallback, or translation-string
interpretation.

## Offline CLI

The command accepts only an offline capture directory and an allowed read root:

```text
python -m scripts.assess_fotmob_page_state \
  --allowed-root artifacts/source-captures/fotmob-date-page \
  --capture-directory artifacts/source-captures/fotmob-date-page/20260815/6bf27350edda7597d709187a
```

The allowed root must resolve below the ATHENA repository and contain no
symlink escape. The CLI first calls PR #35's
`verify_page_capture_directory(..., require_network_acquisition_performed=True)`.
It then performs a second regular-file read bounded at 8 MiB plus one byte,
rechecks raw size and SHA-256, and invokes the pure assessor. It writes no files
and prints exactly one canonical JSON assessment to stdout.

`--allowed-root` is an offline read boundary. It permits assessment of both the
normal ignored capture root and the preserved historical PR #35 location
without moving or modifying evidence. It is not an acquisition destination.

## Canonical artifact and safety

`athena-fotmob-page-state-assessment-v1` uses exact integer schema version 1.
Serialization is compact, sorted-key UTF-8 JSON with no NaN and a final LF. The
assessment anchors the canonical source manifest plus exact raw identity and
contains no HTML, localization payload, fixture fields, or model/pricing data.

Every safety flag is false. Assessment grants no authority for network access,
external asset retrieval, script execution, DOM fallback, fixture extraction,
source qualification, catalog promotion, intelligence, model features,
probabilities, pricing, selections, or betting.

## Upstream risks and non-goals

FotMob's Next.js schema is undocumented. Build IDs and hashed chunks change;
the reviewed notable-match key is locale/country-specific; notable matches may
not represent complete coverage; and server rendering may depend on later
client-side acquisition. Any changed key or non-empty match schema requires a
separate reviewed contract.

PR #36 performs no network request, retrieves no asset, executes no script,
and implements no fixture extraction. It does not call Fixture Catalog, create
Fixture Intelligence or model-feature records, calculate probabilities, obtain
bookmaker prices, rank/select markets, construct accumulators, or place bets.
`SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]` remains `UNKNOWN`.
