# Evidence baselines

ATHENA freezes an evidence baseline before research modelling so later work can
prove which code revision, logical observations, database schema, readiness
result, and local football-data.co.uk cache files were evaluated. The baseline
is a small, versioned JSON manifest; it is not a copy of the evidence.

The logical evidence fingerprint hashes a canonical representation of the
observations selected by the existing half-time coverage audit. It is stable
across SQLite row order and page layout, but changes when evidence-relevant
scores, provenance, identity, metadata, validation, or conflict state changes.
The schema fingerprint covers normalized user-defined SQLite schema objects.
The cache manifest hashes each CSV with its relative path and byte size.

These fingerprints prove byte-for-byte equality of their canonical inputs.
They do not prove that a provider was correct, that the local files represent
complete historical coverage, or that a betting market is safe to enable.
Database files, raw cached CSVs, credentials, absolute paths, and raw provider
payloads remain untracked and are never embedded in the artifact.

After this tooling is merged, generate the real local baseline from a clean
tracked worktree:

```powershell
python -m scripts.freeze_evidence_baseline --database database/athena.db --cache-directory .cache/football-data-uk --output artifacts/evidence-baselines/half-time-ready-for-research.json --require-ready --expect-total-fixtures 21829 --expect-valid-half-time 21791 --expect-missing-half-time 38 --expect-cache-files 66
```

Generation refuses to overwrite an existing artifact unless `--force` is
provided. To verify the same evidence later:

```powershell
python -m scripts.freeze_evidence_baseline --database database/athena.db --cache-directory .cache/football-data-uk --check artifacts/evidence-baselines/half-time-ready-for-research.json
```

`--require-ready` checks the existing research-readiness result, invalid and
conflict counts, league metadata completeness, tracked Git cleanliness, and
the explicit disabled status of both Win Either Half markets. A
`READY_FOR_RESEARCH` result never enables either market and is not betting
approval.
