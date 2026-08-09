# Transparent FotMob source-route qualification probe

PR #33 adds ATHENA's deliberately narrow observation instrument for answering
one question: which reviewed public FotMob route, if any, responds to a
truthful, transparent HTTP client? It does not replace the raw-evidence capture
boundary added by PR #32.

PR #32 made one transparent request to
`https://www.fotmob.com/api/matches?date=20260808` and received HTTP 404. Public
third-party documentation current in March 2026 still describes
`/api/matches?date=YYYYMMDD` as the single-day matches endpoint. Some third-party
clients use browser-like user agents and a FotMob `Referer`; ATHENA deliberately
does not copy browser impersonation, referer spoofing, cookies, browser sessions,
TLS fingerprint spoofing, proxies, credentials, or private/mobile endpoints.

## Exact v1 routes and request profiles

One process invocation may probe exactly one of these fixed HTTPS routes on
`www.fotmob.com:443`:

| Route ID | Fixed target | Exact headers | Expected media |
|---|---|---|---|
| `matches_api` | `/api/matches?date=YYYYMMDD` | `User-Agent: ATHENA/1.0`; `Accept: application/json` | JSON |
| `date_web_page` | `/?date=YYYYMMDD` | `User-Agent: ATHENA/1.0`; `Accept: text/html,application/xhtml+xml` | HTML |

The date must be an exact, valid Gregorian `YYYYMMDD` value. Host, port, path,
query, and headers are internal constants. There is no arbitrary URL, header,
proxy, or alternate-host input. Requests use Python's standard
`http.client.HTTPSConnection` and default TLS certificate verification. The
probe explicitly suppresses `http.client`'s automatic
`Accept-Encoding: identity` insertion. `Host` is generated normally by
`http.client`; the only explicit request-profile headers are the route's
`Accept` value and `User-Agent: ATHENA/1.0`. Behavioral tests inspect the raw
request header bytes serialized by the standard-library client. The probe
follows no redirect and performs no retry. The operator must run the two routes
as separate commands.

Network use is fail-closed behind `--execute-live-network`. Invoking the CLI
without that flag creates no connection and performs no DNS or socket work. The
flag authorizes one diagnostic request only; it does not authorize capture,
scraping, promotion, intelligence, modelling, pricing, selection, or betting.

## Diagnostic receipt, not evidence capture

The canonical dataset is `athena-fotmob-source-probe-v1`, with exact integer
schema version `1`. A response receipt records the fixed route and request
profile, status, bounded response headers, observation time, and a fingerprint
of at most the first 4096 body bytes. It never stores or prints the body, parses
fixtures, inspects embedded page data, or persists raw response data. A
transport-error receipt contains no raw exception message or response fields.

The sample SHA-256 is only a diagnostic fingerprint. It is not equivalent to
PR #32's exact raw-byte preservation and cannot be used as fixture evidence.
HTTP 200 with the expected media type means only that a transparent route
appears reachable. It does not establish source qualification, schema
qualification, fixture trust, production acquisition authority, or downstream
authority.

Every receipt keeps all safety flags at exact Boolean `false`, including
`source_qualified`, fixture promotion, intelligence, model feature,
probability, pricing, selection, and betting authorization. The
`fotmob_unofficial` entry in `domain/source_capabilities.py` therefore remains
`UNKNOWN`; this PR does not modify that registry.

## Architecture boundary

The probe produces a canonical diagnostic receipt for operator and code review.
It does not call PR #32's capture writer, preserve raw bodies, create fixture
candidates, or modify any PR #32 file. It cannot promote fixtures into the
Fixture Catalog and cannot create `FixtureIntelligenceSnapshot` or
`FixtureModelFeatureSnapshot` data. It adds no probability, odds, pricing,
expected-value, Kelly, ranking, selection, accumulator, or betting behavior.
SportyBet and all bookmaker concerns remain separate.

## Interpreting the two reviewed observations

- **API 200 plus JSON:** the current API route appears transparently reachable.
  Review why the PR #32 observation differed before considering a separately
  reviewed capture integration change.
- **API non-200 plus web page 200 plus HTML:** the transparent public webpage is
  reachable while the JSON endpoint is not. A later PR may define a dedicated
  raw webpage capture and extraction boundary; this probe does not parse it.
- **Both non-200 or transport failure:** direct transparent FotMob acquisition
  is not presently usable. Do not bypass the result; reconsider the source
  strategy.

No live result changes PR #33's code or qualifications. A successful request is
an observation, not trust.

The corrected live observations made with automatic `Accept-Encoding`
insertion suppressed supersede PR #33's initial observations. Those initial
observations used the same truthful explicit headers, but the standard library
added an implicit wire header that was not represented in the canonical
receipt.
