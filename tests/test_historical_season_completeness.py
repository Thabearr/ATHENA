from pathlib import Path

from scripts.audit_historical_season_completeness import audit_season_completeness
from scripts.build_historical_warehouse import Warehouse


def _insert(warehouse: Warehouse, season: str, date: str, index: int) -> None:
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
        source_key="openfootball",
        source_match_id=f"season-test-{season}-{index}",
    )


def test_detects_missing_internal_season(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    for year in (2020, 2022):
        for i in range(10):
            _insert(warehouse, f"{year}-{str(year + 1)[-2:]}", f"{year}-09-{i + 1:02d}", i)

    report = audit_season_completeness(warehouse)
    premier = next(c for c in report["competitions"] if c["competition_key"] == "eng_premier")
    assert premier["missing_season_start_years"] == [2021]
    assert report["complete"] is False
    warehouse.close()


def test_detects_underfilled_mature_season_but_ignores_newest(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    for year, count in ((2020, 10), (2021, 2), (2022, 10), (2023, 2)):
        for i in range(count):
            _insert(warehouse, f"{year}-{str(year + 1)[-2:]}", f"{year}-09-{i + 1:02d}", i)

    report = audit_season_completeness(warehouse, underfill_ratio=0.60, min_reference_matches=2)
    premier = next(c for c in report["competitions"] if c["competition_key"] == "eng_premier")
    flagged = {row["season_start_year"] for row in premier["underfilled_seasons"]}
    assert 2021 in flagged
    assert 2023 not in flagged
    warehouse.close()
