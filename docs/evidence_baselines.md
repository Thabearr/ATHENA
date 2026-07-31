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

## Baseline lifecycle

First merge the tooling PR. From a clean `main`, generate the real local
baseline. The clean Git revision at that moment is the evidence revision `H`
and is recorded in the artifact as `code.evidence_git_head_sha`:

```powershell
python -m scripts.freeze_evidence_baseline --database database/athena.db --cache-directory .cache/football-data-uk --output artifacts/evidence-baselines/half-time-ready-for-research.json --require-ready --expect-total-fixtures 21829 --expect-valid-half-time 21791 --expect-missing-half-time 38 --expect-cache-files 66
```

Generation refuses to overwrite an existing artifact unless `--force` is
provided. Open a follow-up PR that commits only the generated baseline
artifact. Do not commit the database or cached CSV files. After that
artifact-only commit is merged, verify the same evidence with:

```powershell
python -m scripts.freeze_evidence_baseline --database database/athena.db --cache-directory .cache/football-data-uk --check artifacts/evidence-baselines/half-time-ready-for-research.json
```

A commit cannot contain its own Git SHA because adding that SHA changes the
commit content and therefore produces a different SHA. The artifact therefore
records the clean parent code state `H`, not the later commit that adds the
artifact. Check mode accepts either exact execution at `H` or a proven
artifact-only descendant: `H` must be an ancestor of the current clean HEAD,
and the checked artifact must be the only tracked path changed since `H`.
The actual `--check` path must be a non-symlinked path inside the repository;
an artifact path stored in JSON is never trusted for this decision. Successful
use of this descendant rule is reported explicitly.

Any later code, schema, test, documentation, configuration, or other tracked
change makes that relationship fail. Verify from the original baseline state,
or intentionally produce a new versioned baseline against the new clean
evidence revision.

`--require-ready` checks the existing research-readiness result, invalid and
conflict counts, league metadata completeness, tracked Git cleanliness, and
the explicit disabled status of both Win Either Half markets. A
`READY_FOR_RESEARCH` result never enables either market and is not betting
approval.
