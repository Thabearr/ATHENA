# ADR-001 — Canonical PriceAll Promotion

## Status

Accepted

## Context

The ATHENA Architecture Remediation Master Implementation Specification v2 requires P1.3 to promote the reviewed current-provider Price-all v3 semantics behind the unversioned `domain.price_all` API. The repository already contains several public Price-all generations that are grandfathered by Architecture Boundary CI. Adding `domain.price_all` therefore creates a temporary additional public family member during migration and must be explicitly reviewed rather than silently bypassing the no-new-parallel-authority rule.

P1.2 has already separated football probability output from provider pricing. P1.3 is an ownership/interface promotion only: the accepted current-provider v3 implementation remains the delegated implementation while the unversioned canonical API becomes the stable target for subsequent router, Shadow and Main migrations.

## Evidence

Controlling design evidence is ATHENA Architecture Remediation Master Implementation Specification v2, Part V / 53, which requires `domain/price_all.py` to become the canonical interface while initially delegating to v3 current-provider behavior and requires canonical/v3 output parity on a fixture corpus.

Live repository evidence at P1.3 start is main `63e4dca1a522a674f34702f9ad02546cc7e293b6`. On that exact state, `domain.price_all_v3_current_provider` owns reviewed exact-source reconstruction, freshness rechecks, complete-partition de-vig, settlement-aware expected return and explicit unpriced dispositions. Its frozen contract SHA-256 is `30481bc9ebf442f0e664bcd14d2c6cd18026a42a35083d143db6366837b3d425`.

The existing Architecture Boundary CI policy requires an accepted ADR for any new public `domain.price_all*` family member that was not present in the frozen P0.4 baseline. This ADR approves only the exact module `domain.price_all` and no other module, version, wildcard or authority family.

## Decision

Approve `domain.price_all` as the unversioned canonical Price-all interface for P1.3. During the migration window it delegates to `domain.price_all_v3_current_provider` and must preserve the delegated canonical pricing payload byte-for-byte on the reviewed replay corpus.

This decision does not approve a second pricing formula. It does not authorize a v4/current2/next pricing generation. It does not promote the v3 filename itself as permanent canonical ownership. It does not grant router, portfolio, provider execution, login, cookies, wallet, staking, betting or wagering authority.

Architecture Boundary CI policy may therefore register exactly `domain.price_all` under responsibility `price_all_and_de_vig` as an accepted temporary coexistence exception.

## Alternatives considered

Retaining only the v3 public name was rejected because the controlling P1.3 specification explicitly requires an unversioned canonical target and version suffixes are migration aids, not permanent ownership.

Copying v3 formulas into a new implementation was rejected because P1.3 forbids formula changes and requires exact replay parity. A facade/delegation boundary is smaller, reversible and preserves the evidence trail.

Adding `domain.price_all` directly to the frozen P0.4 baseline list was rejected because that baseline is historical evidence and must not be rewritten to pretend a later module existed at the P0.4 base.

Bypassing or weakening Architecture Boundary CI was rejected because it would defeat the guardrail established specifically to prevent new parallel authority.

## Consequences

For a bounded migration period, the repository contains both the unversioned canonical public interface and the reviewed v3 implementation name. This coexistence is explicit, source-controlled and limited to one responsibility.

The canonical interface must remain formula-neutral and replay-identical to v3 in P1.3. Existing supported callers are not silently migrated in this ADR. The v3 module remains required until later migration work proves callers can use the canonical interface without semantic drift.

Frozen v2/v3/source contract identities remain evidence. Removing a runtime dependency later requires separate proof that equivalent contract vectors and hashes are preserved.

## Migration plan

P1.3 introduces `domain.price_all` and contract/parity tests while retaining v3 as the delegated implementation. P1.4 may consume canonical `PriceAllEvaluation` through a bounded router compatibility seam. Later P2/P3 work migrates Current Shadow and supported Main/legacy callers to shared canonical components.

Only after supported callers no longer require the public v3 filename may a separate reviewed PR internalize, retire or archive it. That retirement must satisfy architecture reachability and evidence-retention gates; this ADR itself gives no deletion authority.

The `approved_parallel_authority_adrs` entry for this ADR should be removed or replaced by the appropriate post-migration policy representation when the v3 public coexistence period ends.

## Rollback / revisit trigger

If canonical/v3 fixture-corpus parity fails, hosted exact-head CI fails, a downstream authority boundary expands, or the facade cannot preserve exact source replay, revert the P1.3 changes. No supported caller is migrated by P1.3, so rollback returns the repository to direct v3 ownership without data or provider-state migration.

Revisit this ADR when all supported pricing callers target `domain.price_all` and runtime reachability shows the v3 public filename is no longer required, or sooner if the component-authority registry introduced by P1.7 provides a stricter reviewed representation of the same migration state.
