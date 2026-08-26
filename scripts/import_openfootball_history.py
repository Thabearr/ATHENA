#!/usr/bin/env python3
"""Import OpenFootball league/cup/UEFA/international results into Athena history.

The parser keeps European split-year seasons and calendar-year competitions
separate so dates are not shifted into the wrong season.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.historical_competitions import ALL_COMPETITIONS, competition_by_key  # noqa: E402
from scripts.build_historical_warehouse import (  # noqa: E402
    DEFAULT_CACHE,
    DEFAULT_DB,
    Downloader,
    Warehouse,
    digest,
    integer,
    outcome,
)

REPOSITORIES = (
    "champions-league",
    "england",
    "espana",
    "italy",
    "deutschland",
    "france",
    "europe",
    "world",
    "euro",
    "worldcup",
)
CALENDAR_YEAR_KEYS = {"usa_mls", "nor_eliteserien", "swe_allsvenskan"}
MATCH_RE = re.compile(
    r"^(?:(\d{1,2}:\d{2})\s+)?(.+?)\s+v\s+(.+?)\s+(\d+)-(\d+)"
    r"(?:\s+\((\d+)-(\d+)\))?\s*$"
)
DATE_RE = re.compile(
    r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})(?:\s+(\d{4}))?$"
)
SPLIT_SEASON_RE = re.compile(r"(\d{4})[/\-](\d{2,4})")
SINGLE_YEAR_RE = re.compile(r"\b(18\d{2}|19\d{2}|20\d{2})\b")
COUNTRY_SUFFIX_RE = re.compile(r"\s+\([A-Z]{3}\)$")


def _is_reviewed_uefa_ucl_title(lowered_title: str) -> bool:
    """Return whether a source title proves the reviewed UEFA UCL identity.

    OpenFootball's broad ``world`` repository also contains CAF, AFC,
    CONCACAF and other competitions whose titles include the generic words
    ``Champions League``. ATHENA has no reviewed canonical keys for those
    continental club cups, so generic substring matching must not mint the
    ``uefa_ucl`` parent identity.
    """

    title = " ".join(lowered_title.split())
    if "champions league" in title:
        return "uefa champions league" in title
    if "european cup" in title:
        if "winners" in title or "women" in title:
            return False
        return title.startswith("european cup") or "uefa european cup" in title
    return False


def competition_from_title(title: str):
    lowered = title.casefold()

    if "champions league" in lowered or "european cup" in lowered:
        if _is_reviewed_uefa_ucl_title(lowered):
            return competition_by_key("uefa_ucl")
        return None
    if "europa league" in lowered or "uefa cup" in lowered:
        return competition_by_key("uefa_uel")
    if "conference league" in lowered:
        return competition_by_key("uefa_uecl")

    if "world cup qualification" in lowered or "world cup qualifier" in lowered:
        return competition_by_key("intl_world_cup_qual")
    if (
        "euro qualification" in lowered
        or "european championship qualification" in lowered
        or "africa cup of nations qualification" in lowered
        or "asian cup qualification" in lowered
    ):
        return competition_by_key("intl_continental_qual")
    if "world cup" in lowered:
        return competition_by_key("intl_world_cup")
    if "european championship" in lowered or re.search(r"\buefa euro\b", lowered):
        return competition_by_key("intl_euro")
    if "copa america" in lowered or "copa américa" in lowered:
        return competition_by_key("intl_copa_america")
    if "africa cup of nations" in lowered or "african cup of nations" in lowered:
        return competition_by_key("intl_afcon")
    if "asian cup" in lowered:
        return competition_by_key("intl_asian_cup")
    if "gold cup" in lowered:
        return competition_by_key("intl_gold_cup")
    if "nations league" in lowered:
        return competition_by_key("intl_nations_league")
    if "friendly" in lowered:
        return competition_by_key("intl_friendly")

    for comp in ALL_COMPETITIONS:
        for name in (comp.name, *comp.aliases):
            if len(name) > 4 and name.casefold() in lowered:
                return comp
    return None


def season_parts(title: str, competition_key: str | None = None) -> tuple[str | None, int | None]:
    found = SPLIT_SEASON_RE.search(title)
    if found:
        start = int(found.group(1))
        return f"{start}-{found.group(2)[-2:]}", start

    single = SINGLE_YEAR_RE.search(title)
    if single:
        year = int(single.group(1))
        return str(year), year

    return None, None


def resolve_date(
    month_name: str,
    day: str,
    explicit_year: str | None,
    start_year: int | None,
    *,
    calendar_year: bool = False,
) -> str | None:
    month = datetime.strptime(month_name, "%b").month
    if explicit_year:
        year = int(explicit_year)
    elif start_year is not None:
        if calendar_year:
            year = start_year
        else:
            year = start_year if month >= 7 else start_year + 1
    else:
        return None
    return datetime(year, month, int(day)).date().isoformat()


def parse_openfootball_text(text: str, source_path: str) -> Iterator[dict[str, Any]]:
    competition = None
    season = None
    start_year = None
    stage = None
    current_date = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("="):
            title = line.lstrip("= ")
            competition = competition_from_title(title)
            key = competition.key if competition else None
            season, start_year = season_parts(title, key)
            current_date = None
            continue
        if line.startswith("▪"):
            stage = line.lstrip("▪ ")
            continue

        date_match = DATE_RE.match(line)
        if date_match:
            calendar_year = bool(
                competition
                and (
                    competition.key in CALENDAR_YEAR_KEYS
                    or competition.scope == "international"
                    or (season and "-" not in season)
                )
            )
            current_date = resolve_date(
                date_match.group(1),
                date_match.group(2),
                date_match.group(3),
                start_year,
                calendar_year=calendar_year,
            )
            continue

        match = MATCH_RE.match(line)
        if not (match and competition and current_date):
            continue

        home = COUNTRY_SUFFIX_RE.sub("", match.group(2)).strip()
        away = COUNTRY_SUFFIX_RE.sub("", match.group(3)).strip()
        row = {
            "competition_key": competition.key,
            "competition_name": competition.name,
            "scope": competition.scope,
            "season": season,
            "stage": stage,
            "match_date": current_date,
            "kickoff_time": match.group(1),
            "home_team": home,
            "away_team": away,
            "home_score_ft": int(match.group(4)),
            "away_score_ft": int(match.group(5)),
            "home_score_ht": integer(match.group(6)),
            "away_score_ht": integer(match.group(7)),
            "extra_json": json.dumps({"openfootball_path": source_path}, ensure_ascii=False),
        }
        row["result"] = outcome(row["home_score_ft"], row["away_score_ft"])
        yield row


def import_openfootball(warehouse: Warehouse, downloader: Downloader) -> dict[str, Any]:
    files_seen = matches = 0
    per_competition: dict[str, int] = {}

    for repo in REPOSITORIES:
        url = f"https://github.com/openfootball/{repo}/archive/refs/heads/master.zip"
        archive = downloader.cache / "openfootball" / f"{repo}.zip"
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.exists() or downloader.refresh:
            response = downloader.session.get(url, timeout=120)
            response.raise_for_status()
            archive.write_bytes(response.content)

        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                if not name.endswith(".txt"):
                    continue
                files_seen += 1
                try:
                    text = zf.read(name).decode("utf-8", errors="replace")
                except Exception:
                    continue
                for row in parse_openfootball_text(text, name):
                    warehouse.upsert_match(
                        row,
                        source="openfootball",
                        source_id=digest(
                            name,
                            row["match_date"],
                            row["home_team"],
                            row["away_team"],
                        ),
                        source_url=url,
                        coverage={
                            "has_ft": 1,
                            "has_ht": int(row["home_score_ht"] is not None),
                        },
                    )
                    matches += 1
                    key = row["competition_key"]
                    per_competition[key] = per_competition.get(key, 0) + 1

    warehouse.refresh_quality()
    return {
        "files_seen": files_seen,
        "matches_processed": matches,
        "per_competition": dict(sorted(per_competition.items())),
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--export-csv", type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    warehouse = Warehouse(args.db)
    warehouse.initialize()
    downloader = Downloader(args.cache, args.refresh)
    try:
        report = import_openfootball(warehouse, downloader)
        if args.export_csv:
            warehouse.export(args.export_csv)
        print(
            json.dumps(
                {"database": str(args.db), "openfootball": report, "audit": warehouse.audit()},
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    finally:
        warehouse.close()


if __name__ == "__main__":
    raise SystemExit(main())