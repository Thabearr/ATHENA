from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from domain.uefa_competition_stage import (
    UEFACompetitionStage,
    project_warehouse_uefa_stages,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "database" / "historical_warehouse_schema.sql"
OPENFOOTBALL_URL = (
    "https://github.com/openfootball/champions-league/"
    "archive/refs/heads/master.zip"
)


def _warehouse(path: Path, *, label: str, competition: str = "uefa_ucl") -> Path:
    db = sqlite3.connect(path)
    db.executescript(SCHEMA.read_text(encoding="utf-8"))
    db.execute(
        "INSERT OR REPLACE INTO warehouse_meta(key,value) VALUES('schema_version','1')"
    )
    db.execute(
        """INSERT INTO warehouse_sources(
          source_key,display_name,redistributable,source_priority,notes
        ) VALUES(?,?,?,?,?)""",
        ("openfootball", "OpenFootball", 0, 10, "source-native label regression"),
    )
    for key, name in (
        ("uefa_ucl", "UEFA Champions League"),
        ("uefa_uel", "UEFA Europa League"),
        ("uefa_uecl", "UEFA Conference League"),
    ):
        db.execute(
            """INSERT INTO warehouse_competitions(
              competition_key,display_name,scope,confederation,competition_type,
              hierarchy_rank,hierarchy_tier,active,aliases_json
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (key, name, "club", "UEFA", "continental_club_cup", 10, "TIER_1", 1, "[]"),
        )
    qualifier_file = {
        "uefa_ucl": "clq.txt",
        "uefa_uel": "elq.txt",
        "uefa_uecl": "confq.txt",
    }[competition]
    competition_name = {
        "uefa_ucl": "UEFA Champions League",
        "uefa_uel": "UEFA Europa League",
        "uefa_uecl": "UEFA Conference League",
    }[competition]
    db.execute(
        """INSERT INTO warehouse_matches(
          match_key,competition_key,competition_name,scope,season,stage,match_date,
          home_team,away_team,home_score_ft,away_score_ft,result,extra_json,data_quality
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "m1",
            competition,
            competition_name,
            "club",
            "2024-25",
            label,
            "2024-08-06",
            "Home",
            "Away",
            1,
            0,
            "H",
            json.dumps({
                "openfootball_path": (
                    f"champions-league-master/2024-25/{qualifier_file}"
                )
            }),
            "BASIC",
        ),
    )
    for field in ("stage", "extra_json", "home_score_ft", "away_score_ft"):
        db.execute(
            """INSERT INTO warehouse_field_provenance(
              match_key,field_name,source_key,source_priority
            ) VALUES(?,?,?,?)""",
            ("m1", field, "openfootball", 10),
        )
    db.execute(
        """INSERT INTO warehouse_match_sources(
          match_key,source_key,source_match_id,source_url,has_ft
        ) VALUES(?,?,?,?,?)""",
        ("m1", "openfootball", "source-m1", OPENFOOTBALL_URL, 1),
    )
    db.commit()
    db.close()
    return path


@pytest.mark.parametrize(
    ("label", "expected"),
    (
        ("Round 1", UEFACompetitionStage.QUALIFYING_R1),
        ("Round 2", UEFACompetitionStage.QUALIFYING_R2),
        ("Round 3", UEFACompetitionStage.QUALIFYING_R3),
        ("Playoffs", UEFACompetitionStage.QUALIFYING_PLAYOFF),
    ),
)
def test_openfootball_source_native_champions_league_labels_replay_end_to_end(
    tmp_path: Path,
    label: str,
    expected: UEFACompetitionStage,
) -> None:
    row = project_warehouse_uefa_stages(
        _warehouse(tmp_path / f"{expected.value}.db", label=label)
    )[0]
    assert row.stage_authorized is True
    assert row.competition_stage is expected


def test_source_native_label_cannot_borrow_another_parent_qualifier_file(
    tmp_path: Path,
) -> None:
    # Build a valid UEL row, then change only the source-owned path to clq.txt.
    warehouse = _warehouse(
        tmp_path / "cross-parent.db",
        label="Round 3",
        competition="uefa_uel",
    )
    db = sqlite3.connect(warehouse)
    db.execute(
        "UPDATE warehouse_matches SET extra_json=? WHERE match_key='m1'",
        (json.dumps({
            "openfootball_path": "champions-league-master/2024-25/clq.txt"
        }),),
    )
    db.commit()
    db.close()

    row = project_warehouse_uefa_stages(warehouse)[0]
    assert row.stage_authorized is False
    assert row.competition_stage is UEFACompetitionStage.UNKNOWN
    assert row.blocker == "UNMAPPED_OR_AMBIGUOUS_STAGE"
