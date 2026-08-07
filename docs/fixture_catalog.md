# Fixture catalog compiler

`scripts.manage_fixture_catalog` compiles a strict ATHENA fixture catalog from reviewed fixture-provenance records.

## Role split

- **FotMob** is the fixture source only.
- **SportyBet** remains a separate pricing-source candidate.
- Input acquisition stays a reviewed human/operator process.
- The tool performs no network access, scraping, browser automation, odds collection, or bet authorization. No real fixture data or acquisition is performed by this repository tooling.

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

### Normalized input semantics

- `normalized_input_byte_size` and `normalized_input_sha256` in the manifest represent the deterministic byte count and SHA-256 digest of the validated provenance records.
- Records are sorted by `(kickoff, fixture_identifier)` and serialized as canonical JSON Lines with sorted keys and UTF-8 encoding.
- This is not the raw source-file digest; raw whitespace, line ordering variations, or omitted unreviewed lines in the source input file do not change the normalized digest.

### Security and path integrity

- Catalog and manifest output and check paths must differ; passing identical or aliased paths is rejected.
- Check mode and generation mode strictly reject symlinks and symlinked parent path components.
- Output paths within the repository must reside under `.cache/athena-research/` and cannot overwrite tracked Git files.
- Atomic two-file updates guarantee that either both catalog and manifest files are committed durably or neither is modified.
- On Windows platforms, directory durability utilizes Win32 `CreateFileW` with `FILE_FLAG_BACKUP_SEMANTICS` and `FlushFileBuffers`; native Windows execution fails closed if directory durability cannot be proven (WSL/Linux is the fallback).

The catalog is reusable across all ATHENA markets.
A FotMob fixture still requires later SportyBet event reconciliation, and ambiguous cross-source mapping must become `UNKNOWN`.
The 100-fixture minimum remains specific to the later Win Either Half interpretation campaign, not to generic catalog validity.

## CLI

Generation:

```bash
python -m scripts.manage_fixture_catalog \
  --input /path/to/fixture-provenance.jsonl \
  --evidence-root /path/to/evidence \
  --as-of 2026-08-06T00:00:00Z \
  --minimum-lead-seconds 86700 \
  --catalog-output .cache/athena-research/future-fixtures.json \
  --manifest-output .cache/athena-research/fixture-catalog-manifest-v1.json
```

Verification:

```bash
python -m scripts.manage_fixture_catalog \
  --input /path/to/fixture-provenance.jsonl \
  --evidence-root /path/to/evidence \
  --as-of 2026-08-06T00:00:00Z \
  --minimum-lead-seconds 86700 \
  --check-catalog .cache/athena-research/future-fixtures.json \
  --check-manifest .cache/athena-research/fixture-catalog-manifest-v1.json
```

## Notes

- A completed catalog compiler does not activate markets or authorize betting.
- The catalog must remain deterministic byte-for-byte for identical validated inputs.
- Provenance lives in the manifest, not in the strict catalog.
