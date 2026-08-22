#!/usr/bin/env python3
"""Enrich Athena history with scorer/minute data from schochastics football-data.

The broad schochastics parquet supplies the 1.2M-match result backbone. These
competition CSVs add scorer identities and goal times for many of Athena's
highest-priority leagues and cups.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_historical_warehouse import (  # noqa: E402
    DEFAULT_CACHE,
    DEFAULT_DB,
    Warehouse,
    digest,
    norm_team,
)

SOURCE_KEY = "schochastics_events"
BASE_URL = "https://raw.githubusercontent.com/schochastics/football-data/master/data/goals_time"
FILES = {
    "champions-league.csv": "uefa_ucl",
    "europa-league.csv": "uefa_uel",
    "eng-premier-league.csv": "eng_premier",
    "esp-primera-division.csv": "esp_laliga",
    "ita-serie-a.csv": "ita_serie_a",
    "bundesliga.csv": "ger_bundesliga",
    "fra-ligue-1.csv": "fra_ligue1",
    "eng-fa-cup.csv": "eng_fa_cup",
    "eng-league-cup.csv": "eng_efl_cup",
    "esp-copa-del-rey.csv": "esp_copa_del_rey",
    "dfb-pokal.csv": "ger_dfb_pokal",
    "fra-coupe-de-france.csv": "fra_coupe_de_france",
    "ned-eredivisie.csv": "ned_eredivisie",
    "por-primeira-liga.csv": "por_primeira",
    "tur-sueperlig.csv": "tur_superlig",
    "bel-pro-league.csv": "bel_proleague",
    "nor-eliteserien.csv": "nor_eliteserien",
    "sui-super-league.csv": "sui_superleague",
    "gre-super-league.csv": "gre_superleague",
}
GAME_RE = re.compile(
    r"^\s*(.+?)\s+vs\.?\s+(.+?)\s+(\d+)\s*:\s*(\d+)\s*$",
    re.IGNORECASE,
)
MINUTE_RE = re.compile(r"^\s*(\d+)(?:\s*\+\s*(\d+))?")


def download(cache: Path, filename: str, refresh: bool) -> str:
    destination = cache / "schochastics-goals-time" / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not refresh:
        return destination.read_text(encoding="utf-8-sig", errors="replace")
    response = requests.get(
        f"{BASE_URL}/{filename}",
        timeout=180,
        headers={"User-Agent": "ATHENA historical warehouse/1.0"},
    )
    response.raise_for_status()
    destination.write_bytes(response.content)
    return response.content.decode("utf-8-sig", errors="replace")


def parse_minute(value: Any) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    match = MINUTE_RE.match(str(value).replace("'", "").strip())
    if not match:
        return None, None
    minute = int(match.group(1))
    stoppage = int(match.group(2)) if match.group(2) else 0
    return minute, stoppage or None


def parse_game(value: Any) -> tuple[str, str, int, int] | None:
    match = GAME_RE.match(str(value or ""))
    if not match:
        return None
    return (
        match.group(1).strip(),
        match.group(2).strip(),
        int(match.group(3)),
        int(match.group(4)),
    )


def similarity(left: str, right: str) -> float:
    a, b = norm_team(left), norm_team(right)
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def resolve_match(
    warehouse: Warehouse,
    competition_key: str,
    match_date: str,
    home: str | None,
    away: str | None,
    scoring_team: str | None,
) -> str | None:
    rows = warehouse.conn.execute(
        """SELECT match_key,home_team,away_team FROM warehouse_matches
           WHERE competition_key=? AND match_date=?""",
        (competition_key, match_date),
    ).fetchall()
    if not rows:
        return None

    if home and away:
        for row in rows:
            if norm_team(row["home_team"]) == norm_team(home) and norm_team(row["away_team"]) == norm_team(away):
                return row["match_key"]
        ranked = sorted(
            (
                (
                    (similarity(row["home_team"], home) + similarity(row["away_team"], away)) / 2,
                    row["match_key"],
                )
                for row in rows
            ),
            reverse=True,
        )
        if ranked and ranked[0][0] >= 0.82:
            return ranked[0][1]

    if scoring_team:
        ranked = []
        for row in rows:
            score = max(
                similarity(row["home_team"], scoring_team),
                similarity(row["away_team"], scoring_team),
            )
            ranked.append((score, row["match_key"]))
        ranked.sort(reverse=True)
        if ranked and ranked[0][0] >= 0.9:
            return ranked[0][1]
    return None


def maybe_fill_half_time(warehouse: Warehouse, match_key: str) -> bool:
    match = warehouse.conn.execute(
        """SELECT home_team,away_team,home_score_ft,away_score_ft,
                  home_score_et,away_score_et,home_score_ht,away_score_ht
           FROM warehouse_matches WHERE match_key=?""",
        (match_key,),
    ).fetchone()
    if not match or (match["home_score_ht"] is not None and match["away_score_ht"] is not None):
        return False

    events = warehouse.conn.execute(
        """SELECT team,minute,stoppage_minute FROM warehouse_events
           WHERE match_key=? AND source_key=? AND event_type='goal'""",
        (match_key, SOURCE_KEY),
    ).fetchall()
    if not events or any(event["minute"] is None for event in events):
        return False

    final_home = match["home_score_et"] if match["home_score_et"] is not None else match["home_score_ft"]
    final_away = match["away_score_et"] if match["away_score_et"] is not None else match["away_score_ft"]
    if final_home is None or final_away is None or len(events) != int(final_home) + int(final_away):
        return False

    home_ht = away_ht = 0
    for event in events:
        minute = int(event["minute"])
        if minute > 45:
            continue
        if norm_team(event["team"] or "") == norm_team(match["home_team"]):
            home_ht += 1
        elif norm_team(event["team"] or "") == norm_team(match["away_team"]):
            away_ht += 1
        else:
            return False

    warehouse.conn.execute(
        """UPDATE warehouse_matches
           SET home_score_ht=?,away_score_ht=?,updated_at=CURRENT_TIMESTAMP
           WHERE match_key=? AND home_score_ht IS NULL AND away_score_ht IS NULL""",
        (home_ht, away_ht, match_key),
    )
    priority = warehouse.priority(SOURCE_KEY)
    warehouse.conn.executemany(
        """INSERT OR IGNORE INTO warehouse_field_provenance
           (match_key,field_name,source_key,source_priority)
           VALUES(?,?,?,?)""",
        [
            (match_key, "home_score_ht", SOURCE_KEY, priority),
            (match_key, "away_score_ht", SOURCE_KEY, priority),
        ],
    )
    warehouse.conn.execute(
        """UPDATE warehouse_match_sources SET has_ht=1
           WHERE match_key=? AND source_key=?""",
        (match_key, SOURCE_KEY),
    )
    return True


def enrich(warehouse: Warehouse, cache: Path, refresh: bool = False) -> dict[str, Any]:
    events = matched_rows = unmatched_rows = ht_filled = 0
    matches_touched: set[str] = set()
    per_competition: dict[str, int] = {}

    for filename, competition_key in FILES.items():
        text = download(cache, filename, refresh)
        reader = csv.DictReader(io.StringIO(text))
        for row_number, row in enumerate(reader, start=2):
            date = str(row.get("date") or "").strip()
            if not date:
                unmatched_rows += 1
                continue
            parsed_game = parse_game(row.get("game"))
            home = parsed_game[0] if parsed_game else None
            away = parsed_game[1] if parsed_game else None
            scoring_team = str(row.get("scoring_team") or "").strip() or None
            key = resolve_match(
                warehouse,
                competition_key,
                date,
                home,
                away,
                scoring_team,
            )
            if not key:
                unmatched_rows += 1
                continue

            player = str(row.get("scoring_player") or "").strip() or None
            minute, stoppage = parse_minute(row.get("time"))
            source_event_id = f"{filename}:{row_number}"
            warehouse.event(
                key,
                SOURCE_KEY,
                source_event_id,
                "goal",
                event_subtype="scorer_minute",
                team=scoring_team,
                player=player,
                minute=minute,
                stoppage_minute=stoppage,
                period="first half" if minute is not None and minute <= 45 else "second half" if minute is not None and minute <= 90 else "extra time" if minute is not None else None,
                outcome="goal",
                details={
                    "source_file": filename,
                    "published_home_score_after_goal": row.get("GH"),
                    "published_away_score_after_goal": row.get("GA"),
                    "source_season": row.get("season"),
                },
                source_url=f"{BASE_URL}/{filename}",
            )
            source_match_id = digest(competition_key, date, home, away)
            warehouse.conn.execute(
                """INSERT OR IGNORE INTO warehouse_match_sources(
                   match_key,source_key,source_match_id,source_url,has_events
                ) VALUES(?,?,?,?,1)""",
                (key, SOURCE_KEY, source_match_id, f"{BASE_URL}/{filename}"),
            )
            warehouse.conn.execute(
                """UPDATE warehouse_match_sources SET has_events=1
                   WHERE match_key=? AND source_key=?""",
                (key, SOURCE_KEY),
            )
            matched_rows += 1
            events += 1
            matches_touched.add(key)
            per_competition[competition_key] = per_competition.get(competition_key, 0) + 1

    for key in matches_touched:
        if maybe_fill_half_time(warehouse, key):
            ht_filled += 1

    warehouse.conn.commit()
    warehouse.refresh_quality()
    return {
        "events": events,
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows,
        "matches_touched": len(matches_touched),
        "half_time_scores_derived": ht_filled,
        "per_competition": dict(sorted(per_competition.items())),
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    warehouse = Warehouse(args.db)
    warehouse.initialize()
    try:
        report = enrich(warehouse, args.cache, args.refresh)
        print(
            json.dumps(
                {"database": str(args.db), "schochastics_events": report, "audit": warehouse.audit()},
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    finally:
        warehouse.close()


if __name__ == "__main__":
    raise SystemExit(main())
