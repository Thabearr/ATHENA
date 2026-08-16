# PR69 Primary Time-Basis Evidence Acquisition Protocol

## Status

**Pre-registered only. No network acquisition has been executed by this boundary.**

Protocol ID: `REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_PROTOCOL_V1`

Canonical SHA-256: `28ec0a0208858ce3258a584bad1361577a0e202e5cbdb8eb9b13cdd47d7455a3`

Canonical size: `9,039` bytes.

Repository anchor: `620d1c5e3bcbb9fe5223a3f6348d04d11ebc1e44`.

## Why this boundary exists

PR123 correctly stopped at `BLOCKED_NO_ADMISSIBLE_PRIMARY_TIME_BASIS_EVIDENCE`. The frozen PR69 CSV corpus preserves the raw `Date` and `Time` text, but ATHENA still has no reviewed primary evidence bundle that defines the source-local clock semantics and proves the historical effective scope needed for the 2020-21 through 2025-26 research corpus.

The prior observation that current `notes.txt` describes `Time` as the match kick-off time remains discovery-only. That statement does not itself define a timezone, fixed offset, daylight-saving rule, or historical effective period.

This PR therefore freezes how primary evidence must be captured **before** a runner or network request exists.

## Frozen primary targets

The acquisition runner must capture exactly four HTTPS surfaces from `www.football-data.co.uk`, in this order:

1. `/notes.txt` — primary field dictionary.
2. `/data.php` — dataset lineage and historical-availability context.
3. `/downloadm.php` — historical-download and notes-linkage context.
4. `/matches.php` — site clock wording and fixture context.

The latter three are context surfaces. Wording such as `UK time` or `British Standard Time` must not be silently promoted into the CSV `Time` field rule unless captured primary bytes explicitly make that connection.

## Request identity

- method: `GET`
- scheme/host/port: `https://www.football-data.co.uk:443`
- redirects: disabled
- cookies: disabled
- browser impersonation: disabled
- proxy evasion: disabled
- TLS verification: required
- `Accept-Encoding: identity` is frozen so the capture contract can preserve a deterministic HTTP body representation without browser-like content negotiation.

Any redirect, TLS failure, non-200 response, content-type mismatch, oversized response, timeout, hash failure, manifest failure, or durability failure is recorded and fails closed.

## Repeated capture requirement

Each target has slots `A` and `B`. All four `A` captures run first in frozen target order; all four `B` captures follow in the same order. A target's two successful captures must be separated by at least 300 seconds and no more than 3,600 seconds. Up to three attempts per slot are allowed, with frozen retry delays of 60 then 300 seconds. All failures remain evidence even after a later success.

The complete acquisition therefore requires exactly eight successful capture slots plus accounting for every failed attempt.

## Raw evidence and provenance

For every successful capture the runner must preserve the exact HTTP body bytes **before** decoding, line-ending normalization, charset normalization, semantic extraction, or interpretation. SHA-256 and byte size are computed over those bytes.

Each immutable manifest must bind at least:

- target ID and slot;
- requested URL and final URL;
- request start, response completion, and observation timestamps in UTC;
- HTTP status and TLS verification result;
- selected response headers including content type, length, date, ETag, Last-Modified, cache controls, encoding, location, and server when present;
- exact raw-body SHA-256 and byte size;
- filenames/references needed to reproduce the evidence chain.

Raw bytes, manifests, campaign index, and failure journal remain durable research evidence outside Git. Git may later receive only reviewed hashes, counts, classifications, and references.

## Admissibility rules

A semantic statement may be considered for later review only when it comes from the exact primary origin, has a valid successful capture manifest, and cites the exact captured raw hash plus byte/line location.

For a future **direct** PR69 time-basis resolution, primary evidence must explicitly establish the relevant timezone, offset, or source-defined civil-time rule and daylight-saving transition semantics where applicable. `Time = Time of match kick off` is not enough by itself.

Current semantics and historical effective scope are separate gates. Current documentation may not be retroactively applied to the six frozen seasons merely because the current site still exposes the same field name. HTTP `Last-Modified`, ETag, capture date, search snippets, caches, and third-party archives cannot substitute for primary historical scope evidence.

## Historical scope accounting

Any future execution/qualification must account for the exact existing PR69 research scope:

- 66 source files;
- 10,006,877 source bytes;
- 21,226 fixture rows;
- seasons 2020-21 through 2025-26;
- current eleven-family historical/model research scope only.

Every source file must either map to proven primary effective-scope evidence or remain unresolved. Every fixture row inherits only from the proven scope of its own source file. The eleven families remain a research scope, not a claim about ATHENA's full competition universe.

## Conflict handling

All conflicting primary statements or versions are retained independently with their own raw hashes and scope evidence. Conflicts may not be resolved by majority vote, recency, result fit, or convenience. A timezone/offset/DST/civil-time conflict blocks future resolution until a separately reviewed boundary handles it.

Repeated capture pair drift is evidence and must be reported, not overwritten.

## Explicit non-authority

This protocol does not execute acquisition, resolve PR69 time semantics, compare FotMob `Europe/Oslo`, authorize PR80 constructor input, train a model, generate expected goals/probabilities, activate markets, price selections, approve production, or authorize BET.

All safety/authority flags remain exact `false`.

## Next boundary

`IMPLEMENT_REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_RUNNER`

That runner must implement this exact request/capture schedule and durability contract without widening the source set or changing the evidence rules.
