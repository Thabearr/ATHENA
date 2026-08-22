#!/usr/bin/env python3
"""Import the current Global Football Data Lake into Athena's history warehouse.

This source fills the post-2023/current-data gap with fixtures, HT scores,
match statistics, referees, coaches, formations and optional player-level
appearances/goals/cards. The 1.2M schochastics dataset remains the deep
historical backbone; this layer is intentionally imported first so the
lower-priority backbone can only fill gaps.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.historical_competitions import FOOTBALL_DATA_CODES, competition_by_key  # noqa: E402
from scripts.build_historical_warehouse import (  # noqa: E402
    DEFAULT_CACHE,
    DEFAULT_DB,
    MATCH_FIELDS,
    Warehouse,
    clean,
    digest,
    match_key,
    outcome,
)

SOURCE_KEY = "soccer_datalake"
BASE_URL = "https://huggingface.co/datasets/eatpizzanot/soccer-dataset/resolve/main"
CORE_FILES = (
    "leagues.parquet",
    "teams.parquet",
    "fixtures.parquet",
    "match_stats.parquet",
    "fixture_lineups.parquet",
)
DEEP_FILES = (
    "fixture_players.parquet",
    "fixture_players_stats_flat.parquet",
)
CALENDAR_YEAR_KEYS = {"usa_mls", "nor_eliteserien", "swe_allsvenskan"}

COUNTRY_LEAGUES = {
    ("england", "premier league"): "eng_premier",
    ("england", "championship"): "eng_championship",
    ("spain", "la liga"): "esp_laliga",
    ("spain", "primera division"): "esp_laliga",
    ("italy", "serie a"): "ita_serie_a",
    ("germany", "bundesliga"): "ger_bundesliga",
    ("france", "ligue 1"): "fra_ligue1",
    ("netherlands", "eredivisie"): "ned_eredivisie",
    ("portugal", "primeira liga"): "por_primeira",
    ("portugal", "liga portugal"): "por_primeira",
    ("turkey", "super lig"): "tur_superlig",
    ("turkey", "süper lig"): "tur_superlig",
    ("belgium", "jupiler pro league"): "bel_proleague",
    ("belgium", "pro league"): "bel_proleague",
    ("belgium", "first division a"): "bel_proleague",
    ("norway", "eliteserien"): "nor_eliteserien",
    ("denmark", "superliga"): "den_superliga",
    ("denmark", "superligaen"): "den_superliga",
    ("sweden", "allsvenskan"): "swe_allsvenskan",
    ("switzerland", "super league"): "sui_superleague",
    ("switzerland", "swiss super league"): "sui_superleague",
    ("greece", "super league 1"): "gre_superleague",
    ("greece", "super league"): "gre_superleague",
    ("greece", "super league greece"): "gre_superleague",
    ("saudi arabia", "pro league"): "sau_proleague",
    ("saudi arabia", "saudi pro league"): "sau_proleague",
    ("usa", "major league soccer"): "usa_mls",
    ("united states", "major league soccer"): "usa_mls",
}

COUNTRY_CUPS = {
    ("england", "fa cup"): "eng_fa_cup",
    ("england", "league cup"): "eng_efl_cup",
    ("england", "efl cup"): "eng_efl_cup",
    ("england", "carabao cup"): "eng_efl_cup",
    ("spain", "copa del rey"): "esp_copa_del_rey",
    ("italy", "coppa italia"): "ita_coppa_italia",
    ("germany", "dfb pokal"): "ger_dfb_pokal",
    ("france", "coupe de france"): "fra_coupe_de_france",
}

CONTINENTAL = {
    "uefa champions league": "uefa_ucl",
    "champions league": "uefa_ucl",
    "uefa europa league": "uefa_uel",
    "europa league": "uefa_uel",
    "uefa europa conference league": "uefa_uecl",
    "uefa conference league": "uefa_uecl",
    "conference league": "uefa_uecl",
}

INTERNATIONAL = {
    "world cup": "intl_world_cup",
    "fifa world cup": "intl_world_cup",
    "euro championship": "intl_euro",
    "uefa euro championship": "intl_euro",
    "uefa european championship": "intl_euro",
    "copa america": "intl_copa_america",
    "copa américa": "intl_copa_america",
    "africa cup of nations": "intl_afcon",
    "african cup of nations": "intl_afcon",
    "asian cup": "intl_asian_cup",
    "afc asian cup": "intl_asian_cup",
    "concacaf gold cup": "intl_gold_cup",
    "gold cup": "intl_gold_cup",
    "uefa nations league": "intl_nations_league",
    "concacaf nations league": "intl_nations_league",
    "friendlies": "intl_friendly",
    "friendly international": "intl_friendly",
}


def norm(value: Any) -> str:
    text = str(value or "").casefold().replace("_", " ").replace("-", " ")
    return " ".join(text.split())


def safe_int(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_league(row: dict[str, Any]) -> str | None:
    fd_code = clean(row.get("fd_code"))
    if fd_code and fd_code.upper() in FOOTBALL_DATA_CODES:
        return FOOTBALL_DATA_CODES[fd_code.upper()]

    country = norm(row.get("country"))
    name = norm(row.get("name"))
    pair = (country, name)
    if pair in COUNTRY_LEAGUES:
        return COUNTRY_LEAGUES[pair]
    if pair in COUNTRY_CUPS:
        return COUNTRY_CUPS[pair]
    if name in CONTINENTAL:
        return CONTINENTAL[name]
    if country in {"world", "international"} and name in INTERNATIONAL:
        return INTERNATIONAL[name]

    if country in {"world", "international"}:
        if "world cup" in name and ("qualification" in name or "qualifier" in name):
            return "intl_world_cup_qual"
        if (
            "qualification" in name
            and any(token in name for token in ("euro", "africa cup", "asian cup"))
        ):
            return "intl_continental_qual"
        if "nations league" in name:
            return "intl_nations_league"
        if "friend" in name:
            return "intl_friendly"
    return None


def season_for(date_value: Any, competition_key: str) -> str:
    date = pd.Timestamp(date_value)
    comp = competition_by_key(competition_key)
    if (comp and comp.scope == "international") or competition_key in CALENDAR_YEAR_KEYS:
        return str(date.year)
    start = date.year if date.month >= 7 else date.year - 1
    return f"{start}-{str((start + 1) % 100).zfill(2)}"


def download(cache: Path, filename: str, refresh: bool = False) -> Path:
    destination = cache / "soccer-datalake" / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not refresh:
        return destination

    url = f"{BASE_URL}/{filename}"
    with requests.get(
        url,
        stream=True,
        timeout=600,
        headers={"User-Agent": "ATHENA historical warehouse/1.0"},
    ) as response:
        response.raise_for_status()
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with temporary.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
        temporary.replace(destination)
    return destination


def _stats_dict(frame: pd.DataFrame) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in frame.to_dict(orient="records"):
        fixture_id = safe_int(row.get("fixture_id"))
        if fixture_id is not None:
            result[fixture_id] = row
    return result


def _lineup_dict(frame: pd.DataFrame) -> dict[int, dict[int, dict[str, Any]]]:
    result: dict[int, dict[int, dict[str, Any]]] = {}
    for row in frame.to_dict(orient="records"):
        fixture_id = safe_int(row.get("fixture_id"))
        team_id = safe_int(row.get("team_id"))
        if fixture_id is not None and team_id is not None:
            result.setdefault(fixture_id, {})[team_id] = row
    return result


def import_core(
    warehouse: Warehouse,
    cache: Path,
    *,
    refresh: bool = False,
    batch_size: int = 5000,
) -> dict[str, Any]:
    paths = {name: download(cache, name, refresh) for name in CORE_FILES}

    leagues = pd.read_parquet(paths["leagues.parquet"])
    league_keys = {
        int(row["id"]): key
        for row in leagues.to_dict(orient="records")
        if (key := classify_league(row))
    }

    teams = pd.read_parquet(paths["teams.parquet"], columns=["id", "name"])
    team_names = {
        int(row["id"]): str(row["name"])
        for row in teams.to_dict(orient="records")
        if safe_int(row.get("id")) is not None and clean(row.get("name"))
    }

    stats = _stats_dict(pd.read_parquet(paths["match_stats.parquet"]))
    team_lineups = _lineup_dict(pd.read_parquet(paths["fixture_lineups.parquet"]))

    fixture_columns = [
        "id",
        "api_football_id",
        "date_utc",
        "league_id",
        "home_team_id",
        "away_team_id",
        "goals_home",
        "goals_away",
        "status_norm",
        "is_played",
        "referee_name",
        "referee_api_id",
    ]
    fixtures = pd.read_parquet(paths["fixtures.parquet"], columns=fixture_columns)
    fixtures = fixtures[
        fixtures["is_played"].fillna(False)
        & fixtures["league_id"].isin(set(league_keys))
    ]

    insert_columns = ["match_key", *MATCH_FIELDS, "data_quality"]
    insert_sql = (
        f"INSERT OR IGNORE INTO warehouse_matches({','.join(insert_columns)}) "
        f"VALUES({','.join('?' for _ in insert_columns)})"
    )
    source_sql = """INSERT OR IGNORE INTO warehouse_match_sources(
        match_key,source_key,source_match_id,source_url,
        has_ft,has_ht,has_events,has_cards,has_lineups,has_coaches,
        has_officials,has_advanced_stats
    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"""
    provenance_sql = """INSERT OR IGNORE INTO warehouse_field_provenance(
        match_key,field_name,source_key,source_priority
    ) VALUES(?,?,?,?)"""

    match_batch: list[tuple[Any, ...]] = []
    source_batch: list[tuple[Any, ...]] = []
    provenance_batch: list[tuple[Any, ...]] = []
    fixture_to_match: dict[int, str] = {}
    processed = inserted_estimate = 0
    per_competition: dict[str, int] = {}

    def flush() -> None:
        nonlocal inserted_estimate
        if not match_batch:
            return
        before = warehouse.conn.total_changes
        warehouse.conn.executemany(insert_sql, match_batch)
        inserted_estimate += warehouse.conn.total_changes - before
        warehouse.conn.executemany(source_sql, source_batch)
        warehouse.conn.executemany(provenance_sql, provenance_batch)
        warehouse.conn.commit()
        match_batch.clear()
        source_batch.clear()
        provenance_batch.clear()

    for fixture in fixtures.to_dict(orient="records"):
        fixture_id = int(fixture["id"])
        competition_key = league_keys[int(fixture["league_id"])]
        comp = competition_by_key(competition_key)
        if not comp:
            continue
        home_id = int(fixture["home_team_id"])
        away_id = int(fixture["away_team_id"])
        home = team_names.get(home_id)
        away = team_names.get(away_id)
        if not home or not away:
            continue

        date = pd.Timestamp(fixture["date_utc"])
        stat = stats.get(fixture_id, {})
        lineup = team_lineups.get(fixture_id, {})
        home_lineup = lineup.get(home_id, {})
        away_lineup = lineup.get(away_id, {})
        status = str(fixture.get("status_norm") or "").upper()

        home_goals = safe_int(fixture.get("goals_home"))
        away_goals = safe_int(fixture.get("goals_away"))
        row: dict[str, Any] = {
            "competition_key": competition_key,
            "competition_name": comp.name,
            "scope": comp.scope,
            "season": season_for(date, competition_key),
            "match_date": date.date().isoformat(),
            "kickoff_time": date.strftime("%H:%M:%S"),
            "home_team": home,
            "away_team": away,
            "home_score_ht": safe_int(stat.get("home_goals_ht")),
            "away_score_ht": safe_int(stat.get("away_goals_ht")),
            "referee": clean(fixture.get("referee_name")),
            "home_coach": clean(home_lineup.get("coach_name")),
            "away_coach": clean(away_lineup.get("coach_name")),
            "home_xg": safe_float(stat.get("home_xg")),
            "away_xg": safe_float(stat.get("away_xg")),
            "home_possession": safe_float(stat.get("home_possession")),
            "away_possession": safe_float(stat.get("away_possession")),
            "home_shots": safe_int(stat.get("home_shots_total")),
            "away_shots": safe_int(stat.get("away_shots_total")),
            "home_shots_on_target": safe_int(stat.get("home_shots_on_goal")),
            "away_shots_on_target": safe_int(stat.get("away_shots_on_goal")),
            "home_corners": safe_int(stat.get("home_corners")),
            "away_corners": safe_int(stat.get("away_corners")),
            "home_fouls": safe_int(stat.get("home_fouls")),
            "away_fouls": safe_int(stat.get("away_fouls")),
            "home_yellows": safe_int(stat.get("home_yellow_cards")),
            "away_yellows": safe_int(stat.get("away_yellow_cards")),
            "home_reds": safe_int(stat.get("home_red_cards")),
            "away_reds": safe_int(stat.get("away_red_cards")),
            "extra_json": json.dumps(
                {
                    "soccer_datalake_fixture_id": fixture_id,
                    "api_football_id": safe_int(fixture.get("api_football_id")),
                    "status_norm": status,
                    "home_formation": clean(home_lineup.get("formation")),
                    "away_formation": clean(away_lineup.get("formation")),
                    "xg_note": "coarse provider estimate; not per-shot xG",
                },
                ensure_ascii=False,
            ),
        }

        if status in {"FT", "AWD", "WO"} and home_goals is not None and away_goals is not None:
            row["home_score_ft"] = home_goals
            row["away_score_ft"] = away_goals
            row["result"] = outcome(home_goals, away_goals)
        elif status in {"AET", "PEN"} and home_goals is not None and away_goals is not None:
            row["home_score_et"] = home_goals
            row["away_score_et"] = away_goals

        key = match_key(row)
        fixture_to_match[fixture_id] = key

        values = [row.get(field) for field in MATCH_FIELDS]
        values[MATCH_FIELDS.index("extra_json")] = row["extra_json"]
        quality = (
            "STANDARD"
            if row.get("home_score_ft") is not None
            and (
                row.get("home_score_ht") is not None
                or row.get("home_xg") is not None
                or row.get("referee") is not None
            )
            else "BASIC"
            if row.get("home_score_ft") is not None
            else "PARTIAL"
        )
        match_batch.append((key, *values, quality))

        has_ht = int(row.get("home_score_ht") is not None and row.get("away_score_ht") is not None)
        has_cards = int(
            any(
                row.get(field) is not None
                for field in ("home_yellows", "away_yellows", "home_reds", "away_reds")
            )
        )
        has_coaches = int(bool(row.get("home_coach") or row.get("away_coach")))
        has_officials = int(bool(row.get("referee")))
        has_advanced = int(bool(stat))
        source_batch.append(
            (
                key,
                SOURCE_KEY,
                str(fixture_id),
                f"{BASE_URL}/fixtures.parquet",
                int(row.get("home_score_ft") is not None),
                has_ht,
                0,
                has_cards,
                0,
                has_coaches,
                has_officials,
                has_advanced,
            )
        )
        for field, value in row.items():
            if field in MATCH_FIELDS and value not in (None, ""):
                provenance_batch.append((key, field, SOURCE_KEY, 25))

        processed += 1
        per_competition[competition_key] = per_competition.get(competition_key, 0) + 1
        if len(match_batch) >= batch_size:
            flush()
    flush()

    coach_rows = []
    official_rows = []
    for fixture in fixtures.to_dict(orient="records"):
        fixture_id = int(fixture["id"])
        key = fixture_to_match.get(fixture_id)
        if not key:
            continue
        home_id = int(fixture["home_team_id"])
        away_id = int(fixture["away_team_id"])
        lineup = team_lineups.get(fixture_id, {})
        for team_id in (home_id, away_id):
            info = lineup.get(team_id, {})
            coach = clean(info.get("coach_name"))
            team_name = team_names.get(team_id)
            if coach and team_name:
                coach_rows.append(
                    (
                        "c_" + digest(SOURCE_KEY, key, team_name, coach),
                        key,
                        SOURCE_KEY,
                        team_name,
                        coach,
                        clean(info.get("coach_api_id")),
                        "head_coach",
                        None,
                    )
                )
        referee = clean(fixture.get("referee_name"))
        if referee:
            official_rows.append(
                (
                    "o_" + digest(SOURCE_KEY, key, referee),
                    key,
                    SOURCE_KEY,
                    referee,
                    clean(fixture.get("referee_api_id")),
                    "referee",
                    None,
                )
            )

    warehouse.conn.executemany(
        """INSERT OR REPLACE INTO warehouse_coaches(
           coach_key,match_key,source_key,team,coach_name,coach_id,role,nationality
        ) VALUES(?,?,?,?,?,?,?,?)""",
        coach_rows,
    )
    warehouse.conn.executemany(
        """INSERT OR REPLACE INTO warehouse_officials(
           official_key,match_key,source_key,official_name,official_id,role,nationality
        ) VALUES(?,?,?,?,?,?,?)""",
        official_rows,
    )
    warehouse.conn.commit()
    return {
        "fixtures_processed": processed,
        "matches_inserted_estimate": inserted_estimate,
        "coaches": len(coach_rows),
        "officials": len(official_rows),
        "per_competition": dict(sorted(per_competition.items())),
        "fixture_to_match": fixture_to_match,
        "team_names": team_names,
    }


def import_deep_players(
    warehouse: Warehouse,
    cache: Path,
    *,
    fixture_to_match: dict[int, str],
    team_names: dict[int, str],
    refresh: bool = False,
) -> dict[str, int]:
    paths = {name: download(cache, name, refresh) for name in DEEP_FILES}
    selected_ids = set(fixture_to_match)
    if not selected_ids:
        return {"lineups": 0, "events": 0, "matches_with_events": 0}

    appearances = pd.read_parquet(
        paths["fixture_players.parquet"],
        columns=[
            "id",
            "fixture_id",
            "team_id",
            "player_id",
            "player_name",
            "is_starter",
            "position",
            "number",
            "captain",
            "minutes",
            "rating",
        ],
    )
    appearances = appearances[appearances["fixture_id"].isin(selected_ids)]

    player_stats = pd.read_parquet(
        paths["fixture_players_stats_flat.parquet"],
        columns=[
            "fixture_player_id",
            "fixture_id",
            "cards_red",
            "cards_yellow",
            "goals_assists",
            "goals_total",
            "penalty_scored",
        ],
    )
    player_stats = player_stats[player_stats["fixture_id"].isin(selected_ids)]

    merged = appearances.merge(
        player_stats,
        how="left",
        left_on="id",
        right_on="fixture_player_id",
        suffixes=("", "_stat"),
    )

    lineup_rows: list[tuple[Any, ...]] = []
    event_rows: list[tuple[Any, ...]] = []
    matches_with_events: set[str] = set()
    matches_with_cards: set[str] = set()

    for row in merged.to_dict(orient="records"):
        fixture_id = safe_int(row.get("fixture_id"))
        if fixture_id is None:
            continue
        key = fixture_to_match.get(fixture_id)
        if not key:
            continue
        team_id = safe_int(row.get("team_id"))
        team = team_names.get(team_id) if team_id is not None else None
        player = clean(row.get("player_name"))
        if not team or not player:
            continue

        player_id = clean(row.get("player_id"))
        lineup_key = "l_" + digest(SOURCE_KEY, key, team_id, player_id or player)
        lineup_rows.append(
            (
                lineup_key,
                key,
                SOURCE_KEY,
                team,
                player,
                player_id,
                safe_int(row.get("number")),
                clean(row.get("position")),
                int(bool(row.get("is_starter"))) if row.get("is_starter") is not None else None,
                int(bool(row.get("captain"))) if row.get("captain") is not None else None,
                safe_int(row.get("minutes")),
                json.dumps({"rating": safe_float(row.get("rating"))}, ensure_ascii=False),
            )
        )

        goals = safe_int(row.get("goals_total")) or 0
        penalties = min(safe_int(row.get("penalty_scored")) or 0, goals)
        assists = safe_int(row.get("goals_assists")) or 0
        yellows = safe_int(row.get("cards_yellow")) or 0
        reds = safe_int(row.get("cards_red")) or 0

        for sequence in range(goals):
            event_id = f"{row.get('id')}:goal:{sequence + 1}"
            event_rows.append(
                (
                    "e_" + digest(SOURCE_KEY, event_id, key),
                    key,
                    SOURCE_KEY,
                    event_id,
                    "goal",
                    "aggregate_player_stat",
                    team,
                    player,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "goal",
                    None,
                    int(sequence < penalties),
                    0,
                    None,
                    json.dumps(
                        {"minute_known": False, "player_match_assists": assists},
                        ensure_ascii=False,
                    ),
                    f"{BASE_URL}/fixture_players_stats_flat.parquet",
                )
            )
            matches_with_events.add(key)

        for card_type, count in (("yellow", yellows), ("red", reds)):
            for sequence in range(count):
                event_id = f"{row.get('id')}:card:{card_type}:{sequence + 1}"
                event_rows.append(
                    (
                        "e_" + digest(SOURCE_KEY, event_id, key),
                        key,
                        SOURCE_KEY,
                        event_id,
                        "card",
                        "aggregate_player_stat",
                        team,
                        player,
                        None,
                        None,
                        None,
                        None,
                        None,
                        "card",
                        card_type,
                        0,
                        0,
                        None,
                        json.dumps({"minute_known": False}, ensure_ascii=False),
                        f"{BASE_URL}/fixture_players_stats_flat.parquet",
                    )
                )
                matches_with_events.add(key)
                matches_with_cards.add(key)

    warehouse.conn.executemany(
        """INSERT OR REPLACE INTO warehouse_lineups(
           lineup_key,match_key,source_key,team,player,player_id,shirt_number,
           position,starter,captain,minutes_played,details_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        lineup_rows,
    )
    warehouse.conn.executemany(
        """INSERT OR REPLACE INTO warehouse_events(
           event_key,match_key,source_key,source_event_id,event_type,event_subtype,
           team,player,assist,minute,stoppage_minute,second,period,outcome,card_type,
           is_penalty,is_own_goal,xg,details_json,source_url
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        event_rows,
    )
    warehouse.conn.executemany(
        """UPDATE warehouse_match_sources
           SET has_lineups=1
           WHERE source_key=? AND source_match_id=?""",
        [(SOURCE_KEY, str(fixture_id)) for fixture_id in selected_ids],
    )
    warehouse.conn.executemany(
        """UPDATE warehouse_match_sources
           SET has_events=1
           WHERE match_key=? AND source_key=?""",
        [(key, SOURCE_KEY) for key in matches_with_events],
    )
    warehouse.conn.executemany(
        """UPDATE warehouse_match_sources
           SET has_cards=1
           WHERE match_key=? AND source_key=?""",
        [(key, SOURCE_KEY) for key in matches_with_cards],
    )
    warehouse.conn.commit()
    return {
        "lineups": len(lineup_rows),
        "events": len(event_rows),
        "matches_with_events": len(matches_with_events),
        "matches_with_cards": len(matches_with_cards),
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--deep-players",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Import player appearances plus aggregate scorer/card identities.",
    )
    parser.add_argument("--export-csv", type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    warehouse = Warehouse(args.db)
    warehouse.initialize()
    try:
        core = import_core(warehouse, args.cache, refresh=args.refresh)
        fixture_to_match = core.pop("fixture_to_match")
        team_names = core.pop("team_names")
        deep = (
            import_deep_players(
                warehouse,
                args.cache,
                fixture_to_match=fixture_to_match,
                team_names=team_names,
                refresh=args.refresh,
            )
            if args.deep_players
            else {"disabled": True}
        )
        warehouse.refresh_quality()
        if args.export_csv:
            warehouse.export(args.export_csv)
        print(
            json.dumps(
                {
                    "database": str(args.db),
                    "core": core,
                    "deep_players": deep,
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
