# Canonical PriceAll Interface

## Mission

P1.3 promotes the reviewed current-provider Price-all v3 semantics behind the unversioned canonical boundary:

```text
domain.price_all
```

The controlling ATHENA Architecture Remediation Master Implementation Specification v2 requires this first promotion PR to change ownership and interface only. It does **not** change pricing formulas.

At the original P1.3 migration checkpoint, the canonical boundary delegated to:

```text
domain.price_all_v3_current_provider
```

That versioned implementation path has since become a deprecated compatibility shim. The active implementation now lives at the private, unversioned `domain._price_all_current_provider` path; this P3.3 naming change does not alter pricing behavior.

## Canonical API

The stable public surface is:

```text
price_all_as_of(...)
price_all_current(...)
verify_price_all_evaluation(...)
PriceAllEvaluation
PriceAllResult
PriceDisposition
```

`price_all_as_of` is the deterministic replay lane. It accepts an explicit evaluation timestamp and preserves v3 exact-source reconstruction.

`price_all_current` is the currentness lane. It intentionally accepts **no caller-supplied evaluation timestamp**. Wall-clock time and LIVE_CURRENT qualification remain owned by the delegated v3 implementation so callers cannot mint favorable freshness.

`verify_price_all_evaluation` replays the exact delegated source/candidate state and requires byte-identical canonical output.

## Exact-output promotion rule

P1.3 does not translate the pricing evidence payload into a new representation. The canonical wrapper's `to_dict()` is deliberately byte-for-byte identical to the delegated v3 `to_dict()` for the same reviewed inputs.

Therefore the first promotion gate is directly testable:

```text
canonical PriceAll output == v3 output
canonical bytes == v3 bytes
canonical SHA-256 == v3 SHA-256
```

The wrapper type is unversioned; the implementation-specific hashes inside the payload remain provenance evidence during migration. They are not separate pricing authority.

## Preserved pricing semantics

The canonical boundary delegates, without modification, all reviewed v3 behavior:

- exact current-provider source reconstruction;
- exact fixture/event/market/outcome/line quote matching;
- source, manifest, inventory and reconciliation ancestry checks;
- freshness and minimum-kickoff-lead enforcement;
- explicit stale, unavailable, ambiguous, source-mismatch and settlement-unproven dispositions;
- same-provider-market complete-partition de-vig;
- refusal to combine different provider partitions as one market;
- settlement-aware expected return for Draw No Bet and Asian Handicap;
- explicit failure when required settlement distributions are incomplete;
- one audit result per supplied candidate rather than silent dropping;
- deterministic result ordering inherited from v3 replay.

No bookmaker price becomes football-probability authority. P1.2 remains the canonical probability boundary; pricing remains downstream.

## Frozen evidence dependencies

The active private implementation validates both the current-provider source contract and the frozen Price-all v2 contract before issuing a result. P3.2 preserves the exact frozen v2 contract identity and settlement-return semantics in the narrow internal module `domain._price_all_v2_direct_provider_contracts`; canonical Price-All no longer imports the full `domain.price_all_v2_direct_provider` evaluator at runtime.

The v2 identity remains visible through `validate_price_all_contract()` and is pinned by source-controlled vectors and differential tests against the retained v2 implementation. Settlement states, return values, error disposition, serialization and formulas are unchanged. The v2 implementation remains in the repository as historical/differential evidence; P3.2 granted no deletion authority. P3.3 has since handled module naming cleanup, while P5.2 remains the separate deletion gate.

## Architecture Boundary CI and ADR-001

`domain.price_all` is a new public member of the protected Price-all authority family. The frozen P0.4 baseline must not be rewritten to pretend the module existed at that historical checkpoint.

P1.3 therefore registers one exact accepted architecture decision:

```text
docs/architecture/adrs/ADR-001-canonical-price-all-promotion.md
```

ADR-001 approves only `domain.price_all` under `price_all_and_de_vig`. It permits temporary coexistence with the reviewed v3 implementation for migration. It does not approve `price_all_v4`, `price_all_current2`, a wildcard, or another pricing authority.

The ADR is an architecture migration exception, not a grant of production, router, portfolio or wager authority.

## Authority boundary

The canonical facade preserves the delegated pricing authority map:

- current-provider quote consumption: true;
- settlement-aware value computation: true;
- football probability generation: false;
- model promotion: false;
- market routing: false;
- portfolio optimization: false;
- final selection: false;
- SportyBet execution: false;
- staking: false;
- bet/wager: false.

P1.3 performed no provider acquisition and no Current Shadow execution. It created no share code, performed no login, accessed no cookies or wallet, set no stake and placed no wager.

## Migration boundary

At the P1.3 checkpoint, this promotion did **not** migrate Current Shadow, `build_acca`, legacy application callers, Router v3 or Portfolio v3. Subsequent P2/P3 work handled the Shadow and MAIN caller migrations, including P3.1 PR B.

At that stage P1.4 owned canonical Router/Coherence interface promotion. A temporary one-way `unwrap_v3_evaluation()` helper existed so the reviewed router compatibility adapter could recover the exact verified delegated evaluation during migration. Calling it did not promote Router v3 or make v3 Price-all a second canonical owner.

P3.3 has since moved the active Price-All implementation behind its private, unversioned module path and retained the former v3 path as a deprecated compatibility shim. This does not delete the historical implementation; P5.2 remains the separate deletion gate.

## P3.3 naming / retirement status

P3.3 places the active implementation behind private, unversioned `domain._price_all_current_provider`; the former `domain.price_all_v3_current_provider` path is a deprecated compatibility shim. The public canonical owner remains `domain.price_all`. This is a mechanical naming/ownership-boundary update with no formula or registry-promotion change. The historical implementation remains retained; P5.2 is the separate deletion gate.

## Rollback

Rollback is a revert of the P1.3 merge. Because this PR migrates no supported caller, reverting removes the canonical facade and ADR registration while all pre-existing callers continue using the unchanged v3 implementation.

No provider state, historical evidence, model artifact or wager state requires migration for rollback.

## Validation

Focused validation:

```text
git pull --ff-only && PYTHONPATH=. python -m pytest tests/test_price_all.py tests/test_price_all_v3_current_provider.py tests/test_architecture_boundaries.py -q
```

Architecture validation:

```text
git pull --ff-only && PYTHONPATH=. python scripts/validate_architecture_boundaries.py --policy config/architecture/architecture-boundary-policy-v1.json --ref HEAD
```

The hosted `Tests` workflow on the exact final PR head is the repository-wide acceptance gate. No live provider/Current Shadow run is required for this interface-only promotion.
