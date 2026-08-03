# Win Either Half Prospective Pricing Replay (Stage 5B2)

Stage 5B2 adds provider-agnostic, offline research tooling to measure whether exact Home Team to Win Either Half and Away Team to Win Either Half YES/NO bookmaker snapshots would have been available and fresh at predeclared times before kickoff.

This stage is operational availability research. It is not model evaluation, value analysis, decision-policy tuning, source integration, execution, or production approval.

## Why this stage exists

Stage 5A froze an exact pricing-evidence contract. Stage 5B1 added evidence-source qualification gates. The 2025-26 FINAL_TEST season has already been consumed by model and calibration evaluation, so it cannot be reused as a pristine holdout for iterative pricing-policy tuning. ATHENA therefore requires prospective evidence before a decision timestamp or production policy can be frozen.

Stage 5B2 provides the deterministic replay machinery for that prospective evidence. It intentionally leaves the final decision offset unselected.

## Inputs

The exporter accepts only local files:

1. A Stage 5B1 source-qualification report whose `prospective_replay_status` is `QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY` or `QUALIFIED_FOR_HISTORICAL_RESEARCH`.
2. A prospective fixture catalog containing future fixture identity, provider event identity, UTC kickoff, both exact Win Either Half markets, and a frozen list of expected sources.
3. Exact provider mappings for every fixture, source, market, and YES/NO outcome.
4. UTF-8 JSON Lines quote records using genuine decimal odds and exact provider identifiers.
5. The committed Stage 5B2 protocol.

No network request is made. The exporter contains no API key, browser, scraper, session, betslip, or booking-code functionality.

## Candidate decision offsets

The committed protocol evaluates these candidate offsets before kickoff:

- 24 hours
- 12 hours
- 6 hours
- 3 hours
- 2 hours
- 1 hour
- 30 minutes
- 15 minutes

The set is a research grid, not a recommendation. Stage 5B2 emits `selection_status: UNSELECTED` and never declares a winning offset.

## Exact quote eligibility

For one fixture, market, source, and candidate offset, ATHENA derives:

`decision_at = fixture_kickoff - candidate_offset_seconds`

A quote can contribute only when all of the following are true:

- schema version is exact;
- fixture, market, outcome, source, snapshot, event, market, and selection identifiers are explicit;
- the canonical market is exactly Home or Away Win Either Half;
- the canonical outcome is exactly YES or NO;
- line is null;
- decimal odds are finite and greater than 1;
- `is_genuine` is true;
- timestamps are timezone-aware;
- quote kickoff equals the frozen fixture kickoff;
- observed time is before kickoff;
- provider mapping exactly matches the fixture, market, and outcome;
- observed time is at or before the candidate decision time;
- quote age at decision is at most 900 seconds.

YES and NO must form one complete same-source, same-snapshot, same-observed-time market. Rows from different sources, snapshots, timestamps, fixtures, or provider markets cannot be combined.

When several complete eligible snapshots exist, the latest `observed_at` wins. A timestamp tie is broken by the lexically greatest `quote_snapshot_id`. This makes selection deterministic without consulting prices or match results.

## Availability reasons

Every denominator row receives one status and one reason:

- `NO_QUOTE_RECORDS`
- `NO_STRUCTURALLY_VALID_QUOTES`
- `NO_QUOTES_AT_OR_BEFORE_DECISION`
- `NO_FRESH_QUOTES_AT_DECISION`
- `NO_COMPLETE_SNAPSHOT`
- `AVAILABLE`

The denominator is frozen as one row per fixture, canonical market, expected source, and candidate offset. Missing quotes therefore remain explicit instead of disappearing from coverage.

## Outputs

All outputs are local and ignored under `.cache/athena-research/`:

- row-level replay CSV;
- rejected-quote audit CSV;
- deterministic summary JSON.

The replay rows contain availability, reason, selected snapshot identity, selected observation time, and quote age. They do not emit decimal odds, fair probabilities, model probabilities, edge, expected value, Kelly, stakes, profits, decision labels, or bets.

The summary reports:

- complete denominator and reconciliation counts;
- availability by candidate offset;
- availability by offset, source, and market;
- same-source availability of both canonical markets for each fixture;
- reason counts;
- support status based on fixture count;
- immutable identities for every input and generated local output;
- consumed-holdout governance;
- disabled market statuses;
- explicit no-production approval.

## Forbidden information

Fixture, mapping, quote, and source-qualification inputs are recursively rejected if they contain match outcomes, scores, targets, labels, model probabilities, calibration probabilities, edge, expected value, Kelly, profitability, stakes, or betting decisions.

The candidate decision offset must be assessed only from operational quote availability, timestamp freshness, source identity, and snapshot completeness. It must never be selected from match outcomes, model performance, price profitability, or the consumed FINAL_TEST period.

## Command

```bash
python -m scripts.export_win_either_half_prospective_replay \
  --source-qualification path/to/source-qualification.json \
  --fixtures path/to/prospective-fixtures.json \
  --provider-mappings path/to/provider-mappings.json \
  --quotes path/to/quotes.jsonl
```

To verify previously generated local outputs:

```bash
python -m scripts.export_win_either_half_prospective_replay \
  --source-qualification path/to/source-qualification.json \
  --fixtures path/to/prospective-fixtures.json \
  --provider-mappings path/to/provider-mappings.json \
  --quotes path/to/quotes.jsonl \
  --check-rows .cache/athena-research/win-either-half/prospective-replay-rows-v1.csv \
  --check-rejected .cache/athena-research/win-either-half/prospective-replay-rejected-quotes-v1.csv \
  --check-summary .cache/athena-research/win-either-half/prospective-replay-summary-v1.json
```

## Safety boundary

Stage 5B2 does not qualify a provider, collect live quotes, freeze a final decision offset, calculate overround or value, enable either market, create an accumulator, construct a betslip, generate a booking code, recommend a stake, or emit `BET`.

Both Win Either Half markets remain `DISABLED`. A later freeze stage may choose a decision protocol only after real prospective data have been collected under this predeclared contract and reviewed without outcome or profitability leakage.
