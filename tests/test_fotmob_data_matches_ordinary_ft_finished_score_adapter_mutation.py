from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from domain.fotmob_data_matches_capture import manifest_from_mapping, strict_manifest_json_loads
from domain.fotmob_data_matches_ordinary_ft_finished_score_adapter import (
    FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError,
    adapt_fotmob_data_matches_ordinary_ft_finished_scores,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = (
    ROOT
    / "evidence"
    / "fotmob_data_matches"
    / "pr83_post_finish_pair"
    / "20260814"
)
FIRST_DIR = EVIDENCE_ROOT / "a18e843fabe5aca74846b160"
SECOND_DIR = EVIDENCE_ROOT / "e28d9ce746c1ef9102995517"


def _load_capture(directory: Path) -> tuple[bytes, Any]:
    raw = (directory / "response.json").read_bytes()
    manifest = manifest_from_mapping(
        strict_manifest_json_loads((directory / "manifest.json").read_bytes())
    )
    return raw, manifest


def _result():
    first_raw, first_manifest = _load_capture(FIRST_DIR)
    second_raw, second_manifest = _load_capture(SECOND_DIR)
    return adapt_fotmob_data_matches_ordinary_ft_finished_scores(
        first_raw,
        first_manifest,
        second_raw,
        second_manifest,
    )


@pytest.mark.parametrize(
    ("field", "bad"),
    (
        ("request_date", "2026-08-14"),
        ("timezone", ""),
        ("ccode3", "NG"),
        ("first_raw_sha256", "g" * 64),
        ("first_manifest_sha256", "0" * 63),
        ("first_pr89_assessment_sha256", "UPPER" * 12 + "ABCD"),
        ("observation_separation_microseconds", 310_605_740),
        ("source_capability_registration_performed", True),
        ("next_required_boundary", "SKIP_VALIDATION"),
    ),
)
def test_public_result_scalar_mutations_fail_closed(field: str, bad: Any) -> None:
    value = _result()
    with pytest.raises(FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError):
        dataclasses.replace(value, **{field: bad})


def test_public_result_rejects_duplicate_pair_lineage() -> None:
    value = _result()
    with pytest.raises(FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError):
        dataclasses.replace(value, second_raw_sha256=value.first_raw_sha256)
    with pytest.raises(FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError):
        dataclasses.replace(value, second_manifest_sha256=value.first_manifest_sha256)


def test_public_result_rejects_observation_time_mutation_even_if_timezone_aware() -> None:
    value = _result()
    with pytest.raises(FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError):
        dataclasses.replace(value, first_observed_at=value.first_observed_at + __import__("datetime").timedelta(seconds=1))


def test_qualified_score_lineage_must_match_result_pair_lineage() -> None:
    value = _result()
    first = value.qualified_scores[0]
    mutated = dataclasses.replace(first, first_raw_sha256="0" * 64)
    with pytest.raises(FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError):
        dataclasses.replace(value, qualified_scores=(mutated, *value.qualified_scores[1:]))


def test_safety_true_mutation_fails_closed() -> None:
    value = _result()
    safety = dict(value.safety)
    safety["bet_authorized"] = True
    with pytest.raises(FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError):
        dataclasses.replace(value, safety=safety)
