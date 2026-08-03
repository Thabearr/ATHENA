# Win Either Half Prospective Pricing Observations (Stage 5B2)

Stage 5B2 records and evaluates offline prospective attempts to observe exact Home Team to Win Either Half and Away Team to Win Either Half YES/NO bookmaker snapshots at predeclared times before kickoff.

This is operational availability evidence. It is not model evaluation, value analysis, source integration, execution or production approval.

## Why an attempt ledger is required

A missing quote does not prove that a bookmaker market was unavailable. The system must know whether a check happened and what happened during that check. Every fixture therefore has twelve expected attempt keys:

- two canonical markets; and
- six frozen offsets.

A missing attempt is `UNKNOWN / NO_ATTEMPT_RECORD`, never `UNAVAILABLE`.

## Frozen candidate offsets

The exact seconds before kickoff are:

- 86400 - 24 hours
- 21600 - 6 hours
- 10800 - 3 hours
- 3600 - 1 hour
- 1800 - 30 minutes
- 900 - 15 minutes

Stage 5B2 measures all six offsets. It does not select one. `selected_offset_seconds` remains null and `selection_authorized` remains false.

## Attempt results

Every supplied attempt uses exactly one result:

- `QUOTES_CAPTURED`
- `MARKET_UNAVAILABLE`
- `FIXTURE_UNAVAILABLE`
- `SOURCE_UNAVAILABLE`
- `CAPTURE_ERROR`

The resulting availability statuses are:

- `AVAILABLE`
- `UNAVAILABLE`
- `UNKNOWN`
- `INVALID`

Structural contradiction is always `INVALID` and takes precedence over `UNKNOWN`.

## Attempt timing

For each expected fixture-market-offset:

`scheduled_at = kickoff - offset_seconds_before_kickoff`

The equality is exact. `attempted_at` must be within plus or minus 300 seconds of `scheduled_at` and must be strictly before kickoff.

## Provider mapping semantics

Provider mappings are partial evidence.

- `QUOTES_CAPTURED` requires an exact fixture, market, YES and NO mapping.
- `MARKET_UNAVAILABLE` requires an exact fixture/event mapping while the target market mapping is absent.
- `FIXTURE_UNAVAILABLE` requires the fixture mapping to be absent.
- `SOURCE_UNAVAILABLE` may occur even when an older mapping is known.
- `CAPTURE_ERROR` may carry no event/market identifiers or a complete exact identifier pair; a partial pair is invalid.

This prevents availability claims from contradicting the mapping evidence.

## Exact snapshot integrity

An available snapshot requires exactly one genuine YES quote and one genuine NO quote linked to the same attempt. Both rows must match the exact fixture, canonical market, provider, source, bookmaker, provider event, provider market, quote snapshot and observation timestamp.

The line is null. Decimal input odds must be finite and greater than 1. Quote odds are validated privately but are not emitted by Stage 5B2 outputs.

`observed_at` must be at or before `attempted_at`, strictly before kickoff and no more than 900 seconds old at `attempted_at`. Exactly 900 seconds is eligible; anything older is stale.

Rows from different attempts, providers, bookmakers, snapshots or timestamps are never combined.

## Explicit unavailability

A valid `MARKET_UNAVAILABLE`, `FIXTURE_UNAVAILABLE` or `SOURCE_UNAVAILABLE` attempt with no attached quote rows produces `UNAVAILABLE`.

`CAPTURE_ERROR` produces `UNKNOWN`, not `UNAVAILABLE`.

Any raw quote row attached to an unavailable or capture-error attempt makes the evidence contradictory and therefore `INVALID`, even when that quote row is itself malformed.

## Inputs

The exporter reads local files only:

1. Stage 5B1 source-qualification JSON;
2. fixture JSON;
3. partial provider-mapping JSON;
4. observation-attempt JSON Lines;
5. quote JSON Lines; and
6. the committed Stage 5B2 protocol.

It performs no network request, scraping, browser automation or credential use.

## Outputs

One atomic ignored evidence bundle contains:

- `normalized-attempts-table-v1.csv`
- `valid-quotes-table-v1.csv`
- `rejected-quotes-table-v1.csv`
- `validated-snapshots-table-v1.csv`
- `evaluations-table-v1.csv`
- `prospective-replay-summary-v1.json`
- `prospective-replay-manifest-v1.json`

The manifest records raw input hashes, output hashes and row counts, the exact protocol, Git revision, market and model-status registries, snapshot rules, summary accounting and holdout governance.

## Generate an evidence bundle

```bash
python -m scripts.export_win_either_half_prospective_replay \
  --source-qualification path/to/source-qualification.json \
  --fixtures path/to/fixtures.json \
  --provider-mappings path/to/provider-mappings.json \
  --attempts path/to/attempts.jsonl \
  --quotes path/to/quotes.jsonl \
  --manifest-output .cache/athena-research/win-either-half/prospective-pricing/prospective-replay-manifest-v1.json
```

Existing outputs are not replaced unless `--force` is supplied.

## Verify an existing bundle

```bash
python -m scripts.export_win_either_half_prospective_replay \
  --source-qualification path/to/source-qualification.json \
  --fixtures path/to/fixtures.json \
  --provider-mappings path/to/provider-mappings.json \
  --attempts path/to/attempts.jsonl \
  --quotes path/to/quotes.jsonl \
  --check .cache/athena-research/win-either-half/prospective-pricing/prospective-replay-manifest-v1.json
```

Verification is byte-for-byte and fails closed on protocol, input, output, manifest, Git-state or registry drift.

## Safety boundary

Stage 5B2 does not qualify a provider, fetch live odds, calculate fair odds, model probability, edge, expected value or Kelly, select accumulator legs, construct a betslip, generate a booking code, recommend a stake or emit `BET`.

Both Win Either Half markets remain `DISABLED`. A future reviewed stage may freeze a decision offset only after genuine prospective evidence exists. This stage grants no production approval.
