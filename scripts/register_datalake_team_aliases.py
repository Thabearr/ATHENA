#!/usr/bin/env python3
"""Persist source-qualified team aliases from the Global Football Data Lake.

The data lake explicitly publishes ``teams.fd_name`` as its football-data.co.uk
cross-reference. Athena stores that mapping by competition so later historical
Football-Data imports can resolve provider abbreviations without fuzzy matching.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_historical_warehouse import DEFAULT_CACHE, DEFAULT_DB, Warehouse, norm_team  # noqa: E402
from scripts.import_current_soccer_datalake import classify_league, download  # noqa: E402

SOURCE_KEY = "football_data_uk"
REQUIRED_FILES = ("leagues.parquet", "teams.parquet", "fixtures.parquet")


def safe_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def register_aliases(
    warehouse: Warehouse,
    cache: Path,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    paths = {name: download(cache, name, refresh) for name in REQUIRED_FILES}

    leagues = pd.read_parquet(paths["leagues.parquet"])
    league_keys = {
        int(row["id"]): key
        for row in leagues.to_dict(orient="records")
        if safe_int(row.get("id")) is not None and (key := classify_league(row))
    }

    teams = pd.read_parquet(paths["teams.parquet"], columns=["id", "name", "fd_name"])
    team_crosswalk: dict[int, tuple[str, str]] = {}
    for row in teams.to_dict(orient="records"):
        team_id = safe_int(row.get("id"))
        canonical = safe_text(row.get("name"))
        fd_name = safe_text(row.get("fd_name"))
        if team_id is not None and canonical and fd_name:
            team_crosswalk[team_id] = (canonical, fd_name)

    fixtures = pd.read_parquet(
        paths["fixtures.parquet"],
        columns=["league_id", "home_team_id", "away_team_id"],
    )

    # One provider alias may be harmlessly repeated across many fixtures. If the
    # same source-qualified alias resolves to different canonical teams inside a
    # single competition, do not guess: mark it ambiguous and omit it.
    candidates: dict[tuple[str, str], set[tuple[str, int]]] = defaultdict(set)
    for row in fixtures.itertuples(index=False):
        league_id = safe_int(row.league_id)
        competition_key = league_keys.get(league_id) if league_id is not None else None
        if not competition_key:
            continue
        for raw_team_id in (row.home_team_id, row.away_team_id):
            team_id = safe_int(raw_team_id)
            crosswalk = team_crosswalk.get(team_id) if team_id is not None else None
            if not crosswalk:
                continue
            canonical, alias = crosswalk
            alias_norm = norm_team(alias)
            if alias_norm:
                candidates[(competition_key, alias_norm)].add((canonical, team_id))

    rows: list[tuple[str, str, str, str, str, str]] = []
    ambiguous: list[dict[str, Any]] = []
    for (competition_key, alias_norm), resolved in sorted(candidates.items()):
        canonical_names = {canonical for canonical, _ in resolved}
        if len(canonical_names) != 1:
            ambiguous.append(
                {
                    "competition_key": competition_key,
                    "alias_norm": alias_norm,
                    "canonical_candidates": sorted(canonical_names),
                }
            )
            continue
        canonical, team_id = sorted(resolved)[0]
        # Recover the source spelling from the team crosswalk. All rows grouped
        # here share the same normalized football-data alias.
        alias = team_crosswalk[team_id][1]
        rows.append(
            (
                competition_key,
                SOURCE_KEY,
                alias,
                alias_norm,
                canonical,
                str(team_id),
            )
        )

    warehouse.conn.executemany(
        """INSERT INTO warehouse_team_aliases(
               competition_key,source_key,alias,alias_norm,canonical_team,source_team_id,updated_at
           ) VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(competition_key,source_key,alias_norm) DO UPDATE SET
               alias=excluded.alias,
               canonical_team=excluded.canonical_team,
               source_team_id=excluded.source_team_id,
               updated_at=CURRENT_TIMESTAMP""",
        rows,
    )
    warehouse.conn.commit()

    per_competition: dict[str, int] = defaultdict(int)
    for competition_key, *_ in rows:
        per_competition[competition_key] += 1
    return {
        "aliases_registered": len(rows),
        "ambiguous_aliases_skipped": len(ambiguous),
        "ambiguous_examples": ambiguous[:25],
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
        report = register_aliases(warehouse, args.cache, refresh=args.refresh)
        print(json.dumps({"database": str(args.db), "team_aliases": report}, indent=2, sort_keys=True))
        return 0
    finally:
        warehouse.close()


if __name__ == "__main__":
    raise SystemExit(main())
