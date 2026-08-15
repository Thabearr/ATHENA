# Reviewed FotMob ordinary-FT finished-score adapter validation

## Purpose

This boundary executes the reusable adapter introduced by PR #95 against the exact
preserved PR #85 post-finish capture pair. It freezes the deterministic adapter
result and its source lineage before ATHENA returns to the separate capability-
promotion decision.

It is an execution/receipt boundary only. It does **not** register a source
capability, mutate the parent reviewed catalog, prove historical coverage, or
authorize source-history, model, probability, pricing, selection, production, or
betting use.

## Exact base

```text
main d836e6bafb71bdefbc47ae00895229eaa0a136a5
```

Execution identity:

```text
dataset athena-fotmob-data-matches-ordinary-ft-finished-score-adapter-validation-v1
scope   EXECUTE_PR95_REUSABLE_ADAPTER_AGAINST_EXACT_PRESERVED_PR85_PAIR_ONLY
state   EXECUTED_EXACT_PR85_PAIR_28_ORDINARY_FT_SCORES_QUALIFIED_PENALTY_BLOCKED
```

## Frozen adapter ancestry

PR #96 binds the exact merged PR #95 adapter blob:

```text
868563206e09010fce74b4ba7954028930baad54
```

It also binds the preserved PR #85 evidence receipt blob and the unchanged source
capability registry blob. The adapter is executed directly; PR #96 does not replace
its structural, repeat/stability, reason, awarded-result, or penalty guards.

## Exact evidence pair

Both captures are the preserved reviewed `/api/data/matches` network captures for
request identity:

```text
request_date 20260814
timezone     UTC
ccode3       NGA
```

Capture A:

```text
capture id    a18e843fabe5aca74846b160
raw sha256    fbcf24729973dbe7153c87fe9f37bd988aaca14ad10cce6b260ac7df650ff80f
manifest sha  27bfb5dc90c67a305bdb045a7ff33010d87c4109925384d3e6d2a6e058d7b302
raw size      114920
observed      2026-08-14T17:12:02.437509Z
```

Capture B:

```text
capture id    e28d9ce746c1ef9102995517
raw sha256    175c6f94788fbf676e08a288ff0c46a995cd8798d60e4bc5044076e3c9713f8d
manifest sha  d60501a5b7b1b4e5c810a0a0463bdcecb3a0b806110ad4542c314f8fe536824e
raw size      114964
observed      2026-08-14T17:17:13.043248Z
```

Exact separation is `310605739` microseconds.

## Execution result

The exact reusable-adapter result is frozen as:

```text
pair status                    QUALIFIED_WITH_ORDINARY_FT_SCORES
terminal candidate union       29
qualified ordinary-FT scores   28
blocked penalty fixtures        1
```

The one blocked fixture remains:

```text
fixture 5844873
status  BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS
```

It does not enter ordinary home/away finished-score output. Fixture `5186581`
remains the ordinary audit anchor with source-reported score `3-1`.

Exact canonical PR #95 adapter result:

```text
sha256 7e3fcb2c8a4fa8f883ec7dcac2fd15ea8d2f1aa359c5c5f42ab7eaf604bdce27
size   22570 bytes
```

The canonical projection of all 28 qualified score records is additionally frozen:

```text
ffdb20556808a1a6459d959b050e3aa5780f3c017d6971adf0c17a3c91ce03ab
```

This projection hash covers the qualified records themselves, including fixture,
league and team source IDs, kickoff, source score, exact ordinary-FT reason tuple,
observation timestamps, raw hashes, and manifest hashes.

## Canonical PR96 receipt

```text
sha256 09dd9fdff1eddb7b421e968c8de93262b09ce526adeb3d3b95050ddf1f2d4562
size   3610 bytes
```

The canonicalizer accepts only the exact frozen outcome. Mutating adapter identity,
counts, penalty disposition, registration state, next-boundary identity, or any
safety flag fails closed.

## Capability consequence

There is still **no registry promotion in PR #96**.

The parent source remains:

```text
fotmob_data_matches_reviewed_catalog
full_time_score           NOT_CAPTURED
reliable_fixture_identity CONFIRMED
historical_coverage       UNKNOWN
```

The proposed derived source key remains absent:

```text
fotmob_data_matches_reviewed_ordinary_ft_finished_score
```

PR #96 therefore proves that the reviewed reusable adapter reproduces the exact
preserved evidence outcome. It does not itself decide or perform capability
registration.

## Semantic limits

A qualified record retains PR #83's narrow meaning: source-reported finished score
only. It is not a claim about regulation-time score, extra-time treatment, penalty
shootouts, bookmaker settlement, global `status.reason` semantics, historical
coverage, or source freshness.

## Next boundary

```text
EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FULL_TIME_SCORE_CAPABILITY_PROMOTION_ASSESSMENT_WITH_VALIDATED_ADAPTER
```

That assessment can now revisit the frozen PR #93 capability-promotion protocol
with a reusable adapter that both exists and has passed this exact validation. Any
actual source-capability registry mutation remains a later, separate reviewed
boundary.
