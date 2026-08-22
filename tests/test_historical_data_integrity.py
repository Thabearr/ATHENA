from pathlib import Path

from scripts.audit_historical_data_integrity import audit_integrity
from scripts.build_historical_warehouse import Warehouse


def _match(home: str, away: str) -> dict[str, object]:
    return {
        "competition_key": "eng_premier",
        "competition_name": "Premier League",
        "scope": "club",
        "season": "2025-26",
        "match_date": "2025-08-30",
        "home_team": home,
        "away_team": away,
        "home_score_ft": 2,
        "away_score_ft": 1,
    }


def test_integrity_audit_detects_cross_source_logical_fixture_duplicates(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    warehouse.upsert_match(
        _match("AFC Bournemouth", "Fulham FC"),
        source_key="soccer_datalake",
        source_match_id="provider-a",
    )
    warehouse.upsert_match(
        _match("Bournemouth AFC", "FC Fulham"),
        source_key="openfootball",
        source_match_id="provider-b",
    )

    report = audit_integrity(warehouse)

    assert report["logical_duplicate_fixtures"]["duplicate_groups"] == 1
    assert report["complete"] is False
    warehouse.close()


def test_integrity_audit_accepts_canonical_goal_and_card_incidents(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    key = warehouse.upsert_match(
        _match("Arsenal", "Chelsea"),
        source_key="statsbomb_open",
        source_match_id="match-1",
    )
    warehouse.event(
        key,
        "statsbomb_open",
        "goal-1",
        "goal",
        team="Arsenal",
        player="Scorer",
        outcome="Goal",
    )
    warehouse.event(
        key,
        "statsbomb_open",
        "card-1",
        "card",
        team="Chelsea",
        player="Booked Player",
        card_type="Yellow Card",
    )

    report = audit_integrity(warehouse)

    assert report["noncanonical_card_events"] == 0
    assert report["noncanonical_goal_outcome_events"] == 0
    assert report["complete"] is True
    warehouse.close()
