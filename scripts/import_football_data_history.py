#!/usr/bin/env python3
"""Import Football-Data.co.uk history using Athena's deterministic team aliases.

The Global Football Data Lake publishes an explicit ``fd_name`` cross-reference
for teams. When that alias exists for a competition, this importer writes the
canonical data-lake team name so overlapping provider records converge on one
Athena match key. Unknown historical teams retain their source name; no fuzzy
matching is performed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.historical_competitions import FOOTBALL_DATA_CODES, competition_by_key  # noqa: E402
from scripts.build_historical_warehouse import (  # noqa: E402
    DEFAULT_CACHE,
    DEFAULT_DB,
    Downloader,
    Warehouse,
    clean,
    csv_rows,
    digest,
    integer,
    norm_team,
    outcome,
)

SOURCE_KEY = "football_data_uk"
FD_DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d")


def fd_date(value: str) -> str | None:
    for fmt in FD_DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def resolve_team_alias(
    warehouse: Warehouse,
    competition_key: str,
    provider_name: str,
) -> str:
    alias_norm = norm_team(provider_name)
    if not alias_norm:
        return provider_name
    row = warehouse.conn.execute(
        """SELECT canonical_team
           FROM warehouse_team_aliases
           WHERE competition_key=? AND source_key=? AND alias_norm=?""",
        (competition_key, SOURCE_KEY, alias_norm),
    ).fetchone()
    return str(row["canonical_team"]) if row else provider_name


def import_football_data(
    warehouse: Warehouse,
    downloader: Downloader,
    start: int,
    end: int,
    codes: Iterable[str],
) -> dict[str, object]:
    rows_seen = matches = alias_hits = alias_misses = 0
    per_competition: dict[str, int] = {}

    for year in range(start, end + 1):
        season = f"{year}-{str((year + 1) % 100).zfill(2)}"
        archive = f"{year % 100:02d}{(year + 1) % 100:02d}"
        for code in codes:
            comp_key = FOOTBALL_DATA_CODES.get(code)
            if not comp_key:
                continue
            comp = competition_by_key(comp_key)
            if not comp:
                continue
            url = f"https://www.football-data.co.uk/mmz4281/{archive}/{code}.csv"
            try:
                rows = csv_rows(
                    downloader.text(url, f"football-data/{archive}_{code}.csv")
                )
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code in {404, 410}:
                    continue
                raise

            for source_row in rows:
                rows_seen += 1
                date = fd_date(source_row.get("Date") or "")
                source_home = clean(source_row.get("HomeTeam"))
                source_away = clean(source_row.get("AwayTeam"))
                if not date or not source_home or not source_away:
                    continue

                home = resolve_team_alias(warehouse, comp.key, source_home)
                away = resolve_team_alias(warehouse, comp.key, source_away)
                alias_hits += int(home != source_home) + int(away != source_away)
                alias_misses += int(home == source_home) + int(away == source_away)

                row = {
                    "competition_key": comp.key,
                    "competition_name": comp.name,
                    "scope": "club",
                    "season": season,
                    "match_date": date,
                    "kickoff_time": clean(source_row.get("Time")),
                    "home_team": home,
                    "away_team": away,
                    "home_score_ft": integer(source_row.get("FTHG")),
                    "away_score_ft": integer(source_row.get("FTAG")),
                    "home_score_ht": integer(source_row.get("HTHG")),
                    "away_score_ht": integer(source_row.get("HTAG")),
                    "referee": clean(source_row.get("Referee")),
                    "home_shots": integer(source_row.get("HS")),
                    "away_shots": integer(source_row.get("AS")),
                    "home_shots_on_target": integer(source_row.get("HST")),
                    "away_shots_on_target": integer(source_row.get("AST")),
                    "home_fouls": integer(source_row.get("HF")),
                    "away_fouls": integer(source_row.get("AF")),
                    "home_corners": integer(source_row.get("HC")),
                    "away_corners": integer(source_row.get("AC")),
                    "home_yellows": integer(source_row.get("HY")),
                    "away_yellows": integer(source_row.get("AY")),
                    "home_reds": integer(source_row.get("HR")),
                    "away_reds": integer(source_row.get("AR")),
                }
                row["result"] = outcome(row["home_score_ft"], row["away_score_ft"])
                known = {
                    "Div",
                    "Date",
                    "Time",
                    "HomeTeam",
                    "AwayTeam",
                    "FTHG",
                    "FTAG",
                    "FTR",
                    "HTHG",
                    "HTAG",
                    "HTR",
                    "Referee",
                    "HS",
                    "AS",
                    "HST",
                    "AST",
                    "HF",
                    "AF",
                    "HC",
                    "AC",
                    "HY",
                    "AY",
                    "HR",
                    "AR",
                }
                row["extra_json"] = json.dumps(
                    {
                        "football_data_source_home": source_home,
                        "football_data_source_away": source_away,
                        "team_alias_home_applied": home != source_home,
                        "team_alias_away_applied": away != source_away,
                        "provider_fields": {
                            key: value
                            for key, value in source_row.items()
                            if key not in known and value not in (None, "")
                        },
                    },
                    ensure_ascii=False,
                )
                warehouse.upsert_match(
                    row,
                    source=SOURCE_KEY,
                    # Source identity always uses the provider spelling, not the
                    # canonical alias, so refreshes remain stable if aliases grow.
                    source_id=digest(code, date, source_home, source_away),
                    source_url=url,
                    coverage={
                        "has_ft": int(row["home_score_ft"] is not None),
                        "has_ht": int(row["home_score_ht"] is not None),
                        "has_cards": int(row["home_yellows"] is not None),
                        "has_officials": int(bool(row["referee"])),
                        "has_advanced_stats": int(row["home_shots"] is not None),
                    },
                )
                matches += 1
                per_competition[comp.key] = per_competition.get(comp.key, 0) + 1

    warehouse.flush()
    warehouse.refresh_quality()
    return {
        "rows_seen": rows_seen,
        "matches_processed": matches,
        "team_alias_hits": alias_hits,
        "team_alias_misses_or_canonical_names": alias_misses,
        "per_competition": dict(sorted(per_competition.items())),
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--start-year", type=int, default=1993)
    parser.add_argument("--end-year", type=int, default=datetime.now().year)
    parser.add_argument("--leagues", nargs="*", default=list(FOOTBALL_DATA_CODES))
    parser.add_argument("--export-csv", type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    warehouse = Warehouse(args.db)
    warehouse.initialize()
    downloader = Downloader(args.cache, args.refresh)
    try:
        report = import_football_data(
            warehouse,
            downloader,
            args.start_year,
            args.end_year,
            args.leagues,
        )
        if args.export_csv:
            warehouse.export(args.export_csv)
        print(
            json.dumps(
                {
                    "database": str(args.db),
                    "football_data": report,
                    "audit": warehouse.audit(),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    finally:
        warehouse.close()


if __name__ == "__main__":
    raise SystemExit(main())
