# Reviewed FotMob match-details persisted evidence verifier

## Purpose

PR #52 verifies the two exact historical files written by PR #51 before any offline body assessment begins:

```text
response.json
manifest.json
```

The boundary is intentionally historical and offline. It proves that the persisted raw bytes still match the canonical PR #50 manifest envelope that PR #51 wrote. It does **not** replay mutable upstream capability state and does **not** interpret football content.

## Exact checks

`verify_persisted_match_details_evidence(...)` requires:

- exact immutable manifest bytes;
- strict UTF-8 JSON;
- duplicate JSON keys rejected;
- NaN/Infinity-style JSON constants rejected;
- exact canonical compact/sorted JSON plus one trailing newline;
- exact PR #50 capture dataset/schema identity;
- exact reviewed manifest top-level keys;
- source-scoped `FOTMOB:<positive decimal id>` matching `source_match_id`;
- request start and observation timestamps strictly before kickoff;
- exact HTTP 200;
- reviewed JSON Content-Type;
- network acquisition recorded as performed;
- `response.json` as the raw file name;
- exact raw size and SHA-256;
- exact Content-Length agreement when Content-Length was captured;
- exact all-false PR #50 safety mapping.

The historical nested PR #49 plan is required to remain a JSON object and its recorded SHA/size must be structurally valid, but PR #52 does not pretend it can reconstruct the in-memory PR #48/#49 objects from the two persisted files alone.

## Raw response semantics

PR #52 deliberately does **not** parse `response.json`. Even syntactically invalid response-body JSON can pass this boundary if the exact persisted bytes and manifest envelope agree.

That distinction matters: PR #52 is evidence-integrity verification, not schema qualification.

## Receipt

A successful verification emits `VerifiedPersistedFotMobMatchDetailsEvidence`, which records only detached historical identities and metadata:

- manifest SHA-256 and size;
- raw SHA-256 and size;
- fixture/source match identity;
- kickoff/request/observation times;
- response metadata;
- plan SHA-256 and size;
- exact file names;
- all downstream safety flags false.

The receipt has deterministic canonical JSON bytes and SHA-256.

## Safety

PR #52 does not authorize:

- response-body parsing;
- source/schema qualification;
- football semantics;
- Fixture Intelligence facts or snapshots;
- model features;
- probabilities;
- pricing;
- selections;
- bets.

The next safe boundary is PR #53: strict offline structural assessment of the exact raw response bytes after PR #52 verification.
