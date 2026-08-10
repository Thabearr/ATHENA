# Reviewed FotMob match-details durable capture

## Purpose

PR #51 is the operator transport/persistence layer around the exact PR #50 raw-capture artifact.

The reviewed path is now:

```text
reviewed fixture identity
→ PR #48 verified Fixture Intelligence bootstrap artifact
→ PR #49 reviewed one-request `/api/matchDetails` plan
→ PR #50 self-validating raw response + detached canonical manifest artifact
→ PR #51 one transparent full-body request + durable research-cache publication
→ later offline schema assessment
```

PR #51 does **not** parse the response body and does **not** qualify any football field.

## Live request gate

`capture_fotmob_reviewed_match_details(...)` requires exact `execute_live_network=True` before a connection can be created.

The request plan is built through PR #49 from:

- an exact PR #48 verified bootstrap artifact;
- its exact canonical verification receipt bytes;
- one exact admitted `FOTMOB:<positive decimal id>` fixture;
- a UTC request start strictly before kickoff.

The transport remains the transparent ATHENA profile already reviewed in PR #49:

- host `www.fotmob.com`;
- HTTPS port 443;
- `GET /api/matchDetails?matchId=<exact admitted source id>`;
- `Accept: application/json`;
- `User-Agent: ATHENA/1.0`;
- no cookies;
- no `X-Mas` signature;
- no browser impersonation;
- no redirect following;
- one connection / one request only.

Immediately before `endheaders()`, the complete PR #49 plan is reconstructed again and its canonical bytes must still equal the bytes captured before connection setup. The send time must remain strictly before kickoff.

## Full response contract

Unlike PR #49's diagnostic 4096-byte sample, PR #51 reads the complete response only for preservation.

The response must satisfy all of:

- exact HTTP 200;
- strict `application/json` Content-Type;
- optional Content-Length is a canonical non-negative ASCII integer;
- declared Content-Length cannot exceed 8 MiB;
- streamed body cannot exceed 8 MiB;
- body is non-empty exact bytes;
- declared length, when present, equals the complete received byte count;
- full-body observation time is no earlier than the request start and strictly before kickoff.

PR #51 never calls `json.loads(...)` on the body. Syntactically invalid JSON bytes are still preserved if the transport metadata satisfies the raw-evidence contract; deciding whether the payload is structurally valid is intentionally deferred to offline assessment.

## PR #50 artifact construction

After the complete body is received, PR #51 constructs:

1. `CapturedFotMobReviewedMatchDetailsResponse`;
2. the PR #50 `FotMobReviewedMatchDetailsRawCapture` using the exact PR #49 plan bytes;
3. the PR #50 detached `FotMobReviewedMatchDetailsCaptureArtifact`.

The artifact therefore owns the exact raw bytes, exact canonical manifest bytes, manifest SHA-256, raw SHA-256 and raw byte size before filesystem publication begins.

## Durable publication

The only legal output root is:

```text
.cache/athena-research/fotmob-reviewed-match-details-captures
```

The repository already ignores `.cache/athena-research/`.

The capture directory is the deterministic PR #50 capture identifier:

```text
<source_match_id>--<UTC observation timestamp>--<full raw SHA-256>
```

Each capture directory contains exactly:

```text
response.json
manifest.json
```

`response.json` is byte-for-byte the received body. `manifest.json` is byte-for-byte the canonical manifest frozen by PR #50.

Publication is fail-closed:

- repository/output-root containment is exact;
- traversal is rejected;
- symlink components are rejected;
- capture directories are created exclusively;
- temporary files use exclusive creation;
- final publication uses no-overwrite hard-link semantics;
- file contents are flushed with `fsync`;
- directory durability is required on POSIX and Windows;
- partial owned output is rolled back on failure;
- already-existing evidence is never overwritten;
- published files are read back and must exactly equal the PR #50 raw/manifest bytes.

A platform on which directory durability or no-overwrite publication cannot be proven fails closed rather than degrading silently.

## Trust semantics

Successful PR #51 publication proves only that ATHENA performed one reviewed request and durably preserved the exact returned bytes under the reviewed provenance chain.

It does **not** prove that any field inside those bytes is correct, fresh enough for modelling, complete, source-qualified or semantically understood.

In particular, PR #51 does not authorize:

- response-body parsing;
- source/schema qualification;
- football semantics;
- Fixture Intelligence facts;
- Fixture Intelligence snapshots;
- model features;
- probabilities;
- pricing;
- selections;
- bets.

The next safe boundary is an **offline match-details schema assessment** against preserved PR #51 evidence. Only reviewed fields from that later assessment may be considered for a source-capability decision and eventual Fixture Intelligence fact mapping.
