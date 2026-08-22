from pathlib import Path

from scripts.build_historical_warehouse import Warehouse
from scripts.historical_quality import refresh_quality_set_based


def _match(name: str, *, ft=True, ht=False, referee=None, home_coach=None, away_coach=None):
    row = {
        "competition_key": "eng_premier",
        "competition_name": "Premier League",
        "scope": "club",
        "season": "2025-26",
        "match_date": f"2025-09-0{name}",
        "home_team": f"Home {name}",
        "away_team": f"Away {name}",
        "referee": referee,
        "home_coach": home_coach,
        "away_coach": away_coach,
    }
    if ft:
        row.update(home_score_ft=1, away_score_ft=0)
    if ht:
        row.update(home_score_ht=1, away_score_ht=0)
    return row


def test_set_based_quality_refresh_matches_existing_quality_rules(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()

    partial = warehouse.upsert_match(
        _match("1", ft=False),
        source_key="openfootball",
        source_match_id="partial",
    )
    basic = warehouse.upsert_match(
        _match("2"),
        source_key="openfootball",
        source_match_id="basic",
    )
    standard_ht = warehouse.upsert_match(
        _match("3", ht=True),
        source_key="openfootball",
        source_match_id="standard-ht",
    )
    standard_event = warehouse.upsert_match(
        _match("4"),
        source_key="openfootball",
        source_match_id="standard-event",
    )
    rich = warehouse.upsert_match(
        _match(
            "5",
            ht=True,
            referee="Referee",
            home_coach="Home Coach",
            away_coach="Away Coach",
        ),
        source_key="openfootball",
        source_match_id="rich",
    )
    warehouse.event(standard_event, "openfootball", "e-standard", "goal", team="Home 4")
    warehouse.event(rich, "openfootball", "e-rich", "goal", team="Home 5")

    refresh_quality_set_based(warehouse)

    rows = dict(
        warehouse.conn.execute(
            "SELECT match_key,data_quality FROM warehouse_matches"
        ).fetchall()
    )
    assert rows[partial] == "PARTIAL"
    assert rows[basic] == "BASIC"
    assert rows[standard_ht] == "STANDARD"
    assert rows[standard_event] == "STANDARD"
    assert rows[rich] == "RICH"
    warehouse.close()
