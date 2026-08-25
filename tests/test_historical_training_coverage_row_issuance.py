from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import domain.historical_training_coverage as htc
from scripts.build_historical_warehouse import Warehouse


def _row(tmp_path: Path):
    path = tmp_path / "history.db"
    warehouse = Warehouse(path)
    warehouse.initialize()
    key = warehouse.upsert_match(
        {
            "competition_key": "eng_premier",
            "competition_name": "Premier League",
            "scope": "club",
            "season": "2025-26",
            "match_date": "2025-01-02",
            "home_team": "Home",
            "away_team": "Away",
            "home_score_ft": 1,
            "away_score_ft": 0,
        },
        source_key="football_data_uk",
        source_match_id="m1",
    )
    warehouse.close()
    return htc.build_historical_training_coverage_row(path, key)


def test_mutation_and_fresh_sha_cannot_preserve_canonical_issuance(tmp_path: Path):
    row = _row(tmp_path)
    original_sha = row.canonical_sha256
    labels = dict(row.labels)
    original = labels["MATCH_RESULT"]
    labels["MATCH_RESULT"] = htc.Resolution(
        htc.ResolutionStatus.AVAILABLE,
        value="AWAY",
        evidence_identities=original.evidence_identities,
    )
    object.__setattr__(row, "labels", tuple(sorted(labels.items())))

    with pytest.raises(
        htc.HistoricalTrainingCoverageError,
        match="changed after source issuance",
    ):
        _ = row.canonical_bytes
    with pytest.raises(
        htc.HistoricalTrainingCoverageError,
        match="changed after source issuance",
    ):
        _ = row.canonical_sha256
    assert original_sha != ""


def test_unissued_clone_cannot_claim_canonical_ancestry(tmp_path: Path):
    row = _row(tmp_path)
    clone = object.__new__(type(row))
    for field in dataclasses.fields(type(row)):
        object.__setattr__(clone, field.name, getattr(row, field.name))

    with pytest.raises(
        htc.HistoricalTrainingCoverageError,
        match="no live source issuance state",
    ):
        _ = clone.canonical_sha256


def test_legitimate_direct_row_keeps_stable_issuance_bytes(tmp_path: Path):
    row = _row(tmp_path)
    first_bytes = row.canonical_bytes
    first_sha = row.canonical_sha256
    assert row.canonical_bytes == first_bytes
    assert row.canonical_sha256 == first_sha
