# Canonical PriceAll Interface

## Mission

P1.3 promotes the reviewed current-provider Price-all v3 semantics behind the unversioned canonical boundary:

```text
domain.price_all
```

The controlling ATHENA Architecture Remediation Master Implementation Specification v2 requires this first promotion PR to change ownership and interface only. It does **not** change pricing formulas.

During the migration window the canonical boundary delegates to:

```text
domain.price_all_v3_current_provider
```

That implementation remains the exact pricing engine until later caller migration and retirement evidence are complete.

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

The delegated v3 implementation currently validates both the current-provider source contract and the frozen Price-all v2 contract before issuing a result. P1.3 keeps those exact identities visible through `validate_price_all_contract()` and changes none of their bytes or formulas.

This runtime dependency is transitional, not permanent architecture. Before a later PR removes the v2/v3 runtime dependency, equivalent frozen contract vectors, identities and replay evidence must be preserved in tests or historical evidence. P1.3 does not authorize that retirement.

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

P1.3 performs no provider acquisition and no Current Shadow execution. It creates no share code, performs no login, accesses no cookies or wallet, sets no stake and places no wager.

## Migration boundary

P1.3 does **not** migrate Current Shadow, `build_acca`, legacy application callers, router v3 or portfolio v3. Existing supported callers continue to use their pre-P1.3 path until their separately sequenced migration PRs.

P1.4 owns canonical Router/Coherence interface promotion. A temporary one-way `unwrap_v3_evaluation()` helper exists only so a reviewed router compatibility adapter can recover the exact verified delegated v3 evaluation during migration. Calling it does not promote router v3 or make v3 Price-all a second canonical owner.

P2/P3 later migrate Shadow and Main/legacy callers. Only after supported pricing callers target `domain.price_all` and reachability/evidence gates are satisfied may the v3 public filename be internalized, retired or archived in a separate PR.

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
