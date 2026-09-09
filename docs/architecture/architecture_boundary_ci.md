# Architecture Boundary CI

## Purpose

P0.4 stops new architecture sprawl while P1/P2/P3 repair existing duplication.
It is static CI tooling only: it does not select canonical owners, migrate a
pipeline, retire a module, or execute a runtime/provider path.

## Controlling v2 requirement and P0.3 relationship

The policy is pinned to the exact P0.3 Main/Shadow authority contract and its
SHA-256. P0.3 remains the authority source; P0.4 neither changes that contract
nor lets configuration self-assert `SHARED_CANONICAL`, Main, or production
authority.

## Reserved public authority families

The policy freezes the public `domain.market_router`, `domain.price_all`, and
`domain.portfolio_optimizer` families, including their reviewed Current Shadow
counterparts. Existing generations are grandfathered architecture debt, not
canonical approval, permanent ownership, cleanup approval, or permission to
clone another generation.

## Parallel authority and ADRs

A new public family member requires one exact accepted ADR under
`docs/architecture/adrs/`. The ADR must identify a single responsibility and
exact modules, and must contain Status, Context, Evidence, Decision,
Alternatives considered, Consequences, Migration plan, and Rollback / revisit
trigger. An accepted ADR is an architecture exception only, never promotion.

Private helper candidates whose final component begins `_` are not public
authority merely because their name contains router, Price-All, or portfolio.
Comments, docstrings, and string constants are not imports or authority names.

## Dependency boundaries

- Model/probability sources cannot import SportyBet delivery/share-code targets.
  Ordinary SportyBet provider/pricing evidence remains distinct and permitted.
- Price-All and private pricing cores cannot import portfolio, staking, wager,
  or betslip authority.
- P0.3-derived Shadow profile orchestration cannot import login,
  authentication, wallet, stake, wager, or betslip authority. The reviewed
  anonymous share-code boundary remains permitted and non-wager.

Static imports, aliases, relative imports, literal `importlib.import_module`,
and literal `__import__` are resolved through AST analysis. A non-literal
dynamic import in a boundary-controlled source fails closed. Custom loaders are
not mistaken for `importlib` merely because they use a similarly named method.

## Determinism and failure handling

The validator resolves an exact commit, reads only tracked files at that ref,
uses canonical JSON bytes, and emits sorted actionable diagnostics. Ambiguous
relative imports, malformed policies, missing ADRs, or unknown dynamic targets
fail closed. Untracked files, caches, and developer-machine state have no
authority.

When a CI checkout does not retain the exact P0.4 base commit, baseline-family
verification uses only the immutable P0.2 inventory whose bytes and source
commit are already pinned by P0.3. This narrow shallow-checkout fallback never
uses working-tree files or network state; a full-history checkout continues to
inspect the exact base commit directly.

## Current baseline and CI integration

At creation, the ADR registry is empty and the exact P0.4 base has zero
forbidden dependency violations. The policy validates every grandfathered public
family member against that base. Existing `tests.yml` discovery runs
`tests/test_architecture_boundaries.py`; P0.4 adds no workflow.

## What P0.4 does not do

P0.4 does not migrate existing duplicates. It prevents the problem from getting
worse while P1/P2/P3 repair it. It performs no runtime integration, provider
execution, Current Shadow run, fresh-holdout run, share-code operation, login,
wallet access, stake, or wager.

## Checkpoint B0

Architecture Boundary CI is the P0.4 enforcement required for B0. B0 is not
complete until this policy is merged and enforcement exists on main.
