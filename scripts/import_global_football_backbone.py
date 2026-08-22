#!/usr/bin/env python3
"""Import the 1.2M-match schochastics football-data parquet into Athena history.

This source is a broad result backbone (1888-2023), not an event authority.
Richer sources in build_historical_warehouse.py have higher source priority and
will replace/augment its fields where they overlap.

Athena's named hierarchy competitions keep dedicated competition keys. Other
European and global top-flight leagues are retained in catch-all buckets rather
than discarded, preserving the breadth of the 1.2M-match source while keeping
hierarchy coverage auditable. Catch-all fixture identity includes the original
source competition so same-named clubs in different countries cannot collide.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_historical_warehouse import (  # noqa: E402
    DEFAULT_CACHE,
    DEFAULT_DB,
    Warehouse,
    clean,
    digest,
    match_key,
    norm_team,
    outcome,
)

PARQUET_URL = "https://raw.githubusercontent.com/schochastics/football-data/master/data/results/games.parquet"
SOURCE_KEY = "schochastics_global"

COUNTRY_KEYS = {
    "england": "eng_premier", "spain": "esp_laliga", "italy": "ita_serie_a", "germany": "ger_bundesliga",
    "france": "fra_ligue1", "netherlands": "ned_eredivisie", "holland": "ned_eredivisie", "portugal": "por_primeira",
    "turkey": "tur_superlig", "belgium": "bel_proleague", "scotland": "sco_premiership",
    "norway": "nor_eliteserien", "denmark": "den_superliga", "sweden": "swe_allsvenskan",
    "switzerland": "sui_superleague", "greece": "gre_superleague", "saudi arabia": "sau_proleague",
    "saudi-arabia": "sau_proleague", "usa": "usa_mls", "united states": "usa_mls",
    "united states of america": "usa_mls",
}

UEFA_NAMES = {
    "champions league": "uefa_ucl", "uefa champions league": "uefa_ucl", "european cup": "uefa_ucl",
    "europa league": "uefa_uel", "uefa europa league": "uefa_uel", "uefa cup": "uefa_uel",
    "conference league": "uefa_uecl", "uefa conference league": "uefa_uecl",
}

INTERNATIONAL_NAMES = {
    "world cup": "intl_world_cup", "fifa world cup": "intl_world_cup", "european championship": "intl_euro",
    "euro": "intl_euro", "copa america": "intl_copa_america", "africa cup of nations": "intl_afcon",
    "african cup of nations": "intl_afcon", "asian cup": "intl_asian_cup", "gold cup": "intl_gold_cup",
}

CALENDAR_YEAR_KEYS = {"usa_mls", "nor_eliteserien", "swe_allsvenskan"}
DOMESTIC_CATCH_ALL_KEYS = {"other_euro_topflight", "other_global_topflight"}
CATCH_ALL_KEYS = {*DOMESTIC_CATCH_ALL_KEYS, "intl_other"}
PARQUET_COLUMNS = (
    "home", "away", "date", "gh", "ga", "full_time", "competition",
    "home_ident", "away_ident", "home_country", "away_country", "home_code",
    "away_code", "continent", "level",
)


def normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", " ").split())


def register_source(wh: Warehouse) -> None:
    wh.conn.execute(
        """INSERT INTO warehouse_sources(source_key,display_name,homepage,license_name,attribution,
           redistributable,source_priority,notes) VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(source_key) DO UPDATE SET display_name=excluded.display_name,homepage=excluded.homepage,
           license_name=excluded.license_name,attribution=excluded.attribution,redistributable=excluded.redistributable,
           source_priority=excluded.source_priority,notes=excluded.notes""",
        (SOURCE_KEY, "schochastics football-data", "https://github.com/schochastics/football-data",
         "Open Data Commons Attribution License (ODC-By)", "schochastics/football-data", 1, 60,
         "Broad result backbone: 1,237,935 games in 207 top-tier leagues and 20 international tournaments, 1888-2023."),
    )
    wh.conn.commit()


def download(cache: Path, refresh: bool) -> Path:
    path = cache / "schochastics" / "games.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not refresh:
        return path
    response = requests.get(PARQUET_URL, timeout=180, headers={"User-Agent": "ATHENA historical warehouse/1.0"})
    response.raise_for_status()
    path.write_bytes(response.content)
    return path


def classify(row: dict[str, Any]) -> tuple[str, str] | None:
    """Resolve named Athena hierarchy competitions without catch-all expansion."""
    competition = normalized(row.get("competition")); level = normalized(row.get("level")); continent = normalized(row.get("continent"))
    if competition in UEFA_NAMES: return "club", UEFA_NAMES[competition]
    if level == "national":
        if competition in COUNTRY_KEYS: return "club", COUNTRY_KEYS[competition]
        if continent == "europe": return "club", "other_euro_topflight"
        return None
    if competition in INTERNATIONAL_NAMES: return "international", INTERNATIONAL_NAMES[competition]
    if level == "international": return "international", "intl_other"
    return None


def classify_for_import(row: dict[str, Any]) -> tuple[str, str] | None:
    """Classify every usable top-flight/international row for warehouse retention."""
    classified = classify(row)
    if classified:
        return classified
    if normalized(row.get("level")) == "national":
        return "club", "other_global_topflight"
    return None


def season_for(date_value: Any, scope: str, competition_key: str | None = None) -> str:
    date = pd.Timestamp(date_value)
    if scope == "international" or competition_key in CALENDAR_YEAR_KEYS:
        return str(date.year)
    start = date.year if date.month >= 7 else date.year - 1
    return f"{start}-{str((start + 1) % 100).zfill(2)}"


def season_for_import(date_value: Any, scope: str, competition_key: str) -> str | None:
    """Avoid inventing a season convention for catch-all domestic leagues."""
    if competition_key in DOMESTIC_CATCH_ALL_KEYS:
        return None
    return season_for(date_value, scope, competition_key)


def backbone_match_key(match: dict[str, Any], source_competition: Any) -> str:
    """Keep raw competition identity in catch-all fixture keys to avoid collisions."""
    if match.get("competition_key") not in CATCH_ALL_KEYS:
        return match_key(match)
    return "m_" + digest(
        match.get("scope"),
        match.get("competition_key"),
        normalized(source_competition),
        match.get("match_date"),
        norm_team(match.get("home_team") or ""),
        norm_team(match.get("away_team") or ""),
    )


def import_backbone(wh: Warehouse, parquet: Path, batch_size: int = 10000) -> dict[str, int]:
    """Insert the lowest-priority result backbone in batches without overwriting richer rows."""
    frame = pd.read_parquet(parquet, columns=list(PARQUET_COLUMNS))
    columns = list(frame.columns)
    competition_names = {
        row["competition_key"]: row["display_name"]
        for row in wh.conn.execute(
            "SELECT competition_key,display_name FROM warehouse_competitions"
        )
    }
    seen = imported = skipped = 0
    match_batch: list[tuple[Any, ...]] = []; source_batch: list[tuple[Any, ...]] = []
    match_sql = """INSERT OR IGNORE INTO warehouse_matches(
        match_key,competition_key,competition_name,scope,season,match_date,home_team,away_team,
        home_score_ft,away_score_ft,home_score_et,away_score_et,home_score_pen,away_score_pen,
        result,extra_json,data_quality) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    source_sql = """INSERT OR IGNORE INTO warehouse_match_sources(
        match_key,source_key,source_match_id,source_url,has_ft) VALUES(?,?,?,?,?)"""

    def flush() -> None:
        nonlocal imported
        if not match_batch: return
        before = wh.conn.total_changes
        wh.conn.executemany(match_sql, match_batch)
        imported += wh.conn.total_changes - before
        wh.conn.executemany(source_sql, source_batch)
        wh.conn.commit(); match_batch.clear(); source_batch.clear()

    for values in frame.itertuples(index=False, name=None):
        raw = dict(zip(columns, values))
        seen += 1
        classified = classify_for_import(raw)
        if not classified:
            skipped += 1; continue
        scope, competition_key = classified
        source_competition = clean(raw.get("competition")) or competition_key
        competition_name = (
            source_competition
            if competition_key in CATCH_ALL_KEYS
            else competition_names.get(competition_key, source_competition)
        )
        date = pd.Timestamp(raw["date"]).date().isoformat(); home, away = clean(raw.get("home")), clean(raw.get("away"))
        if not home or not away or pd.isna(raw.get("gh")) or pd.isna(raw.get("ga")):
            skipped += 1; continue
        final_home, final_away = int(raw["gh"]), int(raw["ga"]); finish = normalized(raw.get("full_time")).upper()
        match = {
            "competition_key": competition_key, "competition_name": competition_name, "scope": scope,
            "season": season_for_import(raw["date"], scope, competition_key), "match_date": date, "home_team": home, "away_team": away,
            "extra_json": json.dumps({"schochastics_full_time_code": raw.get("full_time"),
                "source_competition": raw.get("competition"), "source_continent": raw.get("continent"), "source_level": raw.get("level"),
                "home_ident": raw.get("home_ident"), "away_ident": raw.get("away_ident"),
                "home_country": raw.get("home_country"), "away_country": raw.get("away_country"),
                "home_code": raw.get("home_code"), "away_code": raw.get("away_code")}, ensure_ascii=False, default=str),
        }
        if finish == "F":
            match["home_score_ft"], match["away_score_ft"] = final_home, final_away; match["result"] = outcome(final_home, final_away)
        elif finish == "E": match["home_score_et"], match["away_score_et"] = final_home, final_away
        elif finish == "P": match["home_score_pen"], match["away_score_pen"] = final_home, final_away
        else:
            match["home_score_ft"], match["away_score_ft"] = final_home, final_away; match["result"] = outcome(final_home, final_away)
        key = backbone_match_key(match, source_competition)
        match_batch.append((key, competition_key, competition_name, scope, match["season"], date, home, away,
            match.get("home_score_ft"), match.get("away_score_ft"), match.get("home_score_et"), match.get("away_score_et"),
            match.get("home_score_pen"), match.get("away_score_pen"), match.get("result"), match["extra_json"],
            "BASIC" if match.get("home_score_ft") is not None else "PARTIAL"))
        source_batch.append((key, SOURCE_KEY, digest(raw.get("home_ident"), raw.get("away_ident"), date, raw.get("competition")),
            PARQUET_URL, int(match.get("home_score_ft") is not None)))
        if len(match_batch) >= batch_size: flush()
    flush()
    return {"rows_seen": seen, "matches_inserted": imported, "rows_skipped": skipped}


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path,default=DEFAULT_DB); parser.add_argument("--cache", type=Path,default=DEFAULT_CACHE)
    parser.add_argument("--refresh", action="store_true"); parser.add_argument("--export-csv", type=Path)
    return parser.parse_args()


def main() -> int:
    options = args(); wh = Warehouse(options.db); wh.initialize(); register_source(wh)
    try:
        report = import_backbone(wh, download(options.cache, options.refresh))
        if options.export_csv: wh.export(options.export_csv)
        print(json.dumps({"database": str(options.db), "import": report, "audit": wh.audit()}, indent=2, sort_keys=True)); return 0
    finally: wh.close()


if __name__ == "__main__": raise SystemExit(main())
