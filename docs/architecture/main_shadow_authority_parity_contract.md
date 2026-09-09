# Main / Shadow authority and parity contract (P0.3)

## Purpose

`config/architecture/main-shadow-authority-parity-v1.json` is the versioned,
machine-validated policy for ATHENA's Main and Shadow execution contexts.  It
freezes the target invariant before implementation migration: **one canonical
ATHENA core, with two explicit authority profiles**.

## Why Shadow is not a second ATHENA

Shadow is a research execution profile over the same intended canonical
baseline, not a permanent duplicate of ATHENA.  A profile difference may be
authority, configuration, or an explicitly registered challenger.  It may not
silently fork fixture identity, evidence lineage, provider market or quote
semantics, settlement, pricing infrastructure, routing, portfolio, or delivery.

## Execution profiles versus module authority roles

`MAIN` and `SHADOW` are runtime execution profiles.  Module/component roles use
the separate P0.2 vocabulary: `SHARED_CANONICAL`, `MAIN_ONLY`, `SHADOW_ONLY`,
`RESEARCH_CHALLENGER`, `HISTORICAL_EVIDENCE`, and `UNKNOWN`.  In particular,
`MAIN_ONLY` does not mean canonical, and `SHADOW_ONLY` does not grant production
authority.

## Cleanup disposition is independent

This contract grants no cleanup disposition.  Every reviewed assignment remains
`UNCLASSIFIED`; `KEEP`, `MIGRATE_THEN_DELETE`, `ARCHIVE_OR_RETIRE`, and `DELETE`
require later multi-signal remediation evidence.

## Shared canonical responsibilities

The contract enumerates the canonical responsibility boundary, even where an
implementation owner has not yet been promoted.  `EXACT_SHARED_BASELINE` means
Shadow divergence is forbidden.  `SHARED_BASELINE_REGISTERED_CHALLENGER_ALLOWED`
means the champion baseline remains shared while Shadow may evaluate a registered
research challenger in the isolated, documented challenger slot.

Parity means that, with the same baseline component identities, evidence,
fixture state, prices, and configuration and no challenger selected, Main and
Shadow are capable of producing the same canonical intermediate semantics.  It
does not require challenger results to equal champion results.

## Current Main and Shadow architecture state

`build_acca` is recorded only as a supported legacy Main-facing entrypoint.  The
Current Shadow hosted roots and runner are research-only orchestration.  The
existing Current Shadow Price-All, Router, Portfolio, and share-code modules are
transitional profile-specific implementations and known parity gaps, not approved
permanent Shadow deviations.  The v3 current-provider components are unproven
canonical-promotion candidates, not shared canonical owners.  Legacy
`engine.market_selector` and `services.prediction_service` remain in a
reachability-review queue, not a deletion queue.

## Fresh-holdout protection

The prospective xG holdout workflows and roots are protected active research
infrastructure.  Protection means no deletion authority, no migration without
experiment review, no synthetic backfill, and no automatic promotion.  It does
not misclassify evidence/continuity infrastructure as a challenger algorithm.

## Registered challenger and deviation schema

Only an explicit entry in `active_shadow_deviations` can activate a Shadow
challenger.  It must identify its responsibility, champion baseline, challenger,
research-only authority, evidence status, review requirement, and future
promotion-PR requirement.  Deviations are forbidden for exact-shared
responsibilities.  The baseline contract has no active deviations.

## No automatic promotion and lifecycle

The lifecycle is:

`REGISTERED_CHALLENGER → SHADOW_EVALUATION → PROSPECTIVE_WALK_FORWARD_EVIDENCE → REVIEW_REQUIRED → EXPLICIT_PROMOTION_PR → MAIN`.

Shadow success, a holdout pass, share-code success, and a backtest win are each
insufficient for promotion.  A later reviewed repository change is required; no
runtime self-promotion is permitted.

## Request semantics parity

`request_date_and_target_semantics` is exact-shared: requests support 1–50 legs,
1–7 selected calendar days, and arbitrary weekday combinations resolved to
concrete dates before orchestration.  `target_legs` is distinct from
`target_total_odds`; `25acca` means 25 requested legs.  A truthful shortfall is
always permitted.

## Safety boundary

Shadow remains research-only.  Login, cookies, wallet, staking, and wager are
false.  Anonymous share-code create/reload verification is non-wager delivery
research and does not grant production pricing, routing, portfolio, or selection
authority.

## What P0.3 does not do

P0.3 makes no runtime migration, cleanup/deletion, architecture CI, runtime
instrumentation, canonical promotion, model/provider/current-Shadow/fresh-holdout
change, or user-command change.  It does not claim Checkpoint B0 complete.

## Next waves

P0.4 will enforce this contract through architecture boundary CI; only then can
B0 pass.  P1/P2/P3 will promote interfaces, extract the shared core, and migrate
Main/legacy callers to close the recorded parity gaps.
