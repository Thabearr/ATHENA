# Reviewed FotMob match-details raw capture contract

## Purpose

PR #50 defines the next narrow ATHENA trust boundary after PR #49.

It does **not** perform a network request and it does **not** write files. Instead, it defines the exact object-level contract that a later operator capture workflow must satisfy before any `/api/matchDetails` response can be treated as preserved raw evidence.

The path is:

```text
reviewed fixture identity
→ PR #48 verified Fixture Intelligence bootstrap artifact
→ PR #49 reviewed one-request match-details plan
→ PR #50 self-validating full raw response + detached manifest artifact
→ later durable writer / offline schema review
```

## Inputs

`build_reviewed_match_details_raw_capture(...)` requires all three of:

1. an exact `FotMobMatchDetailsProbePlan` from PR #49;
2. the exact canonical PR #49 plan bytes;
3. an exact `CapturedFotMobReviewedMatchDetailsResponse` containing the complete unparsed body bytes and transport metadata.

The PR #49 plan is reconstructed with `dataclasses.replace(...)`. That reruns PR #49's own current validation, which in turn reruns the exact PR #48 → #47 → #46 → #45/current reviewed-source-capability chain.

The caller-presented plan bytes must equal the rebuilt canonical plan bytes byte-for-byte.

## Response contract

The raw response object is deliberately narrow:

- HTTP status must be exact `200`;
- `Content-Type` must identify `application/json` using the already-reviewed strict JSON media-type validator;
- `Content-Length`, when present, must be an exact non-negative integer and equal the complete body size;
- body must be exact immutable non-empty bytes;
- maximum body size is 8 MiB;
- `observed_at` is normalized to UTC;
- `network_acquisition_performed` is an exact boolean fact, not an authorization flag.

PR #50 never calls `json.loads(...)` on the raw response bytes. JSON appears only in canonical serialization of already-reviewed metadata and PR #49 plan bytes.

## Timing

The full response observation must satisfy:

```text
PR #49 request_started_at <= observed_at < fixture kickoff
```

A response observed at or after kickoff is rejected. A response timestamp earlier than the exact PR #49 request start is also rejected.

## Manifest

The manifest records detached provenance only:

- schema and dataset identity;
- exact canonical PR #49 plan SHA-256 and byte size;
- detached canonical PR #49 plan payload;
- source-scoped fixture identifier;
- exact FotMob source match id;
- kickoff;
- request start;
- HTTP status and bounded transport metadata;
- observation time;
- whether network acquisition was performed by the supplying layer;
- `response.json` as the eventual raw file name;
- exact raw body byte size;
- exact raw body SHA-256;
- downstream safety flags, all exact `false`.

The `FotMobReviewedMatchDetailsRawCapture` couples the exact body bytes to that manifest. Reconstructing the capture revalidates the manifest, raw size and raw SHA-256.

Canonical manifest serialization is sorted-key, compact UTF-8 JSON with one trailing newline. The raw response bytes themselves are never embedded in the manifest.

## Detached capture artifact

`build_reviewed_match_details_capture_artifact(...)` is the final in-memory output of PR #50. It revalidates the raw capture and freezes:

- the exact canonical manifest bytes;
- the manifest SHA-256;
- the raw body SHA-256;
- the raw body size.

This separation matters for the next writer boundary. A later writer can persist the exact bytes produced by PR #50 rather than recomputing a manifest from a live nested object at write time.

If nested capture or manifest state is later forcibly mutated, the already-captured `manifest_bytes` remain historical audit bytes, while `revalidate_reviewed_match_details_capture_artifact(...)` fails closed for any new use. Changed manifest bytes, manifest hash, raw hash, or raw size are rejected.

## Capture identity

`reviewed_match_details_capture_identifier(...)` deterministically derives:

```text
<source_match_id>--<UTC observed timestamp>--<full raw SHA-256>
```

This is only an evidence/capture identity. It does not create a new football fixture identity.

## Safety

PR #50 authorizes none of the following:

- network transport;
- filesystem writes;
- raw-response parsing;
- source qualification;
- football semantics;
- Fixture Intelligence facts or snapshots;
- model features;
- probabilities;
- pricing;
- selection;
- betting.

All downstream safety flags are exact immutable `false`.

The contract imports no HTTP client, browser tooling, filesystem API, Fixture Intelligence module, model-feature mapper, or prediction engine.

## Why transport and persistence are separate

The existing `/api/data/matches` writer owns a substantial trust surface: symlink rejection, exact research-cache roots, exclusive publication, fsync/directory durability, rollback and Windows/Linux behavior.

PR #50 intentionally does not duplicate or modify that machinery. The next PR should add the operator transport/durable-write workflow around this exact contract, with one transparent full-body request and no response parsing.

Only after exact raw bytes have been durably preserved should a later offline assessment inspect `/api/matchDetails` structure and decide whether any specific fields are suitable for reviewed Fixture Intelligence facts.
