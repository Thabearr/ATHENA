#!/usr/bin/env python3
"""Import the 1.2M-match schochastics football-data parquet into Athena history.

This source is a broad result backbone (1888-2023), not an event authority.
Richer sources in build_historical_warehouse.py have higher source priority and
will replace/augment its fields where they overlap.
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
    outcome,
)

PARQUET_URL = "https://raw.githubusercontent.com/schochastics/football-data/master/data/results/games.parquet"
SOURCE_KEY = "schochastics_global"

COUNTRY_KEYS = {
    "england": "eng_premier", "spain": "esp_laliga", "italy": "ita_serie_a", "germany": "ger_bundesliga",
    "france": "fra_ligue1", "netherlands": "ned_eredivisie", "holland": "ned_eredivisie", "portugal": "por_primeira",
    "turkey": "tur_superlig", "belgium": "bel_proleague", "norway": "nor_eliteserien", "denmark": "den_superliga",
    "sweden": "swe_allsvenskan", "switzerland": "sui_superleague", "greece": "gre_superleague",
    "saudi arabia": "sau_proleague", "saudi-arabia": "sau_proleague", "usa": "usa_mls",
    "united states": "usa_mls", "united states of america": "usa_mls",
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


def normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", " ").split())


def register_source(wh: Warehouse) -> None:
    wh.conn.execute(
        """INSERT INTO warehouse_sources(source_key,display_name,homepage,license_name,attribution,
           redistributable,source_priority,notes) VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(source_key) DO UPDATE SET display_name=excluded.display_name,homepage=excluded.homepage,
           license_name=excluded.license_name,attribution=excluded.attribution,redistributable=excluded.redistributable,
           source_priority=excluded.source_priority,notes=excluded.notes""",
        (
            SOURCE_KEY, "schochastics football-data", "https://github.com/schochastics/football-data",
            "Open Data Commons Attribution License (ODC-By)", "schochastics/football-data", 1, 60,
            "Broad result backbone: 1,237,935 games in 207 top-tier leagues and 20 international tournaments, 1888-2023.",
        ),
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
    competition = normalized(row.get("competition"))
    level = normalized(row.get("level"))
    continent = normalized(row.get("continent"))
    if competition in UEFA_NAMES:
        return "club", UEFA_NAMES[competition]
    if level == "national":
        if competition in COUNTRY_KEYS:
            return "club", COUNTRY_KEYS[competition]
        if continent == "europe":
            return "club", "other_euro_topflight"
        return None
    if competition in INTERNATIONAL_NAMES:
        return "international", INTERNATIONAL_NAMES[competition]
    if level == "international":
        return "international", "intl_other"
    return None


def season_for(date_value: Any, scope: str) -> str:
    date = pd.Timestamp(date_value)
    if scope == "international":
        return str(date.year)
    start = date.year if date.month >= 7 else date.year - 1
    return f"{start}-{str((start + 1) % 100).zfill(2)}"


def import_backbone(wh: Warehouse, parquet: Path) -> dict[str, int]:
    frame = pd.read_parquet(parquet)
    seen = imported = skipped = 0
    for raw in frame.to_dict(orient="records"):
        seen += 1
        classified = classify(raw)
        if not classified:
            skipped += 1
            continue
        scope, competition_key = classified
        competition_row = wh.conn.execute(
            "SELECT display_name FROM warehouse_competitions WHERE competition_key=?", (competition_key,)
        ).fetchone()
        competition_name = competition_row[0] if competition_row else str(raw.get("competition") or competition_key)
        date = pd.Timestamp(raw["date"]).date().isoformat()
        home, away = clean(raw.get("home")), clean(raw.get("away"))
        if not home or not away:
            skipped += 1
            continue
        final_home, final_away = int(raw["gh"]), int(raw["ga"])
        finish = normalized(raw.get("full_time")).upper()
        match = {
            "competition_key": competition_key, "competition_name": competition_name, "scope": scope,
            "season": season_for(raw["date"], scope), "match_date": date, "home_team": home, "away_team": away,
            "extra_json": json.dumps({
                "schochastics_full_time_code": raw.get("full_time"), "home_ident": raw.get("home_ident"),
                "away_ident": raw.get("away_ident"), "home_country": raw.get("home_country"),
                "away_country": raw.get("away_country"), "home_code": raw.get("home_code"), "away_code": raw.get("away_code"),
            }, ensure_ascii=False, default=str),
        }
        # gh/ga can include extra time or shootout goals. Only F is safe as a 90-minute FT score.
        if finish == "F":
            match["home_score_ft"], match["away_score_ft"] = final_home, final_away
            match["result"] = outcome(final_home, final_away)
        elif finish == "E":
            match["home_score_et"], match["away_score_et"] = final_home, final_away
        elif finish == "P":
            match["home_score_pen"], match["away_score_pen"] = final_home, final_away
        else:
            match["home_score_ft"], match["away_score_ft"] = final_home, final_away
            match["result"] = outcome(final_home, final_away)
        wh.upsert_match(
            match, source=SOURCE_KEY,
            source_id=digest(raw.get("home_ident"), raw.get("away_ident"), date, raw.get("competition")),
            source_url=PARQUET_URL, coverage={"has_ft": int(match.get("home_score_ft") is not None)},
        )
        imported += 1
    wh.refresh_quality()
    return {"rows_seen": seen, "matches_imported": imported, "rows_skipped": skipped}


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--export-csv", type=Path)
    return parser.parse_args()


def main() -> int:
    options = args()
    wh = Warehouse(options.db)
    wh.initialize()
    register_source(wh)
    try:
        parquet = download(options.cache, options.refresh)
        report = import_backbone(wh, parquet)
        if options.export_csv:
            wh.export(options.export_csv)
        print(json.dumps({"database": str(options.db), "import": report, "audit": wh.audit()}, indent=2, sort_keys=True))
        return 0
    finally:
        wh.close()


if __name__ == "__main__":
    raise SystemExit(main())
