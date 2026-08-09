# Transparent FotMob data-matches route qualification probe

PR #37 adds a narrow diagnostic boundary for one question: does FotMob's
client-discovered `/api/data/matches` route respond to an independent,
transparent ATHENA request that does not reproduce FotMob's signed application
marker?

PR #35 preserved the exact public date-page HTML. PR #36 then established that
the reviewed server-rendered `__NEXT_DATA__` container held an empty
`notableMatches:en:USA.matches` list and therefore supported only the conclusion
`NO_FIXTURE_DATA`. It did not prove that no matches were scheduled.

Subsequent read-only static analysis identified the client fixture-list route as
`/api/data/matches`, not the older `/api/matches` route. It also established the
ordered required query parameters and the client's serialization behavior:

1. `date`
2. `timezone`
3. `ccode3`

The web client builds an ordered object, removes only undefined values, and
serializes it with `URLSearchParams`. PR #37 uses Python's standard
`urllib.parse.urlencode` over the fixed ordered tuple, which gives compatible
form encoding for the contract's validated strings. For example:

```text
/api/data/matches?date=20260815&timezone=UTC&ccode3=NGA
```

`America/New_York` serializes as `America%2FNew_York`. The optional client
parameter `includeNextDayLateNight` is deliberately outside this qualification
probe and cannot be supplied through its API or CLI.

## Deliberately unsigned transparent profile

Static analysis established that FotMob's web application normally creates an
application-specific signed `x-mas` header. ATHENA PR #37 deliberately does not
reproduce that mechanism. It contains no signing algorithm, embedded signing
constant, MD5 construction, timestamp signature, or Base64 envelope, and it
never sends `x-mas`.

Failure without x-mas is evidence about transparent accessibility, not a reason
to emulate the web client's signed request marker.

The only authorized route is an HTTPS GET to `www.fotmob.com:443` with the fixed
base path `/api/data/matches` and the three validated ordered parameters. The
only explicit request headers are:

```text
Accept: application/json
User-Agent: ATHENA/1.0
```

The standard-library transport uses low-level `HTTPSConnection.putrequest` with
`skip_accept_encoding=True`. `Host` is generated normally. No `Accept-Encoding`,
Referer, Cookie, Authorization, Accept-Language, Origin, connection override,
browser user agent, browser client-hint header, `fotmob-client`, proxy, custom
header, or arbitrary URL is supported.

Network execution is fail-closed behind `--execute-live-network`. One invocation
issues exactly one request. Redirects are recorded but never followed. HTTP
failures and transport failures do not trigger retries, alternate endpoints,
changed headers, cookies, browser emulation, or a signed retry. In particular,
401, 403, and 404 are valid qualification observations.

## Diagnostic receipt only

The canonical dataset is `athena-fotmob-data-matches-probe-v1`, with exact
integer schema version `1`. Its immutable receipt records the exact date,
timezone, country code, host, target, request-header tuple, explicit
`x_mas_included: false`, response metadata, observation time, and the size and
SHA-256 of at most the first 4096 response bytes.

The response body is never decoded, parsed, printed, or persisted. The bounded
sample is not fixture evidence and does not establish a response schema. A
transport-error receipt contains no raw exception message or HTTP metadata.
Canonical serialization is compact UTF-8 JSON with sorted keys and a final
newline.

HTTP 200 with an `application/json` media type means only: **the transparent
route produced a JSON response**. It does not qualify FotMob, trust fixtures,
authorize capture, or approve production acquisition. A refusal or missing
route is equally useful evidence about the unsigned profile.

Every canonical safety flag remains exact Boolean `false`. The operator's live
flag authorizes one diagnostic request only; it grants no continuing network,
capture, parsing, promotion, intelligence, model, probability, pricing,
selection, or betting authority.

## Architecture boundary

This probe does not persist complete fixture JSON, inspect fixture elements,
extract match identifiers, teams, competitions, kickoffs, statuses, or URLs, or
produce fixture candidates. It does not call the Fixture Catalog, Fixture
Intelligence, model-feature, prediction, pricing, selection, accumulator, or
betting layers.

`SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]` therefore remains entirely
`UNKNOWN`. A future reviewed change may decide whether a successful transparent
JSON response warrants a raw-byte capture boundary. PR #37 itself makes no such
promotion.
