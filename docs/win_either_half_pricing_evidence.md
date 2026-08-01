# Win Either Half pricing-evidence research

Stage 5A defines how ATHENA may validate historical or replayed bookmaker
quotes for Win Either Half research. It does not fetch odds, calculate betting
value, approve thresholds, recommend stakes, or activate a market.

## Frozen ancestry

The exporter fails closed unless the committed Stage 4B calibration manifest
has its exact canonical logical identity and continues to select:

- Home: `isotonic_calibration_v1`
- Away: `identity_calibration_v1`

It separately verifies the ignored calibrated-predictions CSV by exact row
count (36,318), byte size (6,705,242), and SHA-256. Fixture identity, kickoff,
target, split, and evaluation role come only from that frozen file. The roles
remain distinct:

- `CALIBRATION_FIT_OOF`
- `VALIDATION_SELECTION`
- `FINAL_TEST`

The calibrated-prediction catalog is also the complete pricing-coverage
denominator: 21,270 `CALIBRATION_FIT_OOF`, 6,952 `VALIDATION_SELECTION`, and
8,096 `FINAL_TEST` fixture-markets, for exactly 36,318 records. Each frozen
`(fixture_identifier, market_id)` appears once regardless of how many
bookmakers supply evidence. Coverage has an explicitly labelled
`ALL_ROLES_DESCRIPTIVE` total and a separate breakdown for every role. No
unlabeled mixed-role analysis is emitted.

## Research quote schema

Every raw JSONL quote is schema version 1 and contains exactly these contract
fields (additional source fields are not interpreted):

- `schema_version`
- `fixture_identifier`
- `market_id`
- `outcome_id`
- `line`
- `source`
- `quote_snapshot_id`
- `observed_at`
- `fixture_kickoff`
- `decimal_odds`
- `is_genuine`
- `provider_event_identifier`
- `provider_market_identifier`
- `provider_selection_identifier`

The only permitted markets are `HOME_WIN_EITHER_HALF` and
`AWAY_WIN_EITHER_HALF`; the only permitted outcomes are `YES` and `NO`.
`line` must be JSON `null`. Identifiers are canonical and case-sensitive. The
validator does not use aliases or fuzzy matching.

Provider mappings are a separate JSON list. Every supplied row is validated,
even when no quote references it. Each mapping binds the exact
bookmaker/source, provider event, provider market, and provider selection to
one frozen fixture, canonical market, canonical outcome, and null line. Missing
identifiers, unmapped tuples, or disagreement between provider and canonical
fields produce `PROVIDER_MAPPING_MISMATCH` or a more specific missing/unknown
reason. Provider identifiers remain in accepted and rejected audit output.

Decision timestamps are supplied as a separate JSON list keyed by frozen
fixture identifier. Every supplied row is validated against the frozen catalog,
even when no quote references it: identifiers must be known and unique, and
timestamps must be present, timezone-aware, and strictly before the frozen
kickoff. They are research protocol inputs, not selected from TEST performance.

## As-of eligibility and freshness

`observed_at`, `decision_at`, and fixture kickoff must be timezone-aware. They
are normalized to UTC for deterministic serialization. A quote is eligible
only when:

- `observed_at <= decision_at`
- `decision_at < fixture kickoff`
- `observed_at < fixture kickoff`
- quote age is non-negative and no greater than the configured maximum

The default and documented maximum age is 900 seconds. A quote exactly 900
seconds old is eligible; one 901 seconds old is stale. Quotes observed after
the simulated decision or kickoff never enter a complete snapshot.

## Complete snapshots and deterministic selection

A candidate snapshot is grouped only by fixture, canonical market, source, and
snapshot identifier. A complete market snapshot contains exactly one `YES` and
one `NO` quote. Both
must share fixture, canonical market, null line, source, snapshot identifier,
and observation timestamp. Duplicate outcomes fail closed. Missing outcomes
remain `UNAVAILABLE` with `INCOMPLETE_MARKET`. Outcomes are never combined
across bookmakers, snapshots, or observation times. A shared snapshot identity
whose outcomes disagree on `observed_at` produces one rejected snapshot with
`MIXED_OBSERVED_AT`; it is not split into two misleading incomplete snapshots.

All eligible complete snapshots remain auditable. For each fixture, market,
and bookmaker, one snapshot is marked as the deterministic latest eligible
snapshot: the greatest `observed_at` not after `decision_at`. If observation
timestamps tie, the lexically greatest `quote_snapshot_id` wins. ATHENA does
not choose a best price across bookmakers and does not synthesize a market from
different sources.

Validation uses the machine-readable statuses `ACCEPTED`, `REJECTED`, and
`UNAVAILABLE`. Reasons include unknown identity, invalid odds or line, missing
provenance, naive or unsafe timestamps, staleness, incomplete markets,
duplicate outcomes, mixed snapshot evidence, mapping mismatch, and non-finite
calculations. Unknown data stays unknown; malformed evidence is not silently
defaulted.

Every frozen fixture-market also receives one deterministic availability row.
Availability requires at least one bookmaker with a selected latest complete
eligible snapshot. Unavailability reasons use this precedence:

1. `NO_QUOTE_RECORDS` when no raw quote row exists;
2. `NO_ACCEPTED_QUOTES` when raw rows exist but none pass quote validation;
3. `NO_ELIGIBLE_COMPLETE_SNAPSHOT` when accepted rows exist but no complete
   eligible snapshot is selected.

An empty quote input therefore reports 36,318 unavailable fixture-markets,
not an empty denominator. Globally and within every evaluation role,
`available + unavailable` equals the frozen fixture-market total.

## Pricing calculation

Only finite genuine decimal odds strictly greater than 1.0 are accepted. For a
complete YES/NO market:

1. raw implied probability is `1 / decimal_odds` for each outcome;
2. overround is the sum of the two raw implied probabilities;
3. multiplicative normalization divides each raw probability by overround;
4. the two de-vigged probabilities must be finite, bounded by `[0, 1]`, and sum
   to 1 within the canonical `1e-12` tolerance.

The method is recorded as `multiplicative_normalization`. Pricing arithmetic
uses an explicit local decimal context with fixed precision and
`ROUND_HALF_EVEN`; numerical output is canonicalized to 12 decimal places
before serialization. Quantization and arithmetic failures become structured
`INVALID_ODDS` or `NON_FINITE_RESULT` evidence rather than escaping as unrelated
exceptions. Stage 5A does not compare alternative de-vig methods.

The following fixed bands are prepared for later descriptive analysis and are
explicitly named bookmaker fair-probability bands:

- `[0.0,0.2)`
- `[0.2,0.4)`
- `[0.4,0.6)`
- `[0.6,0.8)`
- `[0.8,1.0]`

They are not Stage 4 model-probability bands and are not bookmaker odds bands.
No price-band performance result is generated by this tooling PR.

## Output lifecycle

The source-agnostic exporter accepts raw quote JSONL, exact provider-mapping
JSON, and decision-timestamp JSON:

```powershell
python -m scripts.export_win_either_half_pricing_evidence `
  --quotes path/to/quotes.jsonl `
  --provider-mappings path/to/provider-mappings.json `
  --decisions path/to/decision-times.json `
  --manifest-output artifacts/research-manifests/win-either-half-pricing-v1.json
```

Direct-script execution is also supported. Generation requires a clean tracked
worktree, uses only read-only frozen inputs, makes no network request, and
writes UTF-8/LF outputs atomically. Existing outputs are not overwritten unless
`--force` is deliberate. `--check` recomputes the contract and uses ATHENA's
existing exact-revision or artifact-only-descendant policy; generated time is
not semantic evidence.

Future local outputs remain ignored:

- `.cache/athena-research/win-either-half/pricing-valid-quotes-v1.csv`
- `.cache/athena-research/win-either-half/pricing-rejected-quotes-v1.csv`
- `.cache/athena-research/win-either-half/pricing-snapshots-v1.csv`
- `.cache/athena-research/win-either-half/pricing-fixture-market-coverage-v1.csv`
- `.cache/athena-research/win-either-half/pricing-coverage-v1.json`

No real quote data or real Stage 5A manifest is committed by this PR.

## Holdout governance

`FINAL_TEST` is season 2025-26. It was exposed in the Stage 4A benchmark final
evaluation and again in the Stage 4B calibration final evaluation, so it is an
already-consumed audit holdout rather than pristine evidence for iterative
policy tuning. The future manifest records this status machine-readably.

Quote source, provider mapping, decision timestamp, freshness window, snapshot
selection, de-vig method, and availability rules must be frozen without using
`FINAL_TEST` outcomes or performance. This holdout alone cannot authorize
production. Any production approval requires an untouched future-season or
prospective holdout.

## Safety boundary

Stage 5A outputs contain no edge, Kelly, expected-value, profitability, stake,
threshold-approval, recommendation, accumulator, or `BET` decision fields.
Pricing evidence does not establish bookmaker value or deployment readiness.
Both Home and Away Win Either Half remain `DISABLED` in the production model
status registry.
