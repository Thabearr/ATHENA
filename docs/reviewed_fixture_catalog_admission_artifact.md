# Reviewed Fixture Catalog admission artifact verification

## Purpose

PR #46 adds a read-only verification boundary for the canonical admission artifact produced by the reviewed FotMob Fixture Catalog path.

PR #45 established that a compiled catalog is not trusted merely because compilation succeeds. One exact catalog must first receive an explicit `ADMITTED` or `REJECTED` decision anchored through the reviewed candidate, review, handoff, compiler artifacts, and the narrow PR #44 source-capability profile.

PR #46 does **not** add persistence, runtime registration, or Fixture Intelligence consumption. It answers one smaller question first:

> Do these exact bytes still represent this exact, currently revalidatable `ADMITTED` PR #45 object?

Only if the answer is yes does PR #46 produce an immutable verification receipt.

## Verification contract

`verify_reviewed_fixture_catalog_admission_artifact(...)` requires:

- an exact `ReviewedFixtureCatalogAdmission` domain object;
- exact immutable `bytes` presented as the admission artifact;
- a timezone-aware timestamp already normalized to UTC.

Before verification succeeds, the gate:

1. requires the PR #45 disposition to be exactly `ADMITTED`;
2. rebuilds the admission through the PR #45 builder, re-running its current semantic checks rather than trusting an old Python object by assertion;
3. therefore rechecks the exact reviewed source capability and the PR #45 upstream catalog/handoff invariants;
4. requires at least one admitted source-scoped fixture identity;
5. serializes both the supplied admission object and the semantic rebuild canonically and requires those byte sequences to be exactly equal, so inconsistent derived state is rejected rather than silently repaired;
6. regenerates the canonical PR #45 admission bytes from the validated rebuild;
7. requires byte-for-byte equality with the presented artifact, including canonical ordering and the single terminal newline;
8. recomputes SHA-256 over those exact canonical bytes;
9. requires the verification timestamp not to predate the catalog-level admission review;
10. preserves all downstream authorization flags as exact immutable `False`.

Changed whitespace, a missing or extra newline, altered JSON content, mutated derived admission state, a rejected decision, a stale capability profile, an incorrect hash, or a fabricated direct construction all fail closed.

The supplied-object comparison is intentional. The verifier must not accept an inconsistent PR #45 object merely because it can reconstruct a correct replacement from other fields. `admitted_fixtures`, safety state, and other derived fields remain part of the exact object identity presented for verification.

## Verification receipt

A successful verification produces `VerifiedReviewedFixtureCatalogAdmissionArtifact`.

Its audit representation records only:

- schema and dataset identity;
- exact admission SHA-256;
- exact artifact byte length;
- captured source-capability identity and SHA-256 from the validated admission decision;
- admission review time;
- verification time;
- exact `ADMITTED` disposition;
- the already-admitted source-scoped fixture identities and kickoffs;
- exact downstream safety flags.

The receipt itself can be serialized as compact, sorted UTF-8 JSON with `allow_nan=False` and one final newline, and can be SHA-256 hashed deterministically.

The receipt does not replace the PR #45 admission artifact. It proves that one presented byte sequence exactly matched a currently revalidated admission object at a stated verification time.

## Capability changes and historical immutability

PR #45 deliberately made historical admission bytes independent of later mutation of the live capability registry. PR #46 preserves that property.

If the reviewed FotMob capability is later revoked or semantically changed:

- an already-created PR #45 admission object keeps the same historical canonical bytes;
- an already-created PR #46 verification receipt keeps the same historical canonical bytes;
- a **new** PR #46 verification attempt re-runs PR #45 semantic validation and fails closed if the current capability no longer matches the narrow identity-only profile.

This separates historical audit immutability from current eligibility for new downstream use.

## Safety boundary

Every PR #46 safety flag is exact `False` and immutable:

- no network acquisition;
- no artifact write authorization;
- no automatic review;
- no source qualification;
- no global team or competition identity resolution;
- no Fixture Intelligence bootstrap authorization;
- no Fixture Intelligence fact authorization;
- no model-feature authorization;
- no probability authorization;
- no pricing authorization;
- no selection authorization;
- no betting authorization.

The production module imports no filesystem, network, Fixture Intelligence, model, bookmaker, or betting implementation.

## Deliberately deferred

PR #46 performs **no filesystem writes**. PR #29's catalog writer already demonstrates that durable cross-platform transaction handling is a substantial audited boundary of its own; duplicating or casually reimplementing that machinery here would make this PR unnecessarily broad.

A later PR may add a narrowly reviewed persistence workflow that writes the exact PR #45 canonical bytes and PR #46 verification receipt with suitable no-overwrite, path, durability, and recovery guarantees. A separate later boundary may then use a freshly verified `ADMITTED` artifact as the only legal source-scoped fixture-identity bootstrap into Fixture Intelligence.

Neither future step may reinterpret fixture-identity admission as support for any football fact.
