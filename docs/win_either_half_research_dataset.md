# Win Either Half research labels

ATHENA's Stage 3 dataset is a deterministic post-match label dataset. It is
not a feature matrix, probability model, value calculation, or production
recommendation input.

## Settlement and labels

The first-half score is the observed half-time score. Second-half goals are
derived exactly as full-time goals minus half-time goals, independently for
the home and away teams. Home Win Either Half is YES when the home team wins
the first half or the second half. Away Win Either Half uses the same rule for
the away team. The labels are not complements: both can be YES when each team
wins a different half. Both are NO when neither team wins either half.

## Eligibility and exclusions

The exporter reuses the coverage audit's public one-observation-per-fixture
selector and fails closed. A label requires VALID, OBSERVED, conflict-free
score evidence; non-negative integer FT and HT scores; non-negative derived
second-half scores; and fixture, team, kickoff, league, and season identity.
Every ineligible selected fixture is retained in the deterministic exclusions
CSV with sorted reason codes and a bounded explanation. Missing half-time
scores remain missing and are never inferred.

## Temporal partitions and leakage

The default whole-season partitions are TRAIN for 2020-21 through 2023-24,
VALIDATION for 2024-25, and TEST for 2025-26. CLI overrides must remain
disjoint and must assign every eligible season exactly once. Every split must
contain at least one season, season labels must use `YYYY-YY` with a consecutive
ending year, every TRAIN season must precede every VALIDATION season, and every
VALIDATION season must precede every TEST season. Seasons supplied within a
split are canonicalized into chronological order. Reversed or interleaved
overrides are rejected. Random splitting is forbidden because it can mix later
football conditions into earlier research and weaken temporal evaluation. The
test season remains untouched for final evaluation.

Every FT, HT, derived second-half, half-outcome, and Win Either Half target
column is post-match information. None may be used as a pre-match model
feature. The exporter intentionally adds no bookmaker odds, closing lines,
results-derived form, probabilities, or other features.

## Generate and verify

After this tooling PR is merged, generate the real files from a clean tracked
worktree:

```powershell
python -m scripts.export_win_either_half_research_dataset --database database/athena.db --baseline artifacts/evidence-baselines/half-time-ready-for-research.json --labels-output .cache/athena-research/win-either-half/labels-v1.csv --exclusions-output .cache/athena-research/win-either-half/exclusions-v1.csv --manifest-output artifacts/research-manifests/win-either-half-labels-v1.json --require-baseline-evidence --expect-selected-fixtures 21829 --expect-eligible-labels 21791 --expect-exclusions 38
```

Commit only the small manifest in a follow-up PR. Verify it later with:

```powershell
python -m scripts.export_win_either_half_research_dataset --database database/athena.db --baseline artifacts/evidence-baselines/half-time-ready-for-research.json --check artifacts/research-manifests/win-either-half-labels-v1.json
```

The manifest fingerprints the frozen Stage 2 non-code evidence, deterministic
CSV bytes, label and exclusion counts, temporal splits, generator revision,
and market safety. It proves reproducibility against those local inputs; it
does not prove provider correctness, complete historical coverage, predictive
performance, calibration, betting value, or model approval. The tracked
artifact lifecycle permits only an exact generator revision or a clean
manifest-only descendant. Any other tracked change requires a new manifest.

`READY_FOR_RESEARCH` is evidence readiness only. Both Home and Away Win Either
Half markets remain `DISABLED` and this dataset does not enable them.
