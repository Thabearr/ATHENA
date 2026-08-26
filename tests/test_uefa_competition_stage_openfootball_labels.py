from __future__ import annotations

import pytest

import domain.uefa_competition_stage as stage_contract
from domain.uefa_competition_stage import UEFACompetitionStage


@pytest.mark.parametrize(
    ("label", "expected"),
    (
        ("Round 1", UEFACompetitionStage.QUALIFYING_R1),
        ("Round 2", UEFACompetitionStage.QUALIFYING_R2),
        ("Round 3", UEFACompetitionStage.QUALIFYING_R3),
        ("Playoffs", UEFACompetitionStage.QUALIFYING_PLAYOFF),
    ),
)
def test_openfootball_source_native_champions_league_qualifier_labels(
    label: str,
    expected: UEFACompetitionStage,
) -> None:
    assert (
        stage_contract._path_stage(
            "uefa_ucl",
            label,
            "champions-league-master/2024-25/clq.txt",
            "2024-25",
        )
        is expected
    )


def test_source_native_round_label_still_requires_matching_qualifier_parent() -> None:
    assert (
        stage_contract._path_stage(
            "uefa_uel",
            "Round 3",
            "champions-league-master/2024-25/clq.txt",
            "2024-25",
        )
        is UEFACompetitionStage.UNKNOWN
    )
