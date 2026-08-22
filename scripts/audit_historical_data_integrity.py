#!/usr/bin/env python3
"""Audit cross-source integrity invariants in Athena's historical warehouse.

This is intentionally stricter than SQLite foreign-key integrity. It detects
logical duplicate fixtures caused by source naming/orientation differences and
verifies that incident-bearing events use Athena's canonical goal/card types.

A single historical source can legitimately contain two distinct records for
the same team pair on the same coarse/uncertain date (especially in old data).
Those groups are reported as same-source ambiguities, but they are not treated
as cross-source identity collisions when every record carries the same source
set. Unknown-provenance groups remain fatal.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_historical_hierarchy_coverage import REQUIRED_HIERARCHY_KEYS  # noqa: E402
from scripts.build_historical_warehouse import DEFAULT_DB, Warehouse  # noqa: E402
from scripts.enrich_schochastics_goal_events import team_identity  # noqa: E402


def _count(warehouse: Warehouse, sql: str, params: tuple[Any, ...] = ()) -> int:
    return int(warehouse.conn.execute(sql, params).fetchone()[0])


def _source_sets_for_matches(
    warehouse: Warehouse,
    match_keys: list[str],
    *,
    chunk_size: int = 500,
) -> dict[str, set[str]]:
    source_sets: dict[str, set[str]] = defaultdict(set)
    for offset in range(0, len(match_keys), chunk_size):
        chunk = match_keys[offset : offset + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        rows = warehouse.conn.execute(
            f"""SELECT match_key,source_key FROM warehouse_match_sources
                WHERE match_key IN ({placeholders})""",
            chunk,
        )
        for row in rows:
            source_sets[row["match_key"]].add(row["source_key"])
    return source_sets


def logical_duplicate_fixtures(warehouse: Warehouse, *, sample_limit: int = 25) -> dict[str, Any]:
    placeholders = ",".join("?" for _ in REQUIRED_HIERARCHY_KEYS)
    rows = warehouse.conn.execute(
        f"""SELECT match_key,competition_key,match_date,home_team,away_team
            FROM warehouse_matches
            WHERE competition_key IN ({placeholders})
            ORDER BY competition_key,match_date,match_key""",
        REQUIRED_HIERARCHY_KEYS,
    )

    first_seen: dict[tuple[str, str, str, str], dict[str, str]] = {}
    candidate_groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        home = team_identity(row["home_team"])
        away = team_identity(row["away_team"])
        if not home or not away:
            continue
        first_team, second_team = sorted((home, away))
        identity = (row["competition_key"], row["match_date"], first_team, second_team)
        record = {
            "match_key": row["match_key"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "orientation": f"{home} -> {away}",
        }
        prior = first_seen.get(identity)
        if prior is None:
            first_seen[identity] = record
            continue
        if not candidate_groups[identity]:
            candidate_groups[identity].append(prior)
        candidate_groups[identity].append(record)

    candidate_match_keys = [
        match["match_key"]
        for matches in candidate_groups.values()
        for match in matches
    ]
    source_sets = _source_sets_for_matches(warehouse, candidate_match_keys)

    duplicate_groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    same_source_ambiguous_groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    for identity, matches in candidate_groups.items():
        per_match_sources = [frozenset(source_sets.get(match["match_key"], set())) for match in matches]
        # No provenance means we cannot safely explain the collision, so preserve
        # the original strict behavior for legacy/manual rows.
        if any(not sources for sources in per_match_sources) or len(set(per_match_sources)) > 1:
            duplicate_groups[identity] = matches
        else:
            # Every row is independently supported by the exact same provider
            # set. This is usually coarse/uncertain historical dating rather
            # than a cross-source identity collision, so report but do not merge.
            same_source_ambiguous_groups[identity] = matches

    def render_examples(
        groups: dict[tuple[str, str, str, str], list[dict[str, str]]]
    ) -> list[dict[str, Any]]:
        examples = []
        for identity, matches in list(groups.items())[:sample_limit]:
            competition_key, match_date, first_team, second_team = identity
            rendered_matches = []
            for match in matches:
                rendered_matches.append(
                    {
                        **match,
                        "sources": sorted(source_sets.get(match["match_key"], set())),
                    }
                )
            examples.append(
                {
                    "competition_key": competition_key,
                    "match_date": match_date,
                    "team_pair": [first_team, second_team],
                    "matches": rendered_matches,
                }
            )
        return examples

    return {
        "duplicate_groups": len(duplicate_groups),
        "duplicate_rows": sum(len(matches) - 1 for matches in duplicate_groups.values()),
        "examples": render_examples(duplicate_groups),
        "same_source_ambiguous_groups": len(same_source_ambiguous_groups),
        "same_source_ambiguous_rows": sum(
            len(matches) - 1 for matches in same_source_ambiguous_groups.values()
        ),
        "same_source_ambiguous_examples": render_examples(same_source_ambiguous_groups),
    }


def audit_integrity(warehouse: Warehouse) -> dict[str, Any]:
    sqlite_integrity = str(warehouse.conn.execute("PRAGMA integrity_check").fetchone()[0])
    duplicates = logical_duplicate_fixtures(warehouse)
    noncanonical_cards = _count(
        warehouse,
        """SELECT COUNT(*) FROM warehouse_events
           WHERE card_type IS NOT NULL AND TRIM(card_type)<>'' AND event_type<>'card'""",
    )
    noncanonical_own_goals = _count(
        warehouse,
        """SELECT COUNT(*) FROM warehouse_events
           WHERE is_own_goal=1 AND event_type<>'goal'""",
    )
    noncanonical_goal_outcomes = _count(
        warehouse,
        """SELECT COUNT(*) FROM warehouse_events
           WHERE LOWER(COALESCE(outcome,''))='goal' AND event_type<>'goal'""",
    )
    report = {
        "sqlite_integrity": sqlite_integrity,
        "logical_duplicate_fixtures": duplicates,
        "noncanonical_card_events": noncanonical_cards,
        "noncanonical_own_goal_events": noncanonical_own_goals,
        "noncanonical_goal_outcome_events": noncanonical_goal_outcomes,
    }
    report["complete"] = (
        sqlite_integrity == "ok"
        and duplicates["duplicate_groups"] == 0
        and noncanonical_cards == 0
        and noncanonical_own_goals == 0
        and noncanonical_goal_outcomes == 0
    )
    return report


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    warehouse = Warehouse(args.db)
    warehouse.initialize()
    try:
        report = audit_integrity(warehouse)
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
