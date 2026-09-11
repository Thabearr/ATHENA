# Canonical Component Authority Registry (P1.7)

## Purpose

`domain.component_authority_registry` is ATHENA's unversioned P1.7 authority-registry contract. It replaces implicit authority from filenames, import order, or the largest version suffix with typed records that bind a semantic responsibility and regime to an exact component identity, contract identity, source artifact identity, profile eligibility, promotion state, and schema compatibility.

The controlling Architecture Remediation Specification v2 requires registry reads to be deterministic and fail closed on duplicate authority, incompatible schema, unknown component identity, or ambiguous champion state. Registry changes are reviewed source changes, not runtime mutations from a backtest, holdout result, Current Shadow run, or share-code success.

## Authority is not inferred from registration

P1.7 introduces `REGISTERED_CHAMPION` as the registry-local state for an exact canonical baseline identity that is known to the registry but **has not received MAIN authority**. This state is deliberately distinct from `APPROVED_FOR_MAIN`.

A record can resolve for `MAIN` only when all of the following are true:

- its role is `CHAMPION`;
- `MAIN` is explicitly listed in `allowed_profiles`;
- `promotion_state == APPROVED_FOR_MAIN`; and
- `main_authority == true`.

Registration alone cannot satisfy those conditions. The default P1.7 registry grants **zero MAIN authority**.

Research challengers use the separate `RESEARCH_CHALLENGER` role. They are accepted only when their profile eligibility is exactly `SHADOW`, `main_authority` is false, and their promotion state remains in the research lifecycle (`REGISTERED_CHALLENGER`, `SHADOW_EVALUATION`, `PROSPECTIVE_WALK_FORWARD_EVIDENCE`, or `REVIEW_REQUIRED`). There is no direct registry transition from a research result to MAIN.

## Source-controlled registry

The reviewed data file is:

`config/architecture/component-authority-registry-v1.json`

The canonical loader has no environment override, experiment callback, runtime writer, auto-promotion hook, or provider dependency. The registry contract requires:

- `source_controlled_writes_only = true`;
- `runtime_mutation_allowed = false`;
- exact schema and policy identities;
- exact lowercase contract SHA-256 values;
- exact Git blob identities for the registered component source artifacts;
- sorted unique profile/schema compatibility values; and
- exactly one `CHAMPION` record for each populated responsibility/regime.

A source change that adds, removes, promotes, demotes, or rebinds a component is therefore a normal reviewable PR.

## Seeded P1.7 regime

The first registry population is intentionally narrow. It records only the canonical ownership interfaces already established by P1.3 through P1.6 for the current SportyBet-provider migration regime:

| Responsibility | Component | Contract identity | P1.7 role/state |
| --- | --- | --- | --- |
| `price_all_and_de_vig` | `domain.price_all` | reviewed delegated Price-All-v3 contract | `CHAMPION / REGISTERED_CHAMPION` |
| `market_router` | `domain.market_router_canonical_adapter` | canonical P1.4 Router contract | `CHAMPION / REGISTERED_CHAMPION` |
| `portfolio_optimizer` | `domain.portfolio_optimizer` | canonical P1.5 Portfolio contract | `CHAMPION / REGISTERED_CHAMPION` |
| `delivery_share_code_transport` | `domain.sportybet_share_code` | canonical P1.6 share-code contract | `CHAMPION / REGISTERED_CHAMPION` |

All four records are currently eligible for `SHADOW` only and have `main_authority=false`. This does **not** claim that Current Shadow has already migrated to the canonical Price-All/Router/Portfolio stack; P2.0/P2.1 remain responsible for shared-core extraction and caller migration. Profile eligibility is a registry permission boundary, not proof that a caller already uses the component.

The P1.3 Price-All wrapper deliberately preserves the reviewed Price-All-v3 payload and contract semantics byte-for-byte, so its registry `contract_sha256` is the delegated reviewed v3 implementation contract identity while `component_id` and Git blob identity bind the unversioned canonical wrapper itself.

Responsibilities not populated by this first registry have no implicit owner. A lookup for an unregistered responsibility/regime fails closed. P1.7 does not invent a champion merely to make the registry complete.

## Compatibility aliases

The contract supports one-way aliases, but the initial source registry contains none. An alias can only resolve to an already registered component record; it cannot carry its own role, promotion state, profile eligibility, or authority. Alias chains and aliases to unknown components are rejected.

Current Shadow's existing profile-specific Price-All/Router/Portfolio modules are therefore **not** aliased to canonical owners by P1.7. P2 migration must first prove behavioral equivalence before any compatibility alias is added.

## Deterministic fail-closed reads

`ComponentAuthorityRegistry` rejects:

- duplicate component identities;
- more than one champion for the same responsibility/regime;
- unknown component identities;
- aliases that shadow components, duplicate another alias, target themselves, or target unknown components;
- unknown responsibility/profile/promotion-role vocabulary;
- incompatible requested schema versions;
- a research challenger eligible for MAIN;
- any challenger with MAIN authority; and
- any MAIN champion resolution that lacks explicit `APPROVED_FOR_MAIN` authority.

`resolve_component()` returns the exact registered target (or its one-way alias target). `resolve_champion()` performs responsibility/regime/profile/schema checks. `resolve_research_challengers()` is available only for the SHADOW profile.

## Relation to P0.3 and later waves

P0.3 remains the frozen baseline authority/parity contract and cleanup evidence. P1.7 does not rewrite its historical starting-state assignments or close its recorded migration gaps by assertion. Instead, this registry becomes the typed source-controlled authority mechanism that later migration and promotion PRs can consume.

P2.0/P2.1 may migrate SHADOW to the shared canonical core using these exact registered identities. P3 later addresses MAIN/legacy caller migration. A later promotion PR may change a reviewed champion record to `APPROVED_FOR_MAIN` only with the separate evidence and review required by the architecture specification.

## Safety and non-authority

P1.7 does not fetch a provider, run Current Shadow, trigger fresh holdout, change model/calibration/Price-All/Router/Portfolio formulas, create a real SportyBet share code, log in, use cookies, access a wallet, calculate a stake, place a wager, or delete/retire any module. It grants no cleanup disposition and no automatic promotion authority.

## Exit-gate interpretation

For every responsibility/regime populated by P1.7, exactly one champion identity exists. No research challenger in the registry can be MAIN-eligible. No API or source-controlled hook allows a holdout/backtest result to mutate registry authority automatically. Those invariants are enforced by the dedicated regression suite.
