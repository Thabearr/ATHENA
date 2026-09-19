# P3.0 prospective legacy/canonical comparison evidence

## Purpose

P3.0-E1 establishes the immutable evidence boundary needed before P3.0 can
compare the supported legacy application with the source-controlled SHADOW
canonical stack. It remains an evidence-capture prerequisite only: it does not
compare decision quality, select a market, alter an accumulator, grant MAIN
authority, or begin P3.1.

The recovery audit concluded `P3_0_CORPUS_BLOCKED_BY_MISSING_LINEAGE`: no
preserved row proved the same fixture and prospective decision state for both
the supported legacy output and canonical pricing/routing evidence. Existing
canonical receipts could not be joined to captured `AnalysisPipeline`
inputs/results without fabrication.

## Supported paths

The supported legacy application path remains:

`AccaBuilder -> AnalysisPipeline.run_pipeline_snapshot ->
MatchAnalyst.compile_master_fixture_prediction -> AccaFilter / Accumulator`.

`PredictionService -> MarketSelector.select` remains separately reachable
legacy behavior and is not substituted for the supported path.

The canonical research side resolves the source-controlled SHADOW canonical
core and reuses the reviewed Current Shadow acquisition path only through its
Price-All/Router stage. P3.0-E1 does not call Portfolio or share-code delivery.
During P2.1 the Current Shadow Price-All/Router payloads remain compatibility
payloads delegated behind the canonical component owners; the evidence contract
labels them explicitly as such and does not falsely claim they are the P1.3
`PriceAllEvaluation` / canonical `RouterDecision` payload types.

## Evidence contract

Public module: `domain.p3_0_comparison_evidence`.

Policy ID: `ATHENA_P3_0_COMPARISON_EVIDENCE_V1`.

Schema version: `1`.

Pinned hardened schema-contract SHA-256:

`09a18f8a8a197744b7fa335ec8c237168e2efe6992f71663df0ba3146510b329`

The public module is a stable facade over a private implementation. Canonical
JSON is deterministic UTF-8 with sorted keys, compact separators and one final
LF; NaN/Infinity and duplicate JSON keys fail closed.

### Explicit projections

A non-null dictionary is not evidence. `P3_0_CAPTURE_COMPLETE` requires all of
the following projections to pass their semantic validators:

- supported legacy input/context;
- pre-runtime-gate legacy analysis, runtime-authorized analysis and exported
  `AnalysisPipeline` row;
- canonical fixture state;
- a replay-valid `MarketProbabilityBundle` whose canonical SHA is verified by
  the existing probability contract;
- provider semantic registry/source identities;
- at least one exact source-bound quote with source and reconciliation hashes;
- Price-All compatibility output bound to canonical owner
  `domain.price_all`;
- Router compatibility output bound to canonical owner
  `domain.market_router_canonical_adapter` and to the exact Price-All digest;
- exact SHADOW canonical-core authority identities;
- exact fixture join; and
- a derived prospective as-of/capture-window proof.

Empty or placeholder dictionaries remain partial evidence.

### Canonical authority binding

The evidence contract requires exactly one source-controlled SHADOW record for
each reviewed responsibility and pins the current reviewed owner, contract and
Git-blob identities:

- `provider_market_semantics -> domain.provider_market_semantics`;
- `price_all_and_de_vig -> domain.price_all`;
- `market_router -> domain.market_router_canonical_adapter`;
- `portfolio_optimizer -> domain.portfolio_optimizer`;
- `delivery_share_code_transport -> domain.sportybet_share_code`.

All records must remain `allowed_profiles=["SHADOW"]` and
`main_authority=false`. Recording the delivery component identity never invokes
share-code delivery. A runtime caller cannot provide an alternative component
registry to the public canonical resolver used by the collector.

### Temporal proof

`common_as_of_proven=True` is not accepted as caller authority. P3.0-E1 derives
an `as_of_proof` receipt using
`P3_0_SINGLE_PROSPECTIVE_CAPTURE_WINDOW_LINEAGE_V1`, binding:

- capture ID and capture start/end;
- exact fixture identity;
- legacy decision observation/effective evaluation time (the supported legacy pipeline exposes no independent internal model clock);
- probability evaluation time;
- provider quote observation time;
- Price-All evaluation time;
- Router effective evaluation time (the P2.1 compatibility Router is pure over the verified Price-All bundle and acquires no second clock); and
- kickoff.

The proof fails closed for missing timestamps, future-dated quote/probability at
Price-All, Price-All after Router, non-prematch stage times, or evaluation times
outside the single prospective capture window. It does not invent a freshness
tolerance or backdate evidence.

## Legacy observer neutrality

`AnalysisPipeline.run_pipeline_snapshot(..., evidence_observer=...)` remains
optional and default-off. The observer receives deep copies only after the
legacy result and exported row have been computed. Its return value is ignored,
and observer failures are contained. Therefore it cannot replace or mutate the
user-visible legacy decision.

`LegacyEvidenceObserver` uses explicit field projections. It deliberately drops
legacy Kelly/staking advice from durable evidence while retaining the decision,
market, probability, price-availability, edge, risk and evidence-report facts
needed for the future comparison. Sensitive account/session/authentication
material fails closed.

The sensitive-key policy is token/exact-key based rather than substring based,
so legitimate football fields such as `possession` are preserved while
`session`, `session_id`, authorization, cookies, bearer/token/password/secret,
wallet/account-balance, stake/wager and share-code material remain forbidden.
Explicit false safety/authority booleans are allowed as receipts, including the
canonical `MarketProbabilityBundle.authority.wager=false` field; a true wager
authority value still fails closed.

## Fixture identity and artifact path safety

Fixture joins use exact reviewed fixture identity/policy only. No fuzzy team
matching and no invented kickoff tolerance exist.

The logical `fixture_capture_id` is validated, but it is never used directly as
a filesystem path. Per-fixture directories use
`SHA256(fixture_capture_id)` as the storage key. Absolute paths, Windows drive
paths, separators, `.`/`..` and control characters are rejected.

Artifact verification requires every manifest path to be normalized, relative,
inside the artifact root and non-symlinked. Duplicate paths, path traversal,
absolute paths, digest mismatch, missing files and unmanifested extra files all
fail closed. The actual regular-file set must equal `manifest.json` plus the
exact manifest declarations.

## Source-controlled paired capture entrypoint

`scripts.capture_p3_0_paired_evidence` is the reviewed explicit/default-off
operational entrypoint. When separately authorized after merge it:

1. validates one through seven explicit rolling UTC fixture dates and a bounded
   fixture cap;
2. resolves the source-controlled SHADOW canonical core;
3. reuses the reviewed Current Shadow acquisition path only through
   `_acquire_router_inputs`, with the exact-date issuer temporarily installed
   and restored in `finally`;
4. stops before Portfolio optimization/final selection and before share-code delivery (the reviewed source helper may still build its existing post-Router compatibility input envelope);
5. projects the actual canonical probability bundle, provider semantics, exact
   quote snapshot, Price-All compatibility output and Router compatibility
   output already produced by that research path;
6. runs the supported `AnalysisPipeline` against those exact reconciled fixtures
   with the default-off observer; its `bookmaker_odds` input is projected from
   the same already-captured exact SportyBet `ShadowExactQuote` snapshot used by
   the canonical Current Shadow side, so paired capture performs no second
   bookmaker acquisition and cannot compare the two decisions against different
   price snapshots;
7. joins only exact fixture identities; and
8. writes one immutable evidence artifact.

The legacy execution identity records repository/data/model artifact hashes when
available, but makes no claim that the complete historical legacy pipeline can
later be re-executed solely from those hashes. P3.0 compares the preserved
legacy decision evidence; missing replay lineage remains explicit.

## Hosted surface

`.github/workflows/p3-0-comparison-evidence-capture.yml` is
`workflow_dispatch` only. It has no schedule and no issue-comment trigger. It
restores the already-reviewed Current Shadow history/bootstrap material and, for
exact reconciliation replay continuity, establishes a worker-local fixture-
identity state path before capture. It may restore that exact state document
only from a successful main-branch `current-shadow-all-market-request` artifact;
when no such document is available, the configured empty worker-local path still
persists same-worker learning for replay verification. The identity module
continues to validate restored bytes and enforce append-only retained-state
ancestry fail-closed. The workflow then resolves exact lineage main, invokes the
paired collector and uploads the P3.0 artifact.

The workflow contains no email step and no login/cookie/wallet/staking/wagering
or share-code create/reload operation. It must not be triggered pre-merge.

## Prospective-only rule

P3.0-E1 never backdates or reconstructs missed historical evidence and never
attaches a later quote to an earlier decision. A row is only
`P3_0_CAPTURE_COMPLETE`, `P3_0_CAPTURE_PARTIAL`, or
`P3_0_CAPTURE_UNUSABLE`; P3.0 decision-match/severity classifications are not
emitted here.

A successful merge of P3.0-E1 still does **not** satisfy P3.0. A separately
authorized bounded post-merge capture must first produce real complete rows,
and the resulting corpus must then be reviewed for the P3.0 one-week or
sufficiently-large requirement before the comparator is implemented. P3.1 has
not started.

## Post-PR #371 persisted identity-state alias ancestry migration

Owner authorization comment `5722646108` was consumed for bridge run
`35287227717`, which dispatched P3.0-E1 capture run `35287237183` on
`be8e35dd179b44b76ff3aee1f7b3dfdad55a3f6c` for fixture dates
`20260917` through `20260923` with cap `50`. The capture failed only in the
Router-only capture step with `CurrentShadowFixtureIdentityStateError: identity
state seed registry drifted`. Its failure artifact was `10524269182`
(`a9d0aed1a581a4804bf2bf3cb9cdc4bd290777a3e219fe3dd5de9cddd496e7ab`);
the retained source-diagnostics artifact was `10524693269`
(`062890dd79e4806e2f21dd90708de9205aceea1d5a2fbd90cb582ce1cffe880e`).

The workflow had restored trusted-main Current Shadow identity state from run
`34141385342`, whose source head was
`012f15f8ea81dc32c3404880a854815e5e7078ca`. The retained document was valid
schema v1. Its field named `seed_registry_sha256` was actually the complete
stable-identity registry hash, including the reviewed display-name alias policy.
PR #371 changed aliases from V1 to V2 without changing stable seed tables, so
the valid restored document was incorrectly rejected as seed drift.

State schema v2 separates immutable seed-only identity from ordered reviewed
alias-policy ancestry. It accepts only the exact V1-to-V2 transition recorded
in the stable identity registry; it does not accept arbitrary prior hashes,
corrupt state, conflicts, or evidence-less learned bindings. Migration preserves
the validated learned identities, evidence records, authority, exact matching,
and append-only retained replay protections. It adds no provider retry and no
model, pricing, Router, Portfolio, login, cookie, wallet, stake, wager, or
share-code authority. P3.0 comparator and P3.1 remain not started, and
`SOURCE_REVIEW_COUNTER` remains `4 / 5`.

Follow-up review found that schema-v1 admission still needed to bind the
historical immutable seed-only identity directly, rather than relying only on
the historical full registry hash. The reviewed transition now records the
historical seed-only SHA-256
`7fe662fc91a80daabf1e774ddd5c8ecdb5215eaf63adb03822b3fb05f872df79`
and requires it to equal the current seed-only registry identity. Accordingly,
this alias-only V1-to-V2 migration is unavailable after any future seed-table
change; that change requires a new reviewed migration contract. The corrected
stable-identity registry SHA-256 is
`5fbbd1f20e85ba0559328048e9fa8fcca5ed2e127a3adb215a46a6c6a3ddffd6`
and the corrected fanout contract SHA-256 is
`941ce2d1eba567bd6e57aa0be8d7417f0c5d9631c5c94a500399e77d653d697b`.
No provider retry or authority change was used for this repair.

## Run 35404223536 retained source-reconciliation continuity

Authorization comment `5737234207` was consumed by bridge `35404214156`, which
dispatched capture `35404223536` on main
`07b5c2bbcb803675aa538464cc528f8993f8d7bb`. The bounded request used dates
`20260918` through `20260924` and cap `50`. The capture restored the trusted
identity state successfully, then failed closed with zero Router inputs. The
failure artifact is `10572001772`
(`35ab7daef5af7af7ea972f1fbfb297f04d123e0e07e303faffbf3537cd1892b1`)
and retained diagnostics are `10571711837`
(`4f5947c2317fb42709001174e72e72d51881f4389f35ebdd8657ec6b2713c959`).

The retained artifact proves five exact full-UTC, oriented fixture identities:
`66299550 -> 5071366`, `67817882 -> 5140036`, `67912308 -> 5161643`,
`71936122 -> 1000017238`, and `72053630 -> 5833797`. Six literal,
competition-scoped aliases are added as alias-policy V3; the remaining five
provider events remain rejected. No fuzzy, suffix, `(W)`, accent, competition,
orientation, or time-tolerance normalization is introduced.

Schema-v2 persistent identity ancestry now admits only reviewed chains ending
in V3: V3, V2->V3, or V1->V2->V3. Historical V2 snapshots are migrated by an
atomic V2->V3 append; seed-only identity remains
`7fe662fc91a80daabf1e774ddd5c8ecdb5215eaf63adb03822b3fb05f872df79`.
The transition is bound to this retained run and diagnostics digest. No live
retry, provider acquisition, model/pricing/Router/Portfolio change, or authority
increase occurs in this continuity work. P3.0 comparator and P3.1 remain not
started; `SOURCE_REVIEW_COUNTER` remains `4 / 5`.

## Canonical source-to-Router live readiness and pre-router architecture closure

Post-PR #373 live capture run `35409481576` revealed a recurring failure loop at
the pre-router source boundary where zero Router inputs were produced despite
reconciled identities. Architectural analysis identified two root causes:

### Root Cause A: Tournament Fanout Endpoint Scope Collapse (Global-Echo Pattern Diagnostic)

The SportyBet tournament fanout endpoint (`/api/ng/factsCenter/pc/upcomingEvents`)
returned identical 10 global events across multiple distinct tournament requests.
The retained responses do not demonstrate that the request-target category/tournament
parameters scope the response (referred to as the "global-echo pattern" ATHENA diagnostic
label). This was masked in earlier tests but caused complete discovery failure during live
execution.

Resolution:
1. `validate_fanout_request_scope` in
   `domain.current_shadow_sportybet_catalog_fanout_reconciliation` asserts that
   distinct tournament requests return distinct event sets; any repeated identical
   event set fails closed with `FANOUT_REQUEST_SCOPE_UNPROVEN`.
2. The pre-router acquisition path in `domain.current_shadow_all_market_runner`
   was canonicalized to use the already-reviewed, deterministic paginated global
   discovery endpoint (`/api/ng/factsCenter/liveOrPrematchEvents?sportId=sr:sport:1&pageSize=100&pageNum=<n>`)
   via `domain.current_shadow_sportybet_paginated_discovery_reconciliation`.
3. The paginated discovery contract is pinned to SHA-256:
   `106c296d2f5428dfdc1a27782c230bd57cde1f957df23d119a3989c4d9040a90`.

### Root Cause B: Pre-Router Candidate Classification & Failure Taxonomy

Counterpart audit diagnostics previously conflated raw kickoff-matching events,
policy-approved counterparts, and reconciliation-authorized counterparts, obscuring
why events were rejected.

Resolution:
1. `scripts.analyze_p3_0_e1_source_diagnostics` strictly classifies candidates into:
   - `RAW_FOTMOB_COUNTERPART`: Same kickoff time only;
   - `CURRENT_SHADOW_POLICY_APPROVED_FOTMOB_COUNTERPART`: Admitted by competition hierarchy;
   - `RECONCILIATION_AUTHORIZED_COUNTERPART`: Fully authorized by identity recovery / alias registry.
   Unadmitted competitions (e.g., K-League 1, NWSL) are classified as
   `POLICY_UNAPPROVED_COMPETITION` and excluded from compatibility summaries.
2. `scripts._p3_0_paired_capture_part2` enforces a bounded taxonomy of failure reasons:
   - `NO_RECONCILED_PROVIDER_EVENTS_DISCOVERED`
   - `NO_RECONCILIATION_AUTHORIZED_FOTMOB_COUNTERPART`
   - `NO_MARKETS_RECONCILED_FOR_ROUTER`
   - `ZERO_ROUTER_INPUTS_POST_PRICING`

### Pre-Flight No-Network Live Readiness Gate

`scripts/verify_p3_0_e1_live_readiness.py` executes 14 offline checks (Checks A
through N) before any live provider acquisition is permitted in CI:
- Strict socket/network blocking assertion (`strict_network_block`);
- Codebase compilation and lineage main SHA verification (`c5ec9a23486a594d2df279521b6065744fa9a389`);
- Pinned discovery contracts and fanout scope validation;
- Workflow and safety invariant assertions (`login`, `cookies`, `wallet`, `staking`, `bet`, `wager_placed` = False);
- Zero live authorizations spent invariant.

The gate writes `p3-0-e1-live-readiness.json` with status
`P3_0_E1_LIVE_READINESS_VERIFIED` and an exact SHA-256 hash.

## Post-#374 prospective source continuity

Retained capture run `35441111017` is a source-viability finding, not a
FotMob identity failure. Its reviewed `liveOrPrematchEvents` page contained
79 provider page items and 136 extracted events; all 136 were `status=1`,
non-prematch, and H1/HT/H2 in-play rows at
`2026-09-19T11:49:46.016668Z`. The retained shape is pinned by primary
artifact `10584076663` (`81b7e0dfb9fb91cbc961d591c876010330025da24f1aafa3dca4ff038c93222e`)
and diagnostics artifact `10584211437`
(`a9facd41768ad271cae6ccb72f0c092b6f640d82daf0de5c46509af55766064d`).

The canonical pre-Router source for both `SUPPORTED_REQUEST` and
`P3_E1_PRE_ROUTER_CAPTURE` is now the already-reviewed upcoming source
`/api/ng/factsCenter/wapConfigurableUpcomingEvents?sportId=sr%3Asport%3A1&_t=<response-scoped nonce>`
under `ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1`. Its upstream source
contract remains `90c14bd68ed6e8205c16fedfa815d120c53f2af1a3a8f362eee2702a4223b9ff`;
the Current Shadow compatibility wrapper is pinned separately. The old
paginated source remains replayable historical evidence only.

The first-boundary failure code for a non-empty provider universe with zero
prematch/bookable events is `PROVIDER_DISCOVERY_NO_PREMATCH_EVENTS`, before any
FotMob counterpart decision, direct event detail, Price-All, or Router input.
