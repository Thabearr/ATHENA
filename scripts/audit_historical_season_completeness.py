#!/usr/bin/env python3
"""Audit season-by-season completeness for Athena's historical warehouse.

The hierarchy coverage audit proves that a competition exists. This audit goes
further: for annual club competitions it detects missing season-start years
inside the observed historical run and flags suspiciously underfilled seasons
relative to that competition's mature-season median. Non-annual international
tournaments are reported but are not forced into an annual cadence.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.historical_competitions import ALL_COMPETITIONS  # noqa: E402
from scripts.build_historical_warehouse import DEFAULT_DB, Warehouse  # noqa: E402

ANNUAL_TYPES = {"league", "domestic_cup", "continental_cup"}
CATCH_ALL_KEYS = {"other_euro_topflight", "other_global_topflight", "intl_other"}
SEASON_YEAR_RE = re.compile(r"(?<!\d)((?:18|19|20)\d{2})(?!\d)")


def season_start_year(season: str | None, match_date: str | None) -> int | None:
    text = str(season or "").strip()
    match = SEASON_YEAR_RE.search(text)
    if match:
        return int(match.group(1))
    if match_date and len(match_date) >= 4 and match_date[:4].isdigit():
        return int(match_date[:4])
    return None


def competition_seasons(warehouse: Warehouse, competition_key: str) -> list[dict[str, Any]]:
    rows = warehouse.conn.execute(
        """SELECT season, match_date, match_key,
                  home_score_ft, away_score_ft,
                  home_score_ht, away_score_ht,
                  referee, home_coach, away_coach
           FROM warehouse_matches
           WHERE competition_key=?
           ORDER BY match_date, match_key""",
        (competition_key,),
    ).fetchall()

    buckets: dict[int, dict[str, Any]] = {}
    for row in rows:
        year = season_start_year(row["season"], row["match_date"])
        if year is None:
            continue
        bucket = buckets.setdefault(
            year,
            {
                "season_start_year": year,
                "matches": 0,
                "oldest_match": None,
                "newest_match": None,
                "with_ft": 0,
                "with_ht": 0,
                "with_referee": 0,
                "with_both_coaches": 0,
                "source_keys": set(),
            },
        )
        bucket["matches"] += 1
        date = row["match_date"]
        bucket["oldest_match"] = date if bucket["oldest_match"] is None else min(bucket["oldest_match"], date)
        bucket["newest_match"] = date if bucket["newest_match"] is None else max(bucket["newest_match"], date)
        bucket["with_ft"] += int(row["home_score_ft"] is not None and row["away_score_ft"] is not None)
        bucket["with_ht"] += int(row["home_score_ht"] is not None and row["away_score_ht"] is not None)
        bucket["with_referee"] += int(bool(str(row["referee"] or "").strip()))
        bucket["with_both_coaches"] += int(bool(row["home_coach"] and row["away_coach"]))

    source_rows = warehouse.conn.execute(
        """SELECT m.season, m.match_date, s.source_key
           FROM warehouse_match_sources s
           JOIN warehouse_matches m ON m.match_key=s.match_key
           WHERE m.competition_key=?""",
        (competition_key,),
    ).fetchall()
    for row in source_rows:
        year = season_start_year(row["season"], row["match_date"])
        if year in buckets:
            buckets[year]["source_keys"].add(row["source_key"])

    result = []
    for year in sorted(buckets):
        item = buckets[year]
        item["source_keys"] = sorted(item["source_keys"])
        item["source_count"] = len(item["source_keys"])
        result.append(item)
    return result


def audit_season_completeness(
    warehouse: Warehouse,
    *,
    underfill_ratio: float = 0.60,
    min_reference_matches: int = 8,
) -> dict[str, Any]:
    competitions: list[dict[str, Any]] = []
    all_missing: list[dict[str, Any]] = []
    all_underfilled: list[dict[str, Any]] = []

    for comp in sorted(ALL_COMPETITIONS, key=lambda c: (c.scope, c.rank, c.key)):
        seasons = competition_seasons(warehouse, comp.key)
        annual_required = comp.scope == "club" and comp.competition_type in ANNUAL_TYPES and comp.key not in CATCH_ALL_KEYS
        observed_years = [s["season_start_year"] for s in seasons]
        missing_years: list[int] = []
        if annual_required and len(observed_years) >= 2:
            observed = set(observed_years)
            missing_years = [year for year in range(min(observed), max(observed) + 1) if year not in observed]

        counts = [s["matches"] for s in seasons if s["matches"] >= min_reference_matches]
        reference_median = float(statistics.median(counts)) if counts else 0.0
        threshold = max(min_reference_matches, int(reference_median * underfill_ratio)) if reference_median else 0
        underfilled = []
        if annual_required and threshold:
            newest_year = max(observed_years) if observed_years else None
            for season in seasons:
                # The newest season may be in progress; report it but do not fail on volume alone.
                if season["season_start_year"] == newest_year:
                    continue
                if season["matches"] < threshold:
                    underfilled.append(
                        {
                            "season_start_year": season["season_start_year"],
                            "matches": season["matches"],
                            "minimum_expected": threshold,
                        }
                    )

        comp_report = {
            "competition_key": comp.key,
            "competition_name": comp.name,
            "scope": comp.scope,
            "competition_type": comp.competition_type,
            "annual_completeness_required": annual_required,
            "observed_seasons": len(seasons),
            "oldest_season_start_year": min(observed_years) if observed_years else None,
            "newest_season_start_year": max(observed_years) if observed_years else None,
            "reference_match_median": reference_median,
            "underfill_threshold": threshold,
            "missing_season_start_years": missing_years,
            "underfilled_seasons": underfilled,
            "seasons": seasons,
        }
        competitions.append(comp_report)
        all_missing.extend({"competition_key": comp.key, "season_start_year": year} for year in missing_years)
        all_underfilled.extend({"competition_key": comp.key, **item} for item in underfilled)

    return {
        "complete": not all_missing and not all_underfilled,
        "underfill_ratio": underfill_ratio,
        "min_reference_matches": min_reference_matches,
        "missing_seasons": all_missing,
        "underfilled_seasons": all_underfilled,
        "competitions": competitions,
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--underfill-ratio", type=float, default=0.60)
    parser.add_argument("--min-reference-matches", type=int, default=8)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    warehouse = Warehouse(args.db)
    warehouse.initialize()
    try:
        report = audit_season_completeness(
            warehouse,
            underfill_ratio=args.underfill_ratio,
            min_reference_matches=args.min_reference_matches,
        )
        rendered = json.dumps(report, indent=2, sort_keys=True)
        print(rendered)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        return 2 if args.strict and not report["complete"] else 0
    finally:
        warehouse.close()


if __name__ == "__main__":
    raise SystemExit(main())
