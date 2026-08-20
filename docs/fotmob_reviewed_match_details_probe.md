# Reviewed FotMob match-details diagnostic probe

## Purpose

PR #49 is the first richer FotMob surface allowed to consume the reviewed fixture-identity chain.

The path is now:

```text
verified PR #38 raw fixture-list capture
→ PR #39 schema assessment
→ PR #40 UNREVIEWED candidates
→ PR #41 explicit review
→ PR #42 handoff
→ PR #43 controlled catalog compile
→ PR #44 reviewed identity-only capability
→ PR #45 catalog admission
→ PR #46 admission artifact verification
→ PR #47 Fixture Intelligence identity bootstrap
→ PR #48 bootstrap artifact verification
→ PR #49 transparent one-request match-details diagnostic probe
```

PR #49 does **not** parse football data. It determines only whether one exact reviewed fixture identity can be used in one transparent request to FotMob's match-details route and records bounded transport evidence.

## Fixed route

The only reviewed target in this PR is:

```text
https://www.fotmob.com/api/data/matchDetails?matchId=<positive decimal source match id>
```

The source match id is not supplied independently. It is derived from an exact source-scoped fixture identifier already present in the exact PR #48 receipt:

```text
FOTMOB:1001 → matchId=1001
```

No aliasing, fuzzy matching, team-name matching, global identity resolution, or caller-provided alternate source id is allowed.

### 2026-08-20 transparent route migration

A hosted transparent diagnostic for the exact reviewed Saturday fixture observed the historical `/api/matchDetails` route return HTTP 404 while `/api/data/matchDetails` returned HTTP 200 with `application/json; charset=utf-8`. The live builder therefore emits only the `/api/data/matchDetails` route for new requests. Pre-migration `/api/matchDetails` plans remain revalidatable only when their exact `request_started_at` predates `2026-08-20T19:42:27Z`, preserving historical audit without permitting the obsolete route for new acquisition. This migration changes transport location only; it grants no football semantics or downstream authority.

## Exact upstream gate

`build_match_details_probe_plan(...)` requires:

1. an exact `VerifiedReviewedFixtureIntelligenceBootstrapArtifact` from PR #48;
2. the exact canonical PR #48 receipt bytes;
3. an exact fixture identifier present once in that receipt;
4. an exact UTC request start time.

The PR #48 object is reconstructed with `dataclasses.replace(...)`, so current PR #48, PR #47, PR #46, PR #45 and current reviewed-source-capability validation runs again.

The caller-presented PR #48 receipt bytes must equal the rebuilt canonical PR #48 receipt byte-for-byte. Their SHA-256 is carried into the request plan.

The resulting `FotMobMatchDetailsProbePlan` is itself self-validating. It retains the exact PR #48 object and exact receipt bytes internally, while serializing only detached reviewed fields. Reconstructing the plan reruns the PR #48 chain and proves that its hashes, fixture identity, source match id, kickoff, route and transparent headers still match those upstream inputs. A manually fabricated detached plan therefore cannot become a valid probe receipt.

A historical PR #48 receipt whose verification happened after kickoff remains valid for audit, but it cannot drive this probe because PR #49 independently requires:

```text
PR #48 verified_at <= request_started_at < fixture kickoff
```

After connection setup but immediately before `endheaders()` can send request bytes, the plan is revalidated again and the clock is checked again. If that final pre-send time reaches kickoff, the connection is closed and no request bytes are sent.

The completed response observation must also be strictly before kickoff. If a response crosses the kickoff boundary, PR #49 fails closed and emits no successful response receipt.

## Transparent request profile

The request uses `http.client.HTTPSConnection` directly with:

```text
GET /api/data/matchDetails?matchId=<id>
Accept: application/json
User-Agent: ATHENA/1.0
```

The implementation:

- opens at most one HTTPS connection through the supplied connection factory;
- issues one GET request;
- does not follow redirects;
- does not add `X-Mas` or any application signature;
- does not send cookies;
- does not impersonate a browser;
- does not use `requests`, `curl_cffi`, Playwright, proxy evasion, the legacy bypass client, or the advanced scraper;
- reads at most 4096 response bytes;
- requires explicit exact `execute_live_network=True` before a connection can be created;
- revalidates the exact PR #48 chain immediately before request bytes are sent.

PR #49 intentionally exposes an importable operator function rather than a standalone CLI. No reviewed parser yet exists for reconstructing persisted PR #48 Python objects from arbitrary disk input, so this PR does not invent one.

## Probe receipt

A successful transport records only detached reviewed values:

- exact PR #48 receipt SHA-256 and receipt byte size;
- exact PR #47 bootstrap SHA-256;
- source-scoped fixture identifier;
- exact FotMob source match id;
- kickoff;
- request start time;
- fixed host, target and headers;
- explicit no-X-Mas/no-cookie/no-browser-impersonation flags;
- HTTP status;
- bounded `Content-Type`, `Content-Length`, and `Location` metadata when present;
- response observation time;
- bounded sample byte count and SHA-256.

The sample bytes themselves are **not** promoted, parsed, written, or exposed as football evidence by this boundary. A later controlled raw-capture PR must preserve exact bytes if the route is worth qualifying further.

Receipt serialization is detached from nested PR #48 state so historical audit bytes remain stable. Constructing or reconstructing a receipt, however, revalidates its plan and therefore fails closed if the current upstream chain has been mutated or its capability revoked.

Redirects are recorded as the single response and never followed. A transport failure before any response produces a metadata-only `TRANSPORT_ERROR` receipt. An error after a response has been obtained, such as response sampling failure, is not silently downgraded to a transport failure.

## Safety

Every downstream authorization in the receipt remains exact immutable `false`, including:

- network acquisition into trusted evidence;
- raw capture;
- artifact writing;
- response-body parsing;
- source qualification;
- football semantics;
- Fixture Intelligence facts or snapshots;
- model features;
- probabilities;
- pricing;
- selection;
- betting.

The explicit one-shot network flag authorizes only the diagnostic transport operation itself. It is not source qualification and it does not make the returned bytes trusted evidence.

## Legacy code is not part of this boundary

Older repository files contain historical FotMob match-detail callers with browser-style user agents and bypass-oriented clients. PR #49 deliberately does not import or reuse those paths.

Their existence is not evidence that the route is production-safe, stable, semantically understood, or currently qualified.

## Next safe boundary

If an authorized live diagnostic demonstrates a useful stable JSON response, the next narrow PR should be a **controlled raw match-details capture boundary**:

- exact PR #49 request identity and provenance;
- exact raw response bytes;
- SHA-256 and manifest;
- no overwrite;
- no parsing during capture;
- all football semantics still untrusted.

Only a later offline schema/semantic assessment may decide which fields, if any, can become reviewed Fixture Intelligence facts under PR #30.
