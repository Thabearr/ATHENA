#!/usr/bin/env python3
"""Audit Athena's historical warehouse against the configured competition hierarchy.

Strict mode fails when any named hierarchy competition has zero historical
matches. Catch-all buckets are reported but are not required.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.historical_competitions import ALL_COMPETITIONS  # noqa: E402
from scripts.build_historical_warehouse import DEFAULT_DB, Warehouse  # noqa: E402

CATCH_ALL_KEYS = {"other_euro_topflight", "intl_other"}
REQUIRED_HIERARCHY_KEYS = tuple(
    competition.key
    for competition in ALL_COMPETITIONS
    if competition.key not in CATCH_ALL_KEYS
)


def _count(warehouse: Warehouse, query: str, params: tuple[Any, ...]) -> int:
    return int(warehouse.conn.execute(query, params).fetchone()[0])


def competition_coverage(
    warehouse: Warehouse,
    competition_key: str,
    *,
    recent_since: str | None = None,
) -> dict[str, Any]:
    comp = warehouse.conn.execute(
        """SELECT competition_key,display_name,scope,hierarchy_rank,hierarchy_tier
           FROM warehouse_competitions WHERE competition_key=?""",
        (competition_key,),
    ).fetchone()
    if not comp:
        raise KeyError(f"Unknown hierarchy competition {competition_key}")

    base_params = (competition_key,)
    summary = warehouse.conn.execute(
        """SELECT
               COUNT(*) AS matches,
               MIN(match_date) AS oldest_match,
               MAX(match_date) AS newest_match,
               SUM(CASE WHEN home_score_ft IS NOT NULL AND away_score_ft IS NOT NULL THEN 1 ELSE 0 END) AS with_ft,
               SUM(CASE WHEN home_score_ht IS NOT NULL AND away_score_ht IS NOT NULL THEN 1 ELSE 0 END) AS with_ht,
               SUM(CASE WHEN referee IS NOT NULL AND TRIM(referee)<>'' THEN 1 ELSE 0 END) AS with_referee,
               SUM(CASE WHEN home_coach IS NOT NULL AND away_coach IS NOT NULL THEN 1 ELSE 0 END) AS with_both_coaches
           FROM warehouse_matches WHERE competition_key=?""",
        base_params,
    ).fetchone()

    result: dict[str, Any] = {
        "competition_key": comp["competition_key"],
        "competition_name": comp["display_name"],
        "scope": comp["scope"],
        "hierarchy_rank": comp["hierarchy_rank"],
        "hierarchy_tier": comp["hierarchy_tier"],
        "required": competition_key in REQUIRED_HIERARCHY_KEYS,
        "matches": int(summary["matches"] or 0),
        "oldest_match": summary["oldest_match"],
        "newest_match": summary["newest_match"],
        "with_ft": int(summary["with_ft"] or 0),
        "with_ht": int(summary["with_ht"] or 0),
        "with_referee": int(summary["with_referee"] or 0),
        "with_both_coaches": int(summary["with_both_coaches"] or 0),
        "with_events": _count(
            warehouse,
            """SELECT COUNT(DISTINCT e.match_key)
               FROM warehouse_events e
               JOIN warehouse_matches m ON m.match_key=e.match_key
               WHERE m.competition_key=?""",
            base_params,
        ),
        "with_goal_events": _count(
            warehouse,
            """SELECT COUNT(DISTINCT e.match_key)
               FROM warehouse_events e
               JOIN warehouse_matches m ON m.match_key=e.match_key
               WHERE m.competition_key=? AND e.event_type='goal'""",
            base_params,
        ),
        "with_card_events": _count(
            warehouse,
            """SELECT COUNT(DISTINCT e.match_key)
               FROM warehouse_events e
               JOIN warehouse_matches m ON m.match_key=e.match_key
               WHERE m.competition_key=? AND e.event_type='card'""",
            base_params,
        ),
        "with_lineups": _count(
            warehouse,
            """SELECT COUNT(DISTINCT l.match_key)
               FROM warehouse_lineups l
               JOIN warehouse_matches m ON m.match_key=l.match_key
               WHERE m.competition_key=?""",
            base_params,
        ),
        "source_count": _count(
            warehouse,
            """SELECT COUNT(DISTINCT s.source_key)
               FROM warehouse_match_sources s
               JOIN warehouse_matches m ON m.match_key=s.match_key
               WHERE m.competition_key=?""",
            base_params,
        ),
    }

    if recent_since:
        result["matches_since"] = recent_since
        result["recent_matches"] = _count(
            warehouse,
            """SELECT COUNT(*) FROM warehouse_matches
               WHERE competition_key=? AND match_date>=?""",
            (competition_key, recent_since),
        )
    return result


def audit_hierarchy(
    warehouse: Warehouse,
    *,
    recent_since: str | None = None,
) -> dict[str, Any]:
    rows = [
        competition_coverage(
            warehouse,
            competition.key,
            recent_since=recent_since,
        )
        for competition in sorted(
            ALL_COMPETITIONS,
            key=lambda item: (item.scope, item.rank, item.key),
        )
    ]
    missing = [
        row["competition_key"]
        for row in rows
        if row["required"] and row["matches"] == 0
    ]
    stale = []
    if recent_since:
        stale = [
            row["competition_key"]
            for row in rows
            if row["required"] and row["matches"] > 0 and row.get("recent_matches", 0) == 0
        ]

    return {
        "required_competitions": len(REQUIRED_HIERARCHY_KEYS),
        "covered_required_competitions": len(REQUIRED_HIERARCHY_KEYS) - len(missing),
        "missing_required_competitions": missing,
        "stale_required_competitions": stale,
        "complete": not missing,
        "competitions": rows,
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--recent-since",
        help="Also report hierarchy competitions with no matches on/after YYYY-MM-DD.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    warehouse = Warehouse(args.db)
    warehouse.initialize()
    try:
        report = audit_hierarchy(warehouse, recent_since=args.recent_since)
        rendered = json.dumps(report, indent=2, sort_keys=True)
        print(rendered)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        if args.strict and not report["complete"]:
            return 2
        return 0
    finally:
        warehouse.close()


if __name__ == "__main__":
    raise SystemExit(main())
