# Controlled FotMob date-page capture

## Purpose and evidence boundary

PR #33 proved that the ordinary public FotMob date webpage was transparently
reachable: `GET /?date=20260815` returned HTTP 200 and HTML, while the equivalent
transparent JSON matches API request returned HTTP 404 and HTML. PR #35 therefore
adds a controlled raw capture boundary for the public date webpage only.

```text
truthful public date page
    -> one controlled HTTPS request
    -> exact raw HTML bytes
    -> SHA-256 and canonical provenance manifest
    -> offline consistency verification
    -> future separately reviewed extraction
```

Raw capture is evidence preservation, not evidence qualification. A successful
capture does not qualify FotMob, trust any content, or authorize downstream use.
`SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]` remains `UNKNOWN`.

## Exact network profile

Version 1 fixes every network dimension internally:

```text
GET /?date=YYYYMMDD HTTP/1.1
Host: www.fotmob.com
Accept: text/html,application/xhtml+xml
User-Agent: ATHENA/1.0
```

The standard-library `http.client.HTTPSConnection` uses port 443 and default TLS
certificate verification. `Host` is generated normally. The transport calls
`putrequest(..., skip_accept_encoding=True)` so Python does not insert
`Accept-Encoding: identity`; only the listed `Accept` and transparent ATHENA
user agent are emitted explicitly. Behavioral tests inspect the raw request
bytes produced by the real standard-library serializer.

There is no arbitrary URL, host, path, query, header, user-agent, or proxy input.
The exact `YYYYMMDD` value must be eight ASCII digits and a valid Gregorian date.
There is one request per explicitly authorized CLI invocation, no redirect
following, no retry, and no fallback. The implementation uses no Referer,
cookies, credentials, Authorization, Accept-Language, browser impersonation,
browser automation, TLS fingerprinting, proxy, `requests`, `httpx`, `curl_cffi`,
Playwright, or Selenium.

The CLI requires `--execute-live-network`; without it there is no connection,
DNS, socket, or HTTP work. That flag authorizes one operator-requested capture,
not blanket future acquisition. Consequently every canonical safety flag,
including `network_acquisition_authorized` and `html_capture_authorized`, remains
false.

## Raw response and provenance

Capture requires exact HTTP 200 and MIME base type `text/html`; parameters such
as `charset=utf-8` are retained. JSON, plain text, redirects, client errors, and
server errors fail closed. The hard limit is 8 MiB. Oversized `Content-Length`
fails before body acquisition, and incremental reads independently enforce the
same limit.

`page.html` is the exact non-empty response body. It is never decoded,
line-ending-normalized, stripped, pretty-printed, parsed, or rewritten. SHA-256
and size are calculated from those exact bytes. Non-UTF-8 sequences remain raw
transport evidence rather than being silently repaired.

The immutable `CapturedFotMobPageResponse` records exact response metadata,
UTC observation time, raw bytes, and explicit network provenance. The writer
revalidates and propagates that provenance; it never turns an offline/manual
response into a network capture.

## Capture layout and transaction safety

Local captures use:

```text
artifacts/source-captures/fotmob-date-page/
    YYYYMMDD/
        <24-character deterministic capture id>/
            page.html
            manifest.json
```

The identifier is derived from the request date, normalized observation time,
and raw SHA-256. Existing captures are never overwritten. Absolute aliases,
traversal, root escape, and symlink components fail closed.

Transaction ownership is explicit. A directory or temporary file becomes owned
only after this transaction creates it; a final file becomes owned only after
successful publication. Each file is exclusively created as a temporary file,
flushed and `fsync`-ed, then atomically published without replacement using a
same-filesystem hard link. The containing directory is synchronized after link
publication and again after the owned temporary name is removed. If hard links
or required directory synchronization are unavailable, capture fails closed.
No overwrite-capable fallback and no cross-file crash atomicity are claimed.

Rollback deletes only explicitly owned artifacts. Race winners, pre-existing
deterministic names, sibling captures, foreign temporary files, and concurrently
arriving foreign files are preserved. Cleanup attempts all safe owned removal;
incomplete cleanup reports the original failure, each cleanup failure, and the
affected owned paths.

## Canonical manifest and offline verification

`manifest.json` is deterministic compact UTF-8 JSON with sorted keys, no NaN,
stable UTC timestamps, and a final LF. It records request profile, response
metadata, network provenance, `page.html` name, raw size/SHA, and the exact
all-false safety mapping. It never contains HTML text, a DOM, fixture or team
data, match IDs, model data, or odds.

Offline verification performs no network. It validates allowed-root containment,
symlinks, the exact two files, canonical manifest schema and bytes, directory
date and deterministic identifier, request profile, response metadata, raw size
and SHA, provenance policy, and safety mapping. Requiring network provenance
rejects internally constructed offline artifacts. Offline verification proves
byte/schema/hash consistency; it does not independently prove that a network
request occurred.

## Explicit non-goals

PR #35 does not parse HTML or inspect `__NEXT_DATA__`, scripts, JSON embedded in
HTML, team names, match IDs, or kickoff values. It uses no BeautifulSoup, lxml,
`html.parser`, DOM tooling, or regex fixture extraction. It produces no fixture
candidates and performs no Fixture Catalog promotion.

It does not create Fixture Intelligence facts or model features, calculate
probabilities, acquire bookmaker odds, price markets, calculate value or Kelly,
rank or select markets, build accumulators, or place bets. A future PR must
separately review any extraction from the preserved raw evidence.
