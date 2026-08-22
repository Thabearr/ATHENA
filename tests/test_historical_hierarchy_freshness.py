from pathlib import Path

from domain.historical_competitions import competition_by_key
from scripts.audit_historical_hierarchy_coverage import (
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


def test_recent_audit_is_fresh_complete_when_every_required_competition_is_recent(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    for index, key in enumerate(REQUIRED_HIERARCHY_KEYS):
        _insert_fixture(warehouse, key, f"2025-02-{(index % 28) + 1:02d}")

    report = audit_hierarchy(warehouse, recent_since="2024-01-01")

    assert report["missing_required_competitions"] == []
    assert report["stale_required_competitions"] == []
    assert report["complete"] is True
    assert report["fresh_complete"] is True
    warehouse.close()
