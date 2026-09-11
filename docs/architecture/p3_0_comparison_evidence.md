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

`f93922d028c40b8a0d4a246f98c99cb9c208a4e83c7b9e6618fb62cd36788f75`

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
False safety/authority booleans are allowed as receipts.

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
restores only the already-reviewed Current Shadow history/bootstrap material,
resolves exact lineage main, invokes the paired collector and uploads the P3.0
artifact.

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
