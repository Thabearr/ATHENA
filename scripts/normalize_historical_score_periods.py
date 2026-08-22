#!/usr/bin/env python3
"""Normalize historical score-period semantics in Athena's history warehouse.

Some public result sources publish the score after extra time as their
"full-time" result. Athena treats `*_score_ft` as the 90-minute regulation
score, `*_score_et` as the score after extra time, and `*_score_pen` as the
shootout score. This pass moves known ET scores out of FT and reconstructs
regulation scores only when event evidence is complete enough to do so safely.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_historical_warehouse import DEFAULT_DB, Warehouse, norm_team  # noqa: E402


def goal_side(match, event) -> int | None:
    team = event["team"] or ""
    own_goal = bool(event["is_own_goal"])
    if norm_team(team) == norm_team(match["home_team"]):
        return 1 if own_goal else 0
    if norm_team(team) == norm_team(match["away_team"]):
        return 0 if own_goal else 1
    return None


def regulation_from_goal_events(warehouse: Warehouse, match_key: str) -> tuple[int, int, bool] | None:
    match = warehouse.conn.execute(
        "SELECT * FROM warehouse_matches WHERE match_key=?", (match_key,)
    ).fetchone()
    events = warehouse.conn.execute(
        """SELECT team,minute,period,is_own_goal FROM warehouse_events
           WHERE match_key=? AND event_type='goal' ORDER BY minute,event_key""",
        (match_key,),
    ).fetchall()
    if not events:
        return None

    current_total = None
    if match["home_score_ft"] is not None and match["away_score_ft"] is not None:
        current_total = int(match["home_score_ft"]) + int(match["away_score_ft"])
    elif match["home_score_et"] is not None and match["away_score_et"] is not None:
        current_total = int(match["home_score_et"]) + int(match["away_score_et"])

    # If the goal ledger does not reconcile to the published final score, it
    # is not complete enough to reconstruct regulation time safely.
    if current_total is None or len(events) != current_total:
        return None

    home = away = 0
    has_extra_time = False
    for event in events:
        minute = event["minute"]
        period = (event["period"] or "").casefold()
        is_extra = "extra" in period or (minute is not None and int(minute) > 90)
        if is_extra:
            has_extra_time = True
            continue
        # A missing minute is acceptable for Fjelstul events when the period
        # explicitly says first/second half. It is not acceptable otherwise.
        if minute is None and not ("first half" in period or "second half" in period):
            return None
        side = goal_side(match, event)
        if side == 0:
            home += 1
        elif side == 1:
            away += 1
        else:
            return None
    return home, away, has_extra_time


def source_matches(warehouse: Warehouse, source: str):
    return warehouse.conn.execute(
        """SELECT DISTINCT m.* FROM warehouse_matches m
           JOIN warehouse_match_sources s ON s.match_key=m.match_key
           WHERE s.source_key=?""",
        (source,),
    ).fetchall()


def set_score_provenance(warehouse: Warehouse, match_key: str, field: str, source: str) -> None:
    priority = warehouse.priority(source)
    warehouse.conn.execute(
        """INSERT OR REPLACE INTO warehouse_field_provenance
           (match_key,field_name,source_key,source_priority,updated_at)
           VALUES(?,?,?,?,CURRENT_TIMESTAMP)""",
        (match_key, field, source, priority),
    )


def global_period_code(match) -> str | None:
    try:
        details = json.loads(match["extra_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    code = details.get("schochastics_full_time_code")
    return str(code).strip().upper() if code is not None else None


def normalize_world_cup(warehouse: Warehouse) -> dict[str, int]:
    corrected = unresolved = 0
    for match in source_matches(warehouse, "fjelstul_worldcup"):
        reconstructed = regulation_from_goal_events(warehouse, match["match_key"])
        has_shootout = bool((match["home_score_pen"] or 0) + (match["away_score_pen"] or 0))
        if reconstructed is None:
            # A shootout proves that the source's published match score is the
            # post-extra-time score. Do not expose it as a 90-minute score if
            # event evidence cannot reconstruct regulation.
            if has_shootout and match["home_score_ft"] is not None:
                warehouse.conn.execute(
                    """UPDATE warehouse_matches SET home_score_et=home_score_ft,away_score_et=away_score_ft,
                       home_score_ft=NULL,away_score_ft=NULL,result=NULL,updated_at=CURRENT_TIMESTAMP
                       WHERE match_key=?""",
                    (match["match_key"],),
                )
                unresolved += 1
            continue
        reg_home, reg_away, event_has_extra = reconstructed
        final_home, final_away = match["home_score_ft"], match["away_score_ft"]
        if event_has_extra or has_shootout:
            warehouse.conn.execute(
                """UPDATE warehouse_matches SET home_score_et=?,away_score_et=?,home_score_ft=?,away_score_ft=?,
                   result=CASE WHEN ?>? THEN 'H' WHEN ?<? THEN 'A' ELSE 'D' END,updated_at=CURRENT_TIMESTAMP
                   WHERE match_key=?""",
                (final_home, final_away, reg_home, reg_away, reg_home, reg_away, reg_home, reg_away, match["match_key"]),
            )
            for field in ("home_score_ft", "away_score_ft", "home_score_et", "away_score_et", "result"):
                set_score_provenance(warehouse, match["match_key"], field, "fjelstul_worldcup")
            corrected += 1
    return {"corrected": corrected, "unresolved": unresolved}


def normalize_martj42(warehouse: Warehouse) -> dict[str, int]:
    corrected = unresolved = 0
    shootout_keys = {
        row[0]
        for row in warehouse.conn.execute(
            "SELECT DISTINCT match_key FROM warehouse_penalty_shootouts WHERE source_key='martj42_international'"
        )
    }
    for match in source_matches(warehouse, "martj42_international"):
        events = warehouse.conn.execute(
            "SELECT minute FROM warehouse_events WHERE match_key=? AND source_key='martj42_international' AND event_type='goal'",
            (match["match_key"],),
        ).fetchall()
        has_late_goal = any(e["minute"] is not None and int(e["minute"]) > 90 for e in events)
        cross_source_code = global_period_code(match)
        known_et = has_late_goal or match["match_key"] in shootout_keys or cross_source_code in {"E", "P"}
        if not known_et:
            continue
        final_home, final_away = match["home_score_ft"], match["away_score_ft"]
        reconstructed = regulation_from_goal_events(warehouse, match["match_key"])
        if reconstructed is not None:
            reg_home, reg_away, _ = reconstructed
            warehouse.conn.execute(
                """UPDATE warehouse_matches SET home_score_et=?,away_score_et=?,home_score_ft=?,away_score_ft=?,
                   result=CASE WHEN ?>? THEN 'H' WHEN ?<? THEN 'A' ELSE 'D' END,updated_at=CURRENT_TIMESTAMP
                   WHERE match_key=?""",
                (final_home, final_away, reg_home, reg_away, reg_home, reg_away, reg_home, reg_away, match["match_key"]),
            )
            for field in ("home_score_ft", "away_score_ft", "home_score_et", "away_score_et", "result"):
                set_score_provenance(warehouse, match["match_key"], field, "martj42_international")
            corrected += 1
        elif final_home is not None and final_away is not None:
            warehouse.conn.execute(
                """UPDATE warehouse_matches SET home_score_et=?,away_score_et=?,home_score_ft=NULL,away_score_ft=NULL,
                   result=NULL,updated_at=CURRENT_TIMESTAMP WHERE match_key=?""",
                (final_home, final_away, match["match_key"]),
            )
            set_score_provenance(warehouse, match["match_key"], "home_score_et", "martj42_international")
            set_score_provenance(warehouse, match["match_key"], "away_score_et", "martj42_international")
            unresolved += 1
    return {"corrected": corrected, "unresolved": unresolved}


def refresh_source_coverage(warehouse: Warehouse) -> None:
    warehouse.conn.execute(
        """UPDATE warehouse_match_sources
           SET has_events=CASE WHEN EXISTS(
                 SELECT 1 FROM warehouse_events e
                 WHERE e.match_key=warehouse_match_sources.match_key
                   AND e.source_key=warehouse_match_sources.source_key
               ) THEN 1 ELSE has_events END,
               has_ht=CASE WHEN EXISTS(
                 SELECT 1 FROM warehouse_matches m
                 WHERE m.match_key=warehouse_match_sources.match_key
                   AND m.home_score_ht IS NOT NULL AND m.away_score_ht IS NOT NULL
               ) THEN 1 ELSE has_ht END"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    warehouse = Warehouse(args.db)
    warehouse.initialize()
    try:
        report = {
            "fjelstul_worldcup": normalize_world_cup(warehouse),
            "martj42_international": normalize_martj42(warehouse),
        }
        refresh_source_coverage(warehouse)
        warehouse.refresh_quality()
        warehouse.conn.commit()
        print(json.dumps({"database": str(args.db), "score_period_normalization": report, "audit": warehouse.audit()}, indent=2, sort_keys=True))
        return 0
    finally:
        warehouse.close()


if __name__ == "__main__":
    raise SystemExit(main())
