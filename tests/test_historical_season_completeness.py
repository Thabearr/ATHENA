from pathlib import Path

from scripts.audit_historical_season_completeness import audit_season_completeness
from scripts.build_historical_warehouse import Warehouse


def _insert(
    warehouse: Warehouse,
    season: str,
    date: str,
    index: int,
    *,
    source_key: str = "openfootball",
) -> None:
    warehouse.upsert_match(
        {
            "competition_key": "eng_premier",
            "competition_name": "Premier League",
            "scope": "club",
            "season": season,
            "match_date": date,
            "home_team": f"Home {season} {index}",
            "away_team": f"Away {season} {index}",
            "home_score_ft": 1,
            "away_score_ft": 0,
        },
        source_key=source_key,
        source_match_id=f"season-test-{source_key}-{season}-{index}",
    )


def _insert_season(warehouse: Warehouse, year: int, count: int, *, sources=("openfootball",)) -> None:
    season = f"{year}-{str(year + 1)[-2:]}"
    for source_key in sources:
        for index in range(count):
            _insert(
                warehouse,
                season,
                f"{year}-09-{index + 1:02d}",
                index,
                source_key=source_key,
            )


def _premier(report):
    return next(c for c in report["competitions"] if c["competition_key"] == "eng_premier")


def test_single_source_gap_is_reported_without_claiming_strict_confirmation(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    _insert_season(warehouse, 2020, 10)
    _insert_season(warehouse, 2022, 10)

    report = audit_season_completeness(warehouse)
    premier = _premier(report)
    assert premier["missing_season_start_years"] == [2021]
    assert premier["confirmed_missing_season_start_years"] == []
    assert report["complete"] is True
    warehouse.close()


def test_two_sources_confirm_missing_internal_season(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    sources = ("openfootball", "football_data_uk")
    _insert_season(warehouse, 2020, 10, sources=sources)
    _insert_season(warehouse, 2022, 10, sources=sources)

    report = audit_season_completeness(warehouse)
    premier = _premier(report)
    assert premier["missing_season_start_years"] == [2021]
    assert premier["confirmed_missing_season_start_years"] == [2021]
    assert report["complete"] is False
    warehouse.close()


def test_large_disconnected_history_is_reported_without_inventing_every_missing_year(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    sources = ("openfootball", "football_data_uk")
    _insert_season(warehouse, 1970, 10, sources=sources)
    _insert_season(warehouse, 2000, 10, sources=sources)

    report = audit_season_completeness(warehouse)
    premier = _premier(report)
    assert premier["missing_season_start_years"] == []
    assert len(premier["disconnected_historical_runs"]) == 1
    assert premier["disconnected_historical_runs"][0]["missing_years"][0] == 1971
    assert premier["disconnected_historical_runs"][0]["missing_years"][-1] == 1999
    assert report["complete"] is True
    warehouse.close()


def test_detects_corroborated_local_underfill_but_ignores_newest(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    sources = ("openfootball", "football_data_uk")
    for year, count in ((2020, 10), (2021, 2), (2022, 10), (2023, 2)):
        _insert_season(warehouse, year, count, sources=sources)

    report = audit_season_completeness(
        warehouse,
        underfill_ratio=0.60,
        min_reference_matches=2,
    )
    premier = _premier(report)
    flagged = {row["season_start_year"]: row for row in premier["underfilled_seasons"]}
    assert flagged[2021]["confirmed"] is True
    assert 2023 not in flagged
    assert report["complete"] is False
    warehouse.close()


def test_single_source_underfill_remains_visible_but_nonfatal(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    for year, count in ((2020, 10), (2021, 2), (2022, 10)):
        _insert_season(warehouse, year, count)

    report = audit_season_completeness(
        warehouse,
        underfill_ratio=0.60,
        min_reference_matches=2,
    )
    premier = _premier(report)
    assert premier["underfilled_seasons"][0]["season_start_year"] == 2021
    assert premier["underfilled_seasons"][0]["confirmed"] is False
    assert report["complete"] is True
    warehouse.close()
