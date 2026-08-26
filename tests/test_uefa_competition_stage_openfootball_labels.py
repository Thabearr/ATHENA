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


def _warehouse(
    path: Path,
    *,
    label: str,
    competition: str = "uefa_ucl",
    season: str = "2024-25",
    source_file: str | None = None,
    match_date: str = "2024-08-06",
) -> Path:
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
    if source_file is None:
        source_file = {
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
            season,
            label,
            match_date,
            "Home",
            "Away",
            1,
            0,
            "H",
            json.dumps({
                "openfootball_path": (
                    f"champions-league-master/{season}/{source_file}"
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


def _project(path: Path, **kwargs: object):
    return project_warehouse_uefa_stages(_warehouse(path, **kwargs))[0]


@pytest.mark.parametrize(
    ("label", "expected"),
    (
        ("Round 1", UEFACompetitionStage.QUALIFYING_R1),
        ("Round 2", UEFACompetitionStage.QUALIFYING_R2),
        ("Round 3", UEFACompetitionStage.QUALIFYING_R3),
        ("Playoffs", UEFACompetitionStage.QUALIFYING_PLAYOFF),
    ),
)
def test_openfootball_source_native_qualifier_labels_replay_end_to_end(
    tmp_path: Path,
    label: str,
    expected: UEFACompetitionStage,
) -> None:
    row = _project(tmp_path / f"qual-{expected.value}.db", label=label)
    assert row.stage_authorized is True
    assert row.competition_stage is expected


@pytest.mark.parametrize(
    ("competition", "source_file", "label", "expected", "match_date"),
    (
        ("uefa_ucl", "cl.txt", "League, Matchday 1", UEFACompetitionStage.LEAGUE_PHASE, "2024-09-17"),
        ("uefa_ucl", "cl.txt", "Playoffs, Matchday 1", UEFACompetitionStage.KNOCKOUT_PLAYOFF, "2025-02-11"),
        ("uefa_ucl", "cl.txt", "Finals, Round of 16", UEFACompetitionStage.ROUND_OF_16, "2025-03-04"),
        ("uefa_ucl", "cl.txt", "Finals, Quarterfinals", UEFACompetitionStage.QUARTER_FINAL, "2025-04-08"),
        ("uefa_ucl", "cl.txt", "Finals, Semifinals", UEFACompetitionStage.SEMI_FINAL, "2025-04-29"),
        ("uefa_ucl", "cl.txt", "Finals, Final", UEFACompetitionStage.FINAL, "2025-05-31"),
        ("uefa_uel", "el.txt", "League phase", UEFACompetitionStage.LEAGUE_PHASE, "2024-09-25"),
        ("uefa_uel", "el.txt", "Playoffs", UEFACompetitionStage.KNOCKOUT_PLAYOFF, "2025-02-13"),
        ("uefa_uel", "el.txt", "Quarterfinals", UEFACompetitionStage.QUARTER_FINAL, "2025-04-10"),
        ("uefa_uel", "el.txt", "Semifinals", UEFACompetitionStage.SEMI_FINAL, "2025-05-01"),
        ("uefa_uecl", "conf.txt", "League phase", UEFACompetitionStage.LEAGUE_PHASE, "2024-10-02"),
        ("uefa_uecl", "conf.txt", "Playoffs", UEFACompetitionStage.KNOCKOUT_PLAYOFF, "2025-02-13"),
        ("uefa_uecl", "conf.txt", "Quarterfinals", UEFACompetitionStage.QUARTER_FINAL, "2025-04-10"),
        ("uefa_uecl", "conf.txt", "Semifinals", UEFACompetitionStage.SEMI_FINAL, "2025-05-01"),
    ),
)
def test_openfootball_source_native_2024_main_labels_replay_end_to_end(
    tmp_path: Path,
    competition: str,
    source_file: str,
    label: str,
    expected: UEFACompetitionStage,
    match_date: str,
) -> None:
    row = _project(
        tmp_path / f"main-{competition}-{expected.value}-{match_date}.db",
        label=label,
        competition=competition,
        source_file=source_file,
        match_date=match_date,
    )
    assert row.stage_authorized is True
    assert row.competition_stage is expected


@pytest.mark.parametrize(
    ("competition", "source_file"),
    (
        ("uefa_uel", "el.txt"),
        ("uefa_uecl", "conf.txt"),
    ),
)
def test_openfootball_2021_main_playoffs_are_source_native_knockout_playoffs(
    tmp_path: Path,
    competition: str,
    source_file: str,
) -> None:
    row = _project(
        tmp_path / f"2021-playoffs-{competition}.db",
        label="Playoffs",
        competition=competition,
        season="2021-22",
        source_file=source_file,
        match_date="2022-02-17",
    )
    assert row.stage_authorized is True
    assert row.competition_stage is UEFACompetitionStage.KNOCKOUT_PLAYOFF


def test_openfootball_historical_gruppe_heading_is_group_phase(tmp_path: Path) -> None:
    row = _project(
        tmp_path / "gruppe.db",
        label="Gruppe G",
        competition="uefa_uel",
        season="2021-22",
        source_file="el.txt",
        match_date="2021-09-16",
    )
    assert row.stage_authorized is True
    assert row.competition_stage is UEFACompetitionStage.GROUP_PHASE


def test_ucl_main_playoffs_do_not_project_before_2024_era(tmp_path: Path) -> None:
    row = _project(
        tmp_path / "ucl-early-playoffs.db",
        label="Playoffs",
        competition="uefa_ucl",
        season="2021-22",
        source_file="cl.txt",
        match_date="2022-02-17",
    )
    assert row.stage_authorized is False
    assert row.competition_stage is UEFACompetitionStage.UNKNOWN
    assert row.blocker == "UNMAPPED_OR_AMBIGUOUS_STAGE"


def test_source_native_label_cannot_borrow_another_parent_qualifier_file(
    tmp_path: Path,
) -> None:
    warehouse = _warehouse(
        tmp_path / "cross-parent.db",
        label="Round 3",
        competition="uefa_uel",
        source_file="elq.txt",
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


def test_explicit_main_stage_cannot_borrow_qualifier_file(tmp_path: Path) -> None:
    row = _project(
        tmp_path / "main-from-qualifier.db",
        label="Quarterfinals",
        competition="uefa_ucl",
        source_file="clq.txt",
        match_date="2025-04-08",
    )
    assert row.stage_authorized is False
    assert row.competition_stage is UEFACompetitionStage.UNKNOWN
    assert row.blocker == "SOURCE_PATH_PARENT_OR_PHASE_CONFLICT"
