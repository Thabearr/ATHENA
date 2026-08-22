from pathlib import Path

from domain.historical_competitions import competition_by_key
from scripts.audit_historical_hierarchy_coverage import (
    RECENT_EXEMPT_KEYS,
    REQUIRED_HIERARCHY_KEYS,
    audit_hierarchy,
)
from scripts.build_historical_warehouse import Warehouse


def _insert_fixture(warehouse: Warehouse, key: str, date: str) -> None:
    comp = competition_by_key(key)
    assert comp is not None
    warehouse.upsert_match(
        {
            "competition_key": key,
            "competition_name": comp.name,
            "scope": comp.scope,
            "season": date[:4],
            "match_date": date,
            "home_team": f"{key} Home",
            "away_team": f"{key} Away",
            "home_score_ft": 1,
            "away_score_ft": 0,
        },
        source_key="openfootball",
        source_match_id=f"freshness-{key}-{date}",
    )


def test_recent_audit_marks_old_only_competition_stale(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    _insert_fixture(warehouse, "eng_premier", "2023-12-31")

    report = audit_hierarchy(warehouse, recent_since="2024-01-01")

    assert "eng_premier" in report["stale_required_competitions"]
    assert report["complete"] is False
    assert report["fresh_complete"] is False
    warehouse.close()


def test_world_cup_is_historically_required_but_freshness_exempt(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    assert "intl_world_cup" in REQUIRED_HIERARCHY_KEYS
    assert "intl_world_cup" in RECENT_EXEMPT_KEYS
    _insert_fixture(warehouse, "intl_world_cup", "2022-12-18")

    report = audit_hierarchy(warehouse, recent_since="2024-01-01")
    world_cup = next(
        row for row in report["competitions"] if row["competition_key"] == "intl_world_cup"
    )

    assert world_cup["matches"] == 1
    assert world_cup["recent_matches"] == 0
    assert world_cup["freshness_required"] is False
    assert "intl_world_cup" not in report["stale_required_competitions"]
    warehouse.close()


def test_recent_audit_is_fresh_complete_when_every_required_competition_is_recent(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    for index, key in enumerate(REQUIRED_HIERARCHY_KEYS):
        date = "2022-12-18" if key in RECENT_EXEMPT_KEYS else f"2025-02-{(index % 28) + 1:02d}"
        _insert_fixture(warehouse, key, date)

    report = audit_hierarchy(warehouse, recent_since="2024-01-01")

    assert report["missing_required_competitions"] == []
    assert report["stale_required_competitions"] == []
    assert report["complete"] is True
    assert report["fresh_complete"] is True
    warehouse.close()
