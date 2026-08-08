# Controlled FotMob matches capture

## Purpose

PR #32 introduces ATHENA's first explicitly reviewed live network-acquisition
seam. It is deliberately narrower than a general FotMob client:

```text
one fixed HTTPS request
    -> exact raw response bytes
    -> SHA-256 evidence anchor
    -> strict structural validation
    -> UNREVIEWED fixture candidates
    -> future human/source review
    -> possible later fixture-catalog promotion
```

FotMob remains an unofficial, undocumented public-web source. A successful
request proves only that ATHENA received particular bytes from the fixed
resource at a recorded time. It does not make a fixture or fact trusted and
does not change the `fotmob_unofficial` capability registry from `UNKNOWN`.

## Authorized network surface

Version 1 authorizes only:

```text
GET https://www.fotmob.com/api/matches?date=YYYYMMDD
```

The host, HTTPS port 443, path, query key, transparent `ATHENA/1.0` user agent,
and JSON accept header are fixed internally. The date must be exactly eight
ASCII digits and a real Gregorian date. The CLI requires the explicit
`--execute-live-network` flag; ordinary invocation does not open a socket or
perform DNS or HTTP work.

No `matchDetails`, team, league, player, search, news, odds, alternate-domain,
mobile, or private endpoint is authorized by PR #32. There is no arbitrary URL
requester.

The transport uses Python's normal `http.client.HTTPSConnection`, default
certificate verification, and no automatic redirects. It does not use:

- Cloudflare bypasses;
- browser or TLS fingerprint impersonation;
- Playwright or Selenium;
- curl or shell HTTP commands;
- rotating proxies, proxy services, or IP rotation;
- cookies or reusable browser sessions;
- credentials, API keys, bearer tokens, or referer spoofing; or
- legacy FotMob provider, loader, advanced-scraper, or bypass workers.

The request is attempted once. Failure is evidence of failure; the tool does
not retry, change endpoints, or fall back to an evasion technique.

## Response and raw-evidence contract

The response must be HTTP 200 with media type `application/json` (case
insensitive; parameters such as `charset=utf-8` are allowed). HTML and plain
text, including challenge pages, fail closed. The hard response limit is 16
MiB. A supplied `Content-Length` must be a strict non-negative integer and may
not exceed the limit, and the transport independently reads at most 16 MiB plus
one byte.

Exact response bytes are preserved as `response.json` before their semantic
contents are trusted. They are never pretty-printed, decoded/re-encoded, or
silently repaired. SHA-256 is calculated over those exact bytes.

Strict UTF-8 JSON parsing rejects duplicate object keys, NaN, positive or
negative infinity, malformed JSON, a non-object top level, a missing `leagues`
field, or a non-list `leagues` value. Additional upstream fields are permitted
because this public-web response is undocumented and may evolve.

## Fixture candidates and rejections

Candidates use only explicit source values:

- exact positive integer `match.id`, represented as `FOTMOB:<id>`;
- `league.name`;
- `match.home.name`;
- `match.away.name`; and
- timezone-aware `match.status.utcTime`, normalized to UTC.

Names must be non-empty, unpadded strings of at most 256 characters. There are
no `Unknown Home`, `Unknown Away`, or `Unknown League` placeholders, and no
kickoff fallback or current-time substitution. A malformed match becomes a
deterministic indexed rejection rather than a fabricated candidate.

Every candidate has `review_status = UNREVIEWED`. Network acquisition is not
human/source qualification. The candidate JSON Lines intentionally does not
match the reviewed input contract of `domain.fixture_catalog`: it has no
`reviewed_at`, and the extra review status makes its non-promoted state
explicit. This code does not call `compile_fixture_catalog` or write
`future-fixtures.json`.

## Capture directory and durability

Real artifacts are restricted to the ignored root:

```text
.cache/athena-research/fotmob-captures/
```

Each successful capture creates a unique directory:

```text
YYYYMMDD/YYYYMMDDTHHMMSSffffffZ-<first12-payload-sha>/
    response.json
    fixture-candidates.jsonl
    manifest.json
```

Absolute aliases outside that root, traversal, symlinked destinations, and
symlinked parent components are rejected. Existing capture directories are
never overwritten.

New directory entries are synchronized after creation. Each file is written to
a transaction-owned temporary file in the capture directory, its contents are
flushed and `fsync`-ed, and its final name is atomically published without
replacement through a same-filesystem hard link. The containing directory is
synchronized after final publication and again after the temporary name is
removed. If hard-link publication is unavailable or the final name already
exists, capture fails closed; there is no overwrite-capable fallback. Raw
evidence is published first, candidates second, and the manifest last. Thus a
manifest is not published before its referenced files. This is per-file
durability only; no cross-file crash atomicity is claimed.

Normal handled failure attempts to remove only files and directories owned by
that transaction. Ownership is recorded only after this transaction
successfully creates a directory or temporary file, and final-file ownership
is recorded only after successful publication. Expected basenames do not prove
ownership: a concurrent race winner's directory, temporary file, final file,
or other foreign content is never enumerated or removed by rollback. Cleanup
failures are never silently ignored: the reported error preserves the original
operation failure and identifies every owned path whose cleanup could not be
completed. Unrelated and sibling files are not removed.

The manifest records the network-acquisition provenance asserted by the
validated transport receipt. A live transport receipt records `true`; a
manual/offline receipt records `false`, and the persistence writer propagates
that state rather than inventing it. Every scraping, browser, credential,
pricing, model, market, selection, production, and betting safety flag remains
false.

## CLI

One explicitly authorized live capture:

```powershell
python -m scripts.capture_fotmob_matches `
  --date 20260808 `
  --output-root .cache/athena-research/fotmob-captures `
  --execute-live-network
```

Offline verification:

```powershell
python -m scripts.capture_fotmob_matches `
  --check-capture .cache/athena-research/fotmob-captures/20260808/<capture-directory>
```

Check mode verifies the exact required files, non-symlink raw evidence,
payload size and SHA, strict JSON, regenerated canonical candidate JSON Lines,
candidate/rejection counts and ordering, canonical manifest bytes, and
date/source-reference consistency. It never uses the network, even when the
machine has connectivity. This proves byte, schema, and internal consistency;
offline verification alone is not independent proof that an Internet request
actually occurred. Check mode and live execution cannot be combined.

## Architectural separation

A fixture candidate does not automatically enter Fixture Catalog. It does not
create `FixtureIntelligenceFact`, `FixtureIntelligenceSnapshot`, or
`FixtureModelFeatureSnapshot`, and it cannot reach any probability model.
SportyBet remains entirely separate as a candidate bookmaker/pricing source.

PR #32 performs no form, ELO, injury, xG, fatigue, or freshness calculation;
no probability inference or adjustment; no odds collection, expected value,
Kelly sizing, market ranking, selection, accumulator construction, or betting.

Future reviewed PRs may separately define:

- human/source-reviewed promotion into the fixture catalog;
- a separately authorized match-detail acquisition boundary; and
- reviewed football-context extraction into fixture intelligence.

None of those later steps is implied or authorized by one successful capture.
