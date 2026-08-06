# Fixture catalog compiler

`scripts.manage_fixture_catalog` compiles a strict ATHENA fixture catalog from reviewed FotMob fixture-provenance records.

## Role split

- **FotMob** is the fixture source only.
- **SportyBet** remains a separate pricing-source candidate.
- Input acquisition stays a reviewed human/operator process.
- The tool performs no network access, scraping, browser automation, odds collection, or bet authorization.

## Contract

The strict catalog intentionally strips team names and provenance. It keeps only:

```json
{
  "schema_version": 1,
  "fixtures": [
    {
      "fixture_identifier": "FOTMOB:<opaque-id>",
      "kickoff": "2026-08-07T00:05:00.000000Z"
    }
  ]
}
```

The manifest preserves provenance separately, including reviewed timestamps, source references, and evidence hashes.
Evidence must already be saved before its SHA-256 is recorded.

The catalog is reusable across all ATHENA markets.
A FotMob fixture still requires later SportyBet event reconciliation, and ambiguous cross-source mapping must become `UNKNOWN`.
The 100-fixture minimum remains specific to the later Win Either Half interpretation campaign, not to generic catalog validity.

## CLI

Generation:

```bash
python -m scripts.manage_fixture_catalog \
  --input .cache/athena-research/win-either-half/operator-intake/fixture-source/fotmob/future-fixtures.draft.jsonl \
  --evidence-root .cache/athena-research/win-either-half/operator-intake/fixture-source/fotmob/evidence \
  --as-of 2026-08-06T00:00:00Z \
  --minimum-lead-seconds 86700 \
  --catalog-output .cache/athena-research/win-either-half/future-fixtures.json \
  --manifest-output .cache/athena-research/win-either-half/fixture-catalog-manifest-v1.json
```

Verification:

```bash
python -m scripts.manage_fixture_catalog \
  --input .cache/athena-research/win-either-half/operator-intake/fixture-source/fotmob/future-fixtures.draft.jsonl \
  --evidence-root .cache/athena-research/win-either-half/operator-intake/fixture-source/fotmob/evidence \
  --as-of 2026-08-06T00:00:00Z \
  --minimum-lead-seconds 86700 \
  --check-catalog .cache/athena-research/win-either-half/future-fixtures.json \
  --check-manifest .cache/athena-research/win-either-half/fixture-catalog-manifest-v1.json
```

## Notes

- A completed catalog compiler does not activate markets or authorize betting.
- The catalog must remain deterministic byte-for-byte for identical validated inputs.
- Provenance lives in the manifest, not in the strict catalog.
