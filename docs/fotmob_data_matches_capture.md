# Controlled FotMob data-matches raw capture

## Purpose and evidence boundary

PR #37 established that the client-discovered `/api/data/matches` route is
reachable under an independent transparent ATHENA profile. The reviewed request
returned HTTP 200 with `application/json; charset=utf-8`, while deliberately
omitting FotMob's application-specific signed `x-mas` marker. PR #38 preserves
the complete response bytes from that same fixed profile so a later PR can
qualify the schema offline.

```text
transparent reviewed /api/data/matches request
    -> exact bounded HTTP body bytes
    -> response.json
    -> SHA-256 and canonical provenance manifest
    -> bounded offline integrity verification
    -> future separately reviewed schema qualification
```

Raw JSON capture establishes preserved transport evidence, not trusted fixture
semantics. HTTP 200 and a JSON media type do not qualify FotMob, trust any
field, or authorize downstream use. The `fotmob_unofficial` capability registry
therefore remains `UNKNOWN`.

## Exact unsigned request profile

Version 1 fixes every network dimension internally:

```text
GET /api/data/matches?date=YYYYMMDD&timezone=TIMEZONE&ccode3=CCC HTTP/1.1
Host: www.fotmob.com
Accept: application/json
User-Agent: ATHENA/1.0
```

Date, timezone, country code, ordered query serialization, host, port, target,
and request headers reuse the merged PR #37 contract. The standard-library
`http.client.HTTPSConnection` uses port 443 and default TLS verification. It
uses low-level `putrequest(..., skip_accept_encoding=True)` while allowing
`http.client` to generate `Host` normally.

The transport never sends `x-mas`, Referer, Cookie, Authorization,
Accept-Language, Accept-Encoding, Origin, Connection, browser client hints,
`fotmob-client`, `X-Requested-With`, or a browser user agent. It exposes no
arbitrary URL, host, header, user-agent, proxy, late-night parameter, or
alternate route. One explicitly gated invocation makes exactly one request;
there are no redirects, retries, fallbacks, browser attempts, or signed retries.

Static investigation established that FotMob's web client normally creates a
signed `x-mas` marker. ATHENA does not reproduce its algorithm, constant, MD5
construction, timestamp material, or Base64 envelope. PR #38 preserves only the
response available to the transparent independent ATHENA request.

## Exact raw-byte preservation

Capture requires exact HTTP 200 and MIME base type `application/json`.
Parameters such as `charset=utf-8` are retained. Redirects and all other status
codes fail closed. The response limit is 8 MiB. An oversized Content-Length is
rejected before the body is read, and incremental reads independently enforce
the same maximum plus one-byte overflow check. Empty bodies and mismatched
Content-Length values fail.

`response.json` is the exact response body. It is never decoded, parsed,
pretty-printed, stripped, normalized, line-ending-adjusted, or rewritten.
Consequently even non-UTF-8 bytes remain exact transport evidence rather than
being silently repaired. PR #38 does not call `json.loads` on this file, inspect
top-level objects, leagues, matches, IDs, teams, competitions, kickoffs, or any
other potential fixture field. PR #39 owns any future offline schema review.

The immutable receipt records status, media type, optional Content-Length, exact
body bytes, UTC observation time, and explicit network provenance. The writer
revalidates and propagates that provenance; an offline receipt is never upgraded
to claim network acquisition.

## Ignored capture layout

Captures use the repository's existing ignored research namespace:

```text
.cache/athena-research/fotmob-data-matches-captures/
    YYYYMMDD/
        <24-character deterministic capture id>/
            response.json
            manifest.json
```

The identifier is derived from the request date, timezone, country code,
normalized observation time, and raw SHA-256. This root is covered by the
existing `.cache/athena-research/` ignore rule, keeping raw live evidence out of
normal Git staging. Production code does not invoke Git.

## Transaction ownership and durability

Directory and file ownership is explicit. A date or capture directory becomes
transaction-owned only after this transaction successfully creates it. A
temporary file becomes owned only after exclusive `xb` creation; a final file
becomes owned only after successful atomic no-overwrite publication.

Each file is written to a same-directory temporary name, flushed and `fsync`ed,
then published with `os.link(temp, final)`. Hard-link publication fails if a
foreign final already exists. The containing directory is synchronized after
publication and again after removing the owned temporary name. Parent and child
directories are synchronized after directory publication using the reviewed
POSIX/Windows fail-closed mechanism. If hard links or directory synchronization
cannot be proven, capture fails without an overwrite fallback. No cross-file
crash atomicity is claimed; `manifest.json` is published last.

Rollback deletes only explicitly owned artifacts. It never guesses ownership
from deterministic names and never removes race winners, sibling captures,
foreign temporary/final files, or unrelated date-directory content. Cleanup
attempts all safe owned removal. If cleanup is incomplete, the original failure,
each cleanup failure, and each affected owned path are reported.

## Canonical manifest and offline verification

`manifest.json` is compact UTF-8 JSON with sorted keys, `allow_nan=False`, stable
UTC timestamps, and a final LF. It records the exact request profile, explicit
`x_mas_included: false`, response metadata, provenance, filename, raw size and
SHA-256, and the exact all-false safety mapping. It contains no response body,
sample, fixture schema, match data, model input, probability, price, or bet.

Strict manifest loading rejects invalid UTF-8, malformed JSON, duplicate keys,
NaN or infinities, non-object top levels, wrong/missing/extra fields, altered
headers, changed safety flags, and changed request identity. This strict JSON
handling applies only to ATHENA's small `manifest.json`; it never parses
`response.json`.

Offline verification performs zero network work. It enforces root containment,
rejects symlinks, requires exactly `response.json` and `manifest.json`, rebuilds
the target and deterministic ID, and verifies canonical manifest bytes, exact
raw size, SHA-256, response metadata, provenance policy, and safety. Raw reads
are bounded at 8 MiB plus one byte; manifest reads are bounded at 64 KiB plus one
byte, covering both apparent oversize and stat/read growth races.

Offline verification proves filesystem, schema, hash, and internal provenance
consistency. It does not independently prove that a network event occurred.

## Explicit non-goals

PR #38 creates no fixture candidate or source schema. It performs no fixture
parsing or extraction and makes no Fixture Catalog promotion. It creates no
Fixture Intelligence fact or model feature and performs no probability,
bookmaker pricing, value, Kelly, ranking, selection, accumulator, or betting
behavior. Every canonical authorization flag remains exact Boolean `false`; the
live gate authorizes only one operator-requested capture.
