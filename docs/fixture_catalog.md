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
- Records are sorted by `(kickoff, fixture_identifier)` and serialized as canonical JSON Lines: exactly one compact UTF-8 JSON object per line with sorted keys, deterministic separators (`allow_nan=False`), and a trailing newline per line.
- The normalized digest reflects the exact set of validated records; adding, modifying, or removing a record changes the digest, whereas raw whitespace differences in the source input file do not change normalized bytes.

### Security and path integrity

- Catalog and manifest output and check paths must differ; passing identical or aliased paths (including canonical aliases or hard links) is rejected.
- Pre-existing or colliding transaction backup and rollback paths are rejected fail-closed; the transaction never deletes, overwrites, or trusts pre-existing transaction artifacts.
- Check mode and generation mode strictly reject symlinks and symlinked parent path components.
- Output paths within the repository must reside under `.cache/athena-research/` and cannot overwrite tracked Git files.
- Policy checks apply to the canonical resolved destination paths, preventing traversal or prefix aliasing bypasses.
- Individual file replacements are atomic within their destination filesystem, and detected runtime errors trigger exact pair rollback and artifact cleanup. Abrupt process termination or power loss between replacements is not claimed to be cross-file crash atomic; check mode should be used to verify pairs before consumption, and incomplete or drifted pairs must be regenerated from reviewed input.
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
