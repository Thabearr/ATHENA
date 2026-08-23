#!/usr/bin/env python3
"""Audit season-by-season completeness for Athena's historical warehouse.

The warehouse is intentionally multi-source. Raw canonical-row counts therefore
cannot be compared across eras: source overlap can inflate a season, competition
formats change, and sparse specialist providers can contribute isolated historic
matches. This audit keeps those signals visible without turning them into false
strict failures.

For annual club competitions the strict gate only fails on locally corroborated
anomalies: a one-season hole or isolated volume collapse that is independently
supported by multiple sources on both sides. Long disconnected historical runs
and single-source anomalies remain explicit diagnostics because, without an
authoritative competition-calendar manifest, they can also represent provider
coverage limits, wartime hiatuses, or format changes. Non-annual international
tournaments are reported without imposing an annual cadence.
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
                "source_fixture_ids": {},
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
        """SELECT m.season, m.match_date, s.match_key, s.source_key, s.source_match_id
           FROM warehouse_match_sources s
           JOIN warehouse_matches m ON m.match_key=s.match_key
           WHERE m.competition_key=?""",
        (competition_key,),
    ).fetchall()
    for row in source_rows:
        year = season_start_year(row["season"], row["match_date"])
        if year not in buckets:
            continue
        per_source = buckets[year]["source_fixture_ids"]
        fixture_ids = per_source.setdefault(row["source_key"], set())
        fixture_ids.add(row["source_match_id"] or f"match:{row['match_key']}")

    result = []
    for year in sorted(buckets):
        item = buckets[year]
        source_match_counts = {
            source_key: len(fixture_ids)
            for source_key, fixture_ids in sorted(item.pop("source_fixture_ids").items())
        }
        effective_matches = max(source_match_counts.values(), default=item["matches"])
        effective_sources = sorted(
            source_key for source_key, count in source_match_counts.items() if count == effective_matches
        )
        item["source_match_counts"] = source_match_counts
        item["source_keys"] = sorted(source_match_counts)
        item["source_count"] = len(source_match_counts)
        item["effective_matches"] = effective_matches
        item["effective_source_keys"] = effective_sources
        result.append(item)
    return result


def _stable_flanks(left: int, right: int, *, min_reference_matches: int, max_flank_ratio: float) -> bool:
    if left < min_reference_matches or right < min_reference_matches:
        return False
    low = min(left, right)
    high = max(left, right)
    return low > 0 and high / low <= max_flank_ratio


def _source_confirmations(
    left: dict[str, Any],
    current: dict[str, Any] | None,
    right: dict[str, Any],
    *,
    underfill_ratio: float,
    min_reference_matches: int,
    max_flank_ratio: float,
) -> list[str]:
    confirmations: list[str] = []
    left_counts = left["source_match_counts"]
    right_counts = right["source_match_counts"]
    current_counts = current["source_match_counts"] if current else {}
    for source_key in sorted(set(left_counts) & set(right_counts)):
        left_count = left_counts[source_key]
        right_count = right_counts[source_key]
        if not _stable_flanks(
            left_count,
            right_count,
            min_reference_matches=min_reference_matches,
            max_flank_ratio=max_flank_ratio,
        ):
            continue
        if current is None:
            confirmations.append(source_key)
            continue
        reference = statistics.median((left_count, right_count))
        threshold = max(min_reference_matches, int(reference * underfill_ratio))
        if current_counts.get(source_key, 0) < threshold:
            confirmations.append(source_key)
    return confirmations


def audit_season_completeness(
    warehouse: Warehouse,
    *,
    underfill_ratio: float = 0.60,
    min_reference_matches: int = 8,
    min_confirming_sources: int = 2,
    max_flank_ratio: float = 1.50,
) -> dict[str, Any]:
    competitions: list[dict[str, Any]] = []
    all_missing: list[dict[str, Any]] = []
    confirmed_missing: list[dict[str, Any]] = []
    all_underfilled: list[dict[str, Any]] = []
    confirmed_underfilled: list[dict[str, Any]] = []
    all_disconnected: list[dict[str, Any]] = []

    for comp in sorted(ALL_COMPETITIONS, key=lambda c: (c.scope, c.rank, c.key)):
        seasons = competition_seasons(warehouse, comp.key)
        annual_required = (
            comp.scope == "club"
            and comp.competition_type in ANNUAL_TYPES
            and comp.key not in CATCH_ALL_KEYS
        )
        by_year = {season["season_start_year"]: season for season in seasons}
        observed_years = sorted(by_year)
        mature_years = [
            year for year in observed_years if by_year[year]["effective_matches"] >= min_reference_matches
        ]

        missing: list[dict[str, Any]] = []
        disconnected: list[dict[str, Any]] = []
        if annual_required and len(mature_years) >= 2:
            for left_year, right_year in zip(mature_years, mature_years[1:]):
                gap = right_year - left_year - 1
                if gap <= 0:
                    continue
                if gap > 1:
                    disconnected.append(
                        {
                            "after_season_start_year": left_year,
                            "before_season_start_year": right_year,
                            "missing_years": list(range(left_year + 1, right_year)),
                        }
                    )
                    continue

                year = left_year + 1
                # If the year exists but is tiny, underfill logic handles it.
                if year in by_year:
                    continue
                confirming_sources = _source_confirmations(
                    by_year[left_year],
                    None,
                    by_year[right_year],
                    underfill_ratio=underfill_ratio,
                    min_reference_matches=min_reference_matches,
                    max_flank_ratio=max_flank_ratio,
                )
                missing.append(
                    {
                        "season_start_year": year,
                        "confirming_sources": confirming_sources,
                        "confirmed": len(confirming_sources) >= min_confirming_sources,
                    }
                )

        underfilled: list[dict[str, Any]] = []
        newest_year = max(observed_years) if observed_years else None
        if annual_required:
            for year in observed_years:
                if year == newest_year or year - 1 not in by_year or year + 1 not in by_year:
                    continue
                current = by_year[year]
                left = by_year[year - 1]
                right = by_year[year + 1]
                left_count = left["effective_matches"]
                right_count = right["effective_matches"]
                if not _stable_flanks(
                    left_count,
                    right_count,
                    min_reference_matches=min_reference_matches,
                    max_flank_ratio=max_flank_ratio,
                ):
                    continue
                reference = float(statistics.median((left_count, right_count)))
                threshold = max(min_reference_matches, int(reference * underfill_ratio))
                if current["effective_matches"] >= threshold:
                    continue
                confirming_sources = _source_confirmations(
                    left,
                    current,
                    right,
                    underfill_ratio=underfill_ratio,
                    min_reference_matches=min_reference_matches,
                    max_flank_ratio=max_flank_ratio,
                )
                underfilled.append(
                    {
                        "season_start_year": year,
                        "matches": current["matches"],
                        "effective_matches": current["effective_matches"],
                        "minimum_expected": threshold,
                        "local_reference_median": reference,
                        "confirming_sources": confirming_sources,
                        "confirmed": len(confirming_sources) >= min_confirming_sources,
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
            "missing_season_start_years": [item["season_start_year"] for item in missing],
            "confirmed_missing_season_start_years": [
                item["season_start_year"] for item in missing if item["confirmed"]
            ],
            "missing_seasons": missing,
            "disconnected_historical_runs": disconnected,
            "underfilled_seasons": underfilled,
            "seasons": seasons,
        }
        competitions.append(comp_report)

        for item in missing:
            row = {"competition_key": comp.key, **item}
            all_missing.append(row)
            if item["confirmed"]:
                confirmed_missing.append(row)
        for item in underfilled:
            row = {"competition_key": comp.key, **item}
            all_underfilled.append(row)
            if item["confirmed"]:
                confirmed_underfilled.append(row)
        all_disconnected.extend({"competition_key": comp.key, **item} for item in disconnected)

    return {
        "complete": not confirmed_missing and not confirmed_underfilled,
        "underfill_ratio": underfill_ratio,
        "min_reference_matches": min_reference_matches,
        "min_confirming_sources": min_confirming_sources,
        "max_flank_ratio": max_flank_ratio,
        "missing_seasons": all_missing,
        "confirmed_missing_seasons": confirmed_missing,
        "underfilled_seasons": all_underfilled,
        "confirmed_underfilled_seasons": confirmed_underfilled,
        "disconnected_historical_runs": all_disconnected,
        "competitions": competitions,
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--underfill-ratio", type=float, default=0.60)
    parser.add_argument("--min-reference-matches", type=int, default=8)
    parser.add_argument("--min-confirming-sources", type=int, default=2)
    parser.add_argument("--max-flank-ratio", type=float, default=1.50)
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
            min_confirming_sources=args.min_confirming_sources,
            max_flank_ratio=args.max_flank_ratio,
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
