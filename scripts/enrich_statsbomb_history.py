#!/usr/bin/env python3
"""Enrich Athena history with StatsBomb Open Data events, lineups and xG.

Only male, non-youth competitions that map to Athena's hierarchy are imported.
StatsBomb coverage is selective; this script enriches those matches rather than
pretending the source covers every historical competition/season.
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

from domain.historical_competitions import resolve_competition  # noqa: E402
from scripts.build_historical_warehouse import (  # noqa: E402
    DEFAULT_CACHE, DEFAULT_DB, Downloader, Warehouse, clean, digest, norm_team, outcome,
)

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"


def get(obj: dict[str, Any], *path: str, default=None):
    cur: Any = obj
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def competition_for(record: dict[str, Any]):
    if record.get("competition_gender") != "male" or record.get("competition_youth"):
        return None
    scope = "international" if record.get("competition_international") else "club"
    comp = resolve_competition(record.get("competition_name") or "", scope)
    if scope == "club" and comp.key == "other_club_competition":
        return None
    return comp


def goal_side(event: dict[str, Any], home: str, away: str) -> str | None:
    event_type = get(event, "type", "name", default="")
    team = get(event, "team", "name", default="")
    if event_type == "Shot" and get(event, "shot", "outcome", "name") == "Goal":
        return "home" if norm_team(team) == norm_team(home) else "away" if norm_team(team) == norm_team(away) else None
    if event_type == "Own Goal Against":
        return "away" if norm_team(team) == norm_team(home) else "home" if norm_team(team) == norm_team(away) else None
    if event_type == "Own Goal For":
        return "home" if norm_team(team) == norm_team(home) else "away" if norm_team(team) == norm_team(away) else None
    return None


def event_card(event: dict[str, Any]) -> str | None:
    name = get(event, "bad_behaviour", "card", "name") or get(event, "foul_committed", "card", "name")
    return clean(name)


def canonical_event_type(event: dict[str, Any], home: str, away: str) -> str:
    """Map provider event names onto Athena's canonical incident types.

    StatsBomb represents a goal as a successful ``Shot`` (or an own-goal event)
    and cards as attributes of ``Bad Behaviour``/``Foul Committed``. Athena's
    cross-source event queries expect those incidents under ``goal`` and
    ``card`` respectively, while non-incident provider event types remain
    available in their normalized raw form and in ``details_json``.
    """
    if goal_side(event, home, away) is not None:
        return "goal"
    if event_card(event):
        return "card"
    return get(event, "type", "name", default="Unknown").casefold().replace(" ", "_")


def import_lineups(wh: Warehouse, dl: Downloader, match_key: str, match_id: int) -> int:
    url = f"{BASE}/lineups/{match_id}.json"
    try:
        teams = json.loads(dl.text(url, f"statsbomb/lineups/{match_id}.json"))
    except Exception:
        return 0
    inserted = 0
    for team in teams:
        team_name = team.get("team_name") or ""
        for player in team.get("lineup") or []:
            positions = player.get("positions") or []
            starter = 1 if any((p.get("start_reason") or "").casefold() == "starting xi" for p in positions) else 0
            position = clean(positions[0].get("position")) if positions else None
            wh.conn.execute(
                """INSERT OR REPLACE INTO warehouse_lineups(lineup_key,match_key,source_key,team,player,player_id,
                   shirt_number,position,starter,captain,minutes_played,details_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "l_" + digest("statsbomb", match_id, team_name, player.get("player_id")), match_key, "statsbomb_open",
                    team_name, player.get("player_name") or player.get("player_nickname") or "Unknown",
                    str(player.get("player_id")) if player.get("player_id") is not None else None,
                    player.get("jersey_number"), position, starter, 0, None,
                    json.dumps({"country": get(player, "country", "name"), "positions": positions, "cards": player.get("cards") or []}, ensure_ascii=False),
                ),
            )
            inserted += 1
    return inserted


def import_match_events(wh: Warehouse, dl: Downloader, match_key: str, match: dict[str, Any]) -> dict[str, Any]:
    match_id = int(match["match_id"])
    url = f"{BASE}/events/{match_id}.json"
    events = json.loads(dl.text(url, f"statsbomb/events/{match_id}.json"))
    home, away = get(match, "home_team", "home_team_name"), get(match, "away_team", "away_team_name")
    goals = defaultdict(lambda: [0, 0])
    xg = [0.0, 0.0]
    yellows = [0, 0]
    reds = [0, 0]

    for event in events:
        event_type = get(event, "type", "name", default="Unknown")
        team = get(event, "team", "name")
        player = get(event, "player", "name")
        period = int(event.get("period") or 0)
        side = 0 if norm_team(team or "") == norm_team(home or "") else 1 if norm_team(team or "") == norm_team(away or "") else None
        shot_xg = get(event, "shot", "statsbomb_xg")
        if event_type == "Shot" and side is not None and shot_xg is not None:
            xg[side] += float(shot_xg)
        scoring_side = goal_side(event, home or "", away or "")
        if scoring_side:
            goals[period][0 if scoring_side == "home" else 1] += 1
        card = event_card(event)
        if card and side is not None:
            if "Red" in card or "Second Yellow" in card:
                reds[side] += 1
            elif "Yellow" in card:
                yellows[side] += 1
        substitution = get(event, "substitution", "replacement", "name")
        details = {
            "type": event_type, "possession": event.get("possession"), "position": get(event, "position", "name"),
            "location": event.get("location"), "play_pattern": get(event, "play_pattern", "name"),
            "shot": event.get("shot") if event_type == "Shot" else None,
            "pass": event.get("pass") if event_type == "Pass" and (get(event, "pass", "goal_assist") or get(event, "pass", "shot_assist")) else None,
            "replacement": substitution,
        }
        wh.event(
            match_key, "statsbomb_open", str(event.get("id")), canonical_event_type(event, home or "", away or ""),
            event_subtype=get(event, "shot", "type", "name") or get(event, "pass", "type", "name"),
            team=team, player=player, minute=event.get("minute"), second=event.get("second"), period=str(period),
            outcome=get(event, "shot", "outcome", "name") or get(event, "pass", "outcome", "name"), card_type=card,
            is_penalty=get(event, "shot", "type", "name") == "Penalty", is_own_goal=event_type.startswith("Own Goal"),
            xg=shot_xg, details=details, source_url=url,
        )

    regulation = [sum(goals[p][i] for p in (1, 2)) for i in (0, 1)]
    extra = [regulation[i] + sum(goals[p][i] for p in (3, 4)) for i in (0, 1)]
    shootout = [goals[5][0], goals[5][1]]
    return {
        "home_score_ft": regulation[0], "away_score_ft": regulation[1], "result": outcome(*regulation),
        "home_score_et": extra[0] if any(goals[p] != [0, 0] for p in (3, 4)) else None,
        "away_score_et": extra[1] if any(goals[p] != [0, 0] for p in (3, 4)) else None,
        "home_score_pen": shootout[0] if sum(shootout) else None, "away_score_pen": shootout[1] if sum(shootout) else None,
        "home_xg": round(xg[0], 5), "away_xg": round(xg[1], 5),
        "home_yellows": yellows[0], "away_yellows": yellows[1], "home_reds": reds[0], "away_reds": reds[1],
        "event_count": len(events),
    }


def import_statsbomb(wh: Warehouse, dl: Downloader) -> dict[str, int]:
    competitions = json.loads(dl.text(f"{BASE}/competitions.json", "statsbomb/competitions.json"))
    counts = {"competition_seasons": 0, "matches": 0, "events": 0, "lineups": 0}
    for record in competitions:
        comp = competition_for(record)
        if not comp:
            continue
        counts["competition_seasons"] += 1
        cid, sid = record["competition_id"], record["season_id"]
        matches_url = f"{BASE}/matches/{cid}/{sid}.json"
        try:
            matches = json.loads(dl.text(matches_url, f"statsbomb/matches/{cid}_{sid}.json"))
        except Exception:
            continue
        for match in matches:
            home = get(match, "home_team", "home_team_name")
            away = get(match, "away_team", "away_team_name")
            if not home or not away:
                continue
            row = {
                "competition_key": comp.key, "competition_name": comp.name, "scope": comp.scope,
                "season": get(match, "season", "season_name") or record.get("season_name"),
                "stage": get(match, "competition_stage", "name"), "round_name": str(match.get("match_week") or "") or None,
                "match_date": match["match_date"], "kickoff_time": clean(match.get("kick_off")), "home_team": home, "away_team": away,
                "venue": get(match, "stadium", "name"), "country": get(match, "stadium", "country", "name"),
                "referee": get(match, "referee", "name"),
            }
            home_managers = get(match, "home_team", "managers", default=[]) or []
            away_managers = get(match, "away_team", "managers", default=[]) or []
            if home_managers: row["home_coach"] = home_managers[0].get("nickname") or home_managers[0].get("name")
            if away_managers: row["away_coach"] = away_managers[0].get("nickname") or away_managers[0].get("name")
            key = wh.upsert_match(row, source="statsbomb_open", source_id=str(match["match_id"]), source_url=matches_url,
                                  coverage={"has_coaches": int(bool(home_managers and away_managers)), "has_officials": int(bool(row["referee"]))})
            if row.get("home_coach"): wh.coach(key, "statsbomb_open", home, row["home_coach"], str(home_managers[0].get("id")), get(home_managers[0], "country", "name"))
            if row.get("away_coach"): wh.coach(key, "statsbomb_open", away, row["away_coach"], str(away_managers[0].get("id")), get(away_managers[0], "country", "name"))
            if row.get("referee"): wh.official(key, "statsbomb_open", row["referee"], str(get(match, "referee", "id") or ""), get(match, "referee", "country", "name"))
            try:
                enrichment = import_match_events(wh, dl, key, match)
                counts["events"] += enrichment.pop("event_count")
                wh.upsert_match({**row, **enrichment}, source="statsbomb_open", source_id=str(match["match_id"]), source_url=matches_url)
                wh.conn.execute("UPDATE warehouse_match_sources SET has_ft=1,has_events=1,has_cards=1,has_advanced_stats=1 WHERE match_key=? AND source_key='statsbomb_open'", (key,))
            except Exception:
                pass
            lineup_count = import_lineups(wh, dl, key, int(match["match_id"]))
            counts["lineups"] += lineup_count
            wh.conn.execute("UPDATE warehouse_match_sources SET has_lineups=CASE WHEN ? > 0 THEN 1 ELSE has_lineups END WHERE match_key=? AND source_key='statsbomb_open'", (lineup_count, key))
            counts["matches"] += 1
            wh.conn.commit()
    wh.refresh_quality()
    return counts


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--export-csv", type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments(); wh = Warehouse(args.db); wh.initialize(); dl = Downloader(args.cache, args.refresh)
    try:
        report = import_statsbomb(wh, dl)
        if args.export_csv: wh.export(args.export_csv)
        print(json.dumps({"database": str(args.db), "statsbomb": report, "audit": wh.audit()}, indent=2, sort_keys=True))
        return 0
    finally:
        wh.close()


if __name__ == "__main__":
    raise SystemExit(main())
