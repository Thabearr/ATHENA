#!/usr/bin/env python3
"""Build Athena's historical football warehouse from open historical sources.

The canonical store is SQLite. CSVs are exports, not the source of truth.
Missing historical facts remain NULL and every merge is source-priority aware.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.historical_competitions import (  # noqa: E402
    ALL_COMPETITIONS,
    FOOTBALL_DATA_CODES,
    SOURCES,
    competition_by_key,
    resolve_competition,
)

DEFAULT_DB = ROOT / "database" / "athena_history.db"
DEFAULT_CACHE = ROOT / ".cache" / "athena-history"
SCHEMA = ROOT / "database" / "historical_warehouse_schema.sql"
MATCH_FIELDS = (
    "competition_key", "competition_name", "scope", "season", "stage", "round_name",
    "match_date", "kickoff_time", "home_team", "away_team", "home_score_ft", "away_score_ft",
    "home_score_ht", "away_score_ht", "home_score_et", "away_score_et", "home_score_pen",
    "away_score_pen", "result", "venue", "city", "country", "neutral", "attendance", "referee",
    "home_coach", "away_coach", "home_xg", "away_xg", "home_possession", "away_possession",
    "home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target", "home_corners",
    "away_corners", "home_fouls", "away_fouls", "home_yellows", "away_yellows", "home_reds",
    "away_reds", "extra_json",
)


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def integer(value: Any) -> int | None:
    value = clean(value)
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def number(value: Any) -> float | None:
    value = clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def boolint(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return 1 if str(value).strip().casefold() in {"1", "true", "yes", "y"} else 0


def outcome(home: int | None, away: int | None) -> str | None:
    if home is None or away is None:
        return None
    return "H" if home > away else "A" if away > home else "D"


def norm_team(name: str) -> str:
    text = " ".join(str(name).casefold().replace("&", "and").split())
    for suffix in (" fc", " afc", " cf"):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
    return text


def digest(*parts: Any, size: int = 32) -> str:
    raw = "|".join("" if x is None else str(x).strip() for x in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:size]


def match_key(row: dict[str, Any]) -> str:
    return "m_" + digest(
        row.get("scope"), row.get("competition_key"), row.get("match_date"),
        norm_team(row.get("home_team") or ""), norm_team(row.get("away_team") or ""),
    )


def player_name(row: dict[str, Any]) -> str | None:
    given, family = clean(row.get("given_name")), clean(row.get("family_name"))
    return " ".join(part for part in (given, family) if part) or clean(row.get("player"))


def csv_rows(text: str) -> Iterator[dict[str, str]]:
    yield from csv.DictReader(io.StringIO(text.lstrip("\ufeff")))


class Downloader:
    def __init__(self, cache: Path, refresh: bool = False):
        self.cache, self.refresh = Path(cache), refresh
        self.cache.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "ATHENA historical football warehouse/1.0"

    def text(self, url: str, cache_name: str) -> str:
        path = self.cache / cache_name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not self.refresh:
            return path.read_text(encoding="utf-8-sig", errors="replace")
        response = self.session.get(url, timeout=90)
        response.raise_for_status()
        path.write_bytes(response.content)
        return response.content.decode("utf-8-sig", errors="replace")


class Warehouse:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")

    def close(self) -> None:
        self.conn.commit(); self.conn.close()

    def initialize(self) -> None:
        self.conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        for source in SOURCES:
            self.conn.execute(
                """INSERT INTO warehouse_sources(source_key,display_name,homepage,license_name,attribution,
                   redistributable,source_priority,notes) VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(source_key) DO UPDATE SET display_name=excluded.display_name,homepage=excluded.homepage,
                   license_name=excluded.license_name,attribution=excluded.attribution,redistributable=excluded.redistributable,
                   source_priority=excluded.source_priority,notes=excluded.notes""",
                (source.key, source.name, source.homepage, source.license_name, source.attribution,
                 int(source.redistributable), source.priority, source.notes),
            )
        for comp in ALL_COMPETITIONS:
            self.conn.execute(
                """INSERT INTO warehouse_competitions(competition_key,display_name,scope,country,confederation,
                   competition_type,hierarchy_rank,hierarchy_tier,aliases_json) VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(competition_key) DO UPDATE SET display_name=excluded.display_name,scope=excluded.scope,
                   country=excluded.country,confederation=excluded.confederation,competition_type=excluded.competition_type,
                   hierarchy_rank=excluded.hierarchy_rank,hierarchy_tier=excluded.hierarchy_tier,aliases_json=excluded.aliases_json""",
                (comp.key, comp.name, comp.scope, comp.country, comp.confederation, comp.competition_type,
                 comp.rank, comp.tier, json.dumps(comp.aliases, ensure_ascii=False)),
            )
        self.conn.execute("INSERT OR REPLACE INTO warehouse_meta(key,value) VALUES('schema_version','1')")
        self.conn.commit()

    def priority(self, source: str) -> int:
        row = self.conn.execute("SELECT source_priority FROM warehouse_sources WHERE source_key=?", (source,)).fetchone()
        if not row:
            raise KeyError(f"Unknown source {source}")
        return int(row[0])

    def source_match(self, source: str, source_id: str | None) -> str | None:
        if not source_id:
            return None
        row = self.conn.execute(
            "SELECT match_key FROM warehouse_match_sources WHERE source_key=? AND source_match_id=? LIMIT 1",
            (source, str(source_id)),
        ).fetchone()
        return row[0] if row else None

    def upsert_match(self, row: dict[str, Any], *, source: str | None = None, source_id: str | None = None,
                     source_url: str | None = None, coverage: dict[str, int] | None = None,
                     source_key: str | None = None, source_match_id: str | None = None) -> str:
        source = source or source_key
        source_id = source_id or source_match_id
        if not source:
            raise ValueError("source/source_key is required")
        key = self.source_match(source, source_id) or match_key(row)
        incoming_priority = self.priority(source)
        existing = self.conn.execute("SELECT * FROM warehouse_matches WHERE match_key=?", (key,)).fetchone()
        if not existing:
            values = {field: row.get(field) for field in MATCH_FIELDS}
            values["extra_json"] = values.get("extra_json") or "{}"
            cols = ["match_key", *MATCH_FIELDS]
            self.conn.execute(
                f"INSERT INTO warehouse_matches({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",
                [key, *[values[c] for c in MATCH_FIELDS]],
            )
            for field, value in values.items():
                if value not in (None, ""):
                    self.conn.execute(
                        "INSERT OR REPLACE INTO warehouse_field_provenance(match_key,field_name,source_key,source_priority) VALUES(?,?,?,?)",
                        (key, field, source, incoming_priority),
                    )
        else:
            for field in MATCH_FIELDS:
                incoming = row.get(field)
                if incoming in (None, ""):
                    continue
                current = existing[field]
                prov = self.conn.execute(
                    "SELECT source_key,source_priority FROM warehouse_field_provenance WHERE match_key=? AND field_name=?",
                    (key, field),
                ).fetchone()
                current_priority = int(prov["source_priority"]) if prov else 999
                if current in (None, "") or incoming_priority < current_priority:
                    if current not in (None, "") and str(current) != str(incoming):
                        self._conflict(key, field, current, incoming, prov["source_key"] if prov else None, source)
                    self.conn.execute(f"UPDATE warehouse_matches SET {field}=?,updated_at=? WHERE match_key=?", (incoming, now(), key))
                    self.conn.execute(
                        "INSERT OR REPLACE INTO warehouse_field_provenance(match_key,field_name,source_key,source_priority) VALUES(?,?,?,?)",
                        (key, field, source, incoming_priority),
                    )
                elif str(current) != str(incoming):
                    self._conflict(key, field, current, incoming, prov["source_key"] if prov else None, source)
        cov = {k: int(v) for k, v in (coverage or {}).items()}
        self.conn.execute(
            """INSERT OR IGNORE INTO warehouse_match_sources(match_key,source_key,source_match_id,source_url,
               has_ft,has_ht,has_events,has_cards,has_lineups,has_coaches,has_officials,has_advanced_stats)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (key, source, source_id, source_url, cov.get("has_ft",0), cov.get("has_ht",0),
             cov.get("has_events",0), cov.get("has_cards",0), cov.get("has_lineups",0), cov.get("has_coaches",0),
             cov.get("has_officials",0), cov.get("has_advanced_stats",0)),
        )
        self.conn.commit()
        return key

    def _conflict(self, key: str, field: str, old: Any, new: Any, old_source: str | None, new_source: str) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO warehouse_conflicts(match_key,field_name,existing_value,incoming_value,
               existing_source,incoming_source) VALUES(?,?,?,?,?,?)""",
            (key, field, str(old), str(new), old_source, new_source),
        )

    def event(self, key: str, source: str, source_event_id: str | None, event_type: str, **data: Any) -> None:
        event_key = f"e_{digest(source, source_event_id or '', key, event_type, data.get('minute'), data.get('player'), data.get('team'))}"
        self.conn.execute(
            """INSERT OR REPLACE INTO warehouse_events(event_key,match_key,source_key,source_event_id,event_type,event_subtype,
               team,player,assist,minute,stoppage_minute,second,period,outcome,card_type,is_penalty,is_own_goal,xg,details_json,source_url)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (event_key,key,source,source_event_id,event_type,data.get("event_subtype"),data.get("team"),data.get("player"),
             data.get("assist"),data.get("minute"),data.get("stoppage_minute"),data.get("second"),data.get("period"),
             data.get("outcome"),data.get("card_type"),int(bool(data.get("is_penalty"))),int(bool(data.get("is_own_goal"))),
             data.get("xg"),json.dumps(data.get("details") or {},ensure_ascii=False),data.get("source_url")),
        )

    def coach(self, key: str, source: str, team: str, name: str, coach_id: str | None = None, nationality: str | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO warehouse_coaches(coach_key,match_key,source_key,team,coach_name,coach_id,nationality) VALUES(?,?,?,?,?,?,?)",
            ("c_"+digest(source,key,team,name),key,source,team,name,coach_id,nationality),
        )
        match = self.conn.execute("SELECT home_team,away_team FROM warehouse_matches WHERE match_key=?",(key,)).fetchone()
        if match:
            field = "home_coach" if norm_team(team)==norm_team(match["home_team"]) else "away_coach" if norm_team(team)==norm_team(match["away_team"]) else None
            if field:
                self.conn.execute(f"UPDATE warehouse_matches SET {field}=COALESCE({field},?) WHERE match_key=?",(name,key))

    def official(self, key: str, source: str, name: str, official_id: str | None = None, nationality: str | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO warehouse_officials(official_key,match_key,source_key,official_name,official_id,nationality) VALUES(?,?,?,?,?,?)",
            ("o_"+digest(source,key,name),key,source,name,official_id,nationality),
        )
        self.conn.execute("UPDATE warehouse_matches SET referee=COALESCE(referee,?) WHERE match_key=?",(name,key))

    def refresh_quality(self) -> None:
        for row in self.conn.execute("SELECT match_key,home_score_ft,away_score_ft,home_score_ht,away_score_ht,referee,home_coach,away_coach FROM warehouse_matches"):
            events = self.conn.execute("SELECT COUNT(*) FROM warehouse_events WHERE match_key=?",(row["match_key"],)).fetchone()[0]
            ft = row["home_score_ft"] is not None and row["away_score_ft"] is not None
            ht = row["home_score_ht"] is not None and row["away_score_ht"] is not None
            rich = ft and ht and events and row["referee"] and row["home_coach"] and row["away_coach"]
            quality = "RICH" if rich else "STANDARD" if ft and (ht or events) else "BASIC" if ft else "PARTIAL"
            self.conn.execute("UPDATE warehouse_matches SET data_quality=? WHERE match_key=?",(quality,row["match_key"]))
        self.conn.commit()

    def export(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for name, query in {
            "matches":"SELECT * FROM warehouse_match_flat ORDER BY match_date,match_key",
            "events":"SELECT * FROM warehouse_events ORDER BY match_key,minute,event_key",
            "lineups":"SELECT * FROM warehouse_lineups ORDER BY match_key,team,player",
            "coaches":"SELECT * FROM warehouse_coaches ORDER BY match_key,team",
            "officials":"SELECT * FROM warehouse_officials ORDER BY match_key,role",
            "sources":"SELECT * FROM warehouse_match_sources ORDER BY match_key,source_key",
            "conflicts":"SELECT * FROM warehouse_conflicts ORDER BY observed_at,id",
        }.items():
            cur = self.conn.execute(query)
            with (directory/f"{name}.csv").open("w",newline="",encoding="utf-8") as fh:
                writer = csv.writer(fh); writer.writerow([d[0] for d in cur.description]); writer.writerows(cur)

    def audit(self) -> dict[str,int]:
        scalar = lambda q: int(self.conn.execute(q).fetchone()[0])
        return {
            "matches":scalar("SELECT COUNT(*) FROM warehouse_matches"),
            "events":scalar("SELECT COUNT(*) FROM warehouse_events"),
            "coaches":scalar("SELECT COUNT(*) FROM warehouse_coaches"),
            "officials":scalar("SELECT COUNT(*) FROM warehouse_officials"),
            "with_ht":scalar("SELECT COUNT(*) FROM warehouse_matches WHERE home_score_ht IS NOT NULL AND away_score_ht IS NOT NULL"),
            "with_cards":scalar("SELECT COUNT(DISTINCT match_key) FROM warehouse_events WHERE event_type='card'"),
            "rich":scalar("SELECT COUNT(*) FROM warehouse_matches WHERE data_quality='RICH'"),
            "conflicts":scalar("SELECT COUNT(*) FROM warehouse_conflicts"),
        }


def import_martj42(wh: Warehouse, dl: Downloader) -> None:
    base = "https://raw.githubusercontent.com/martj42/international_results/master"
    results = list(csv_rows(dl.text(f"{base}/results.csv","martj42/results.csv")))
    by_identity: dict[tuple[str,str,str],str] = {}
    for r in results:
        tournament = clean(r.get("tournament")) or "Other Senior International"
        comp = resolve_competition(tournament,"international")
        date, home, away = r["date"], r["home_team"], r["away_team"]
        row = {"competition_key":comp.key,"competition_name":tournament,"scope":"international","season":date[:4],
               "match_date":date,"home_team":home,"away_team":away,"home_score_ft":integer(r.get("home_score")),
               "away_score_ft":integer(r.get("away_score")),"neutral":boolint(r.get("neutral")),"city":clean(r.get("city")),
               "country":clean(r.get("country"))}
        row["result"] = outcome(row["home_score_ft"],row["away_score_ft"])
        key=wh.upsert_match(row,source="martj42_international",source_id=digest(date,home,away),source_url=f"{base}/results.csv",coverage={"has_ft":1})
        by_identity[(date,home,away)] = key
    scorer_rows = list(csv_rows(dl.text(f"{base}/goalscorers.csv","martj42/goalscorers.csv")))
    per_match: dict[str,list[dict[str,str]]] = {}
    for r in scorer_rows:
        key=by_identity.get((r.get("date",""),r.get("home_team",""),r.get("away_team","")))
        if not key: continue
        per_match.setdefault(key,[]).append(r)
        wh.event(key,"martj42_international",digest(*r.values()),"goal",team=clean(r.get("team")),player=clean(r.get("scorer")),
                 minute=integer(r.get("minute")),is_own_goal=boolint(r.get("own_goal")),is_penalty=boolint(r.get("penalty")),source_url=f"{base}/goalscorers.csv")
    for key, events in per_match.items():
        m=wh.conn.execute("SELECT home_team,away_team,home_score_ft,away_score_ft FROM warehouse_matches WHERE match_key=?",(key,)).fetchone()
        if not m or m["home_score_ft"] is None: continue
        if len(events) != m["home_score_ft"] + m["away_score_ft"]: continue
        hh=ah=0
        for e in events:
            minute=integer(e.get("minute"))
            if minute is None or minute>45: continue
            team=clean(e.get("team")); own=boolint(e.get("own_goal"))==1
            if norm_team(team or "")==norm_team(m["home_team"]): hh += 0 if own else 1; ah += 1 if own else 0
            elif norm_team(team or "")==norm_team(m["away_team"]): ah += 0 if own else 1; hh += 1 if own else 0
        wh.conn.execute("UPDATE warehouse_matches SET home_score_ht=COALESCE(home_score_ht,?),away_score_ht=COALESCE(away_score_ht,?) WHERE match_key=?",(hh,ah,key))
    for r in csv_rows(dl.text(f"{base}/shootouts.csv","martj42/shootouts.csv")):
        key=by_identity.get((r.get("date",""),r.get("home_team",""),r.get("away_team","")))
        if key:
            wh.conn.execute("INSERT OR REPLACE INTO warehouse_penalty_shootouts(shootout_key,match_key,source_key,winner,first_shooter,details_json) VALUES(?,?,?,?,?,?)",
                            ("p_"+digest(key,"martj42"),key,"martj42_international",clean(r.get("winner")),clean(r.get("first_shooter")),json.dumps(r)))
    wh.conn.commit()


def import_worldcup(wh: Warehouse, dl: Downloader) -> None:
    base="https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv"
    match_url=f"{base}/matches.csv"
    match_ids: dict[str,str] = {}
    for r in csv_rows(dl.text(match_url,"fjelstul/matches.csv")):
        if "FIFA Men's World Cup" not in (r.get("tournament_name") or ""): continue
        date=r["match_date"]
        row={"competition_key":"intl_world_cup","competition_name":"FIFA World Cup","scope":"international","season":date[:4],
             "stage":clean(r.get("stage_name")),"round_name":clean(r.get("group_name")),"match_date":date,"kickoff_time":clean(r.get("match_time")),
             "home_team":r["home_team_name"],"away_team":r["away_team_name"],"home_score_ft":integer(r.get("home_team_score")),
             "away_score_ft":integer(r.get("away_team_score")),"home_score_pen":integer(r.get("home_team_score_penalties")),
             "away_score_pen":integer(r.get("away_team_score_penalties")),"venue":clean(r.get("stadium_name")),"city":clean(r.get("city_name")),
             "country":clean(r.get("country_name"))}
        row["result"]=outcome(row["home_score_ft"],row["away_score_ft"])
        key=wh.upsert_match(row,source="fjelstul_worldcup",source_id=r["match_id"],source_url=match_url,coverage={"has_ft":1,"has_events":1,"has_cards":1,"has_coaches":1,"has_officials":1})
        match_ids[r["match_id"]]=key
    goal_url=f"{base}/goals.csv"; goal_map: dict[str,list[dict[str,str]]]={}
    for r in csv_rows(dl.text(goal_url,"fjelstul/goals.csv")):
        key=match_ids.get(r.get("match_id",""))
        if not key: continue
        goal_map.setdefault(key,[]).append(r)
        wh.event(key,"fjelstul_worldcup",r.get("goal_id"),"goal",team=clean(r.get("team_name")),player=player_name(r),minute=integer(r.get("minute_regulation")),
                 stoppage_minute=integer(r.get("minute_stoppage")),period=clean(r.get("match_period")),is_own_goal=boolint(r.get("own_goal")),
                 is_penalty=boolint(r.get("penalty")),source_url=goal_url)
    for key, goals in goal_map.items():
        m=wh.conn.execute("SELECT home_team,away_team FROM warehouse_matches WHERE match_key=?",(key,)).fetchone(); hh=ah=0
        for g in goals:
            period=(g.get("match_period") or "").casefold()
            if "first half" not in period: continue
            team=g.get("team_name") or ""; own=boolint(g.get("own_goal"))==1
            if norm_team(team)==norm_team(m["home_team"]): hh += 0 if own else 1; ah += 1 if own else 0
            elif norm_team(team)==norm_team(m["away_team"]): ah += 0 if own else 1; hh += 1 if own else 0
        wh.conn.execute("UPDATE warehouse_matches SET home_score_ht=COALESCE(home_score_ht,?),away_score_ht=COALESCE(away_score_ht,?) WHERE match_key=?",(hh,ah,key))
    booking_url=f"{base}/bookings.csv"; card_totals: dict[str,list[int]]={}
    for r in csv_rows(dl.text(booking_url,"fjelstul/bookings.csv")):
        key=match_ids.get(r.get("match_id",""))
        if not key: continue
        card="red" if boolint(r.get("red_card")) or boolint(r.get("second_yellow_card")) else "yellow"
        wh.event(key,"fjelstul_worldcup",r.get("booking_id"),"card",team=clean(r.get("team_name")),player=player_name(r),minute=integer(r.get("minute_regulation")),
                 stoppage_minute=integer(r.get("minute_stoppage")),period=clean(r.get("match_period")),card_type=card,source_url=booking_url)
        m=wh.conn.execute("SELECT home_team,away_team FROM warehouse_matches WHERE match_key=?",(key,)).fetchone()
        vals=card_totals.setdefault(key,[0,0,0,0]); home=norm_team(r.get("team_name") or "")==norm_team(m["home_team"])
        idx=(0 if card=="yellow" else 2)+(0 if home else 1); vals[idx]+=1
    for key,(hy,ay,hr,ar) in card_totals.items():
        wh.conn.execute("UPDATE warehouse_matches SET home_yellows=?,away_yellows=?,home_reds=?,away_reds=? WHERE match_key=?",(hy,ay,hr,ar,key))
    manager_url=f"{base}/manager_appearances.csv"
    for r in csv_rows(dl.text(manager_url,"fjelstul/manager_appearances.csv")):
        key=match_ids.get(r.get("match_id","")); name=player_name(r)
        if key and name: wh.coach(key,"fjelstul_worldcup",r["team_name"],name,r.get("manager_id"),clean(r.get("country_name")))
    referee_url=f"{base}/referee_appearances.csv"
    for r in csv_rows(dl.text(referee_url,"fjelstul/referee_appearances.csv")):
        key=match_ids.get(r.get("match_id","")); name=player_name(r)
        if key and name: wh.official(key,"fjelstul_worldcup",name,r.get("referee_id"),clean(r.get("country_name")))
    wh.conn.commit()


FD_DATE_FORMATS=("%d/%m/%Y","%d/%m/%y","%Y-%m-%d")
def fd_date(value:str) -> str | None:
    for fmt in FD_DATE_FORMATS:
        try: return datetime.strptime(value.strip(),fmt).date().isoformat()
        except ValueError: pass
    return None


def import_football_data(wh:Warehouse, dl:Downloader, start:int, end:int, codes:Iterable[str]) -> None:
    for year in range(start,end+1):
        season=f"{year}-{str((year+1)%100).zfill(2)}"; archive=f"{year%100:02d}{(year+1)%100:02d}"
        for code in codes:
            comp_key=FOOTBALL_DATA_CODES.get(code)
            if not comp_key: continue
            comp=competition_by_key(comp_key); url=f"https://www.football-data.co.uk/mmz4281/{archive}/{code}.csv"
            try: rows=csv_rows(dl.text(url,f"football-data/{archive}_{code}.csv"))
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code in {404,410}: continue
                raise
            for r in rows:
                date=fd_date(r.get("Date") or "")
                if not date or not r.get("HomeTeam") or not r.get("AwayTeam"): continue
                row={"competition_key":comp.key,"competition_name":comp.name,"scope":"club","season":season,"match_date":date,
                     "kickoff_time":clean(r.get("Time")),"home_team":r["HomeTeam"],"away_team":r["AwayTeam"],"home_score_ft":integer(r.get("FTHG")),
                     "away_score_ft":integer(r.get("FTAG")),"home_score_ht":integer(r.get("HTHG")),"away_score_ht":integer(r.get("HTAG")),
                     "referee":clean(r.get("Referee")),"home_shots":integer(r.get("HS")),"away_shots":integer(r.get("AS")),
                     "home_shots_on_target":integer(r.get("HST")),"away_shots_on_target":integer(r.get("AST")),"home_fouls":integer(r.get("HF")),
                     "away_fouls":integer(r.get("AF")),"home_corners":integer(r.get("HC")),"away_corners":integer(r.get("AC")),
                     "home_yellows":integer(r.get("HY")),"away_yellows":integer(r.get("AY")),"home_reds":integer(r.get("HR")),"away_reds":integer(r.get("AR"))}
                row["result"]=outcome(row["home_score_ft"],row["away_score_ft"])
                known={"Div","Date","Time","HomeTeam","AwayTeam","FTHG","FTAG","FTR","HTHG","HTAG","HTR","Referee","HS","AS","HST","AST","HF","AF","HC","AC","HY","AY","HR","AR"}
                row["extra_json"]=json.dumps({k:v for k,v in r.items() if k not in known and v not in (None,"")},ensure_ascii=False)
                wh.upsert_match(row,source="football_data_uk",source_id=digest(code,date,r["HomeTeam"],r["AwayTeam"]),source_url=url,
                                coverage={"has_ft":1,"has_ht":int(row["home_score_ht"] is not None),"has_cards":int(row["home_yellows"] is not None),"has_officials":int(bool(row["referee"])),"has_advanced_stats":int(row["home_shots"] is not None)})


OF_REPOS=("champions-league","england","espana","italy","deutschland","france","europe")
OF_MATCH=re.compile(r"^(?:(\d{1,2}:\d{2})\s+)?(.+?)\s+v\s+(.+?)\s+(\d+)-(\d+)(?:\s+\((\d+)-(\d+)\))?\s*$")
OF_DATE=re.compile(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})(?:\s+(\d{4}))?$")

def of_comp(title:str):
    t=title.casefold()
    if "champions league" in t or "european cup" in t:return competition_by_key("uefa_ucl")
    if "europa league" in t or "uefa cup" in t:return competition_by_key("uefa_uel")
    if "conference league" in t:return competition_by_key("uefa_uecl")
    for c in ALL_COMPETITIONS:
        if c.scope=="club" and any(a.casefold() in t for a in (c.name,*c.aliases) if len(a)>5): return c
    return None

def parse_openfootball_text(text:str, source_path:str) -> Iterator[dict[str,Any]]:
    title=None; comp=None; season=None; stage=None; current_date=None; year_hint=None
    for raw in text.splitlines():
        line=raw.strip()
        if line.startswith("="):
            title=line.lstrip("= "); comp=of_comp(title); sm=re.search(r"(\d{4})[/\-](\d{2,4})",title)
            season=f"{sm.group(1)}-{sm.group(2)[-2:]}" if sm else None; year_hint=int(sm.group(1)) if sm else None; continue
        if line.startswith("▪"):
            stage=line.lstrip("▪ "); continue
        dm=OF_DATE.match(line)
        if dm:
            year=int(dm.group(3)) if dm.group(3) else year_hint
            if year:
                current_date=datetime.strptime(f"{dm.group(1)} {dm.group(2)} {year}","%b %d %Y").date().isoformat()
            continue
        mm=OF_MATCH.match(line)
        if not (mm and comp and current_date): continue
        home=re.sub(r"\s+\([A-Z]{3}\)$","",mm.group(2)).strip(); away=re.sub(r"\s+\([A-Z]{3}\)$","",mm.group(3)).strip()
        row={"competition_key":comp.key,"competition_name":comp.name,"scope":"club","season":season,"stage":stage,"match_date":current_date,
             "kickoff_time":mm.group(1),"home_team":home,"away_team":away,"home_score_ft":int(mm.group(4)),"away_score_ft":int(mm.group(5)),
             "home_score_ht":integer(mm.group(6)),"away_score_ht":integer(mm.group(7)),"source_path":source_path}
        row["result"]=outcome(row["home_score_ft"],row["away_score_ft"]); yield row


def import_openfootball(wh:Warehouse, dl:Downloader) -> None:
    import zipfile
    for repo in OF_REPOS:
        url=f"https://github.com/openfootball/{repo}/archive/refs/heads/master.zip"
        path=dl.cache/f"openfootball/{repo}.zip"; path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists() or dl.refresh:
            resp=dl.session.get(url,timeout=120); resp.raise_for_status(); path.write_bytes(resp.content)
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if not name.endswith((".txt",".csv")): continue
                try:text=zf.read(name).decode("utf-8",errors="replace")
                except Exception:continue
                for row in parse_openfootball_text(text,name):
                    wh.upsert_match(row,source="openfootball",source_id=digest(name,row["match_date"],row["home_team"],row["away_team"]),source_url=url,
                                    coverage={"has_ft":1,"has_ht":int(row["home_score_ht"] is not None)})


def arguments() -> argparse.Namespace:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",type=Path,default=DEFAULT_DB); p.add_argument("--cache",type=Path,default=DEFAULT_CACHE); p.add_argument("--refresh",action="store_true")
    p.add_argument("--all",action="store_true"); p.add_argument("--martj42",action="store_true"); p.add_argument("--worldcup",action="store_true")
    p.add_argument("--football-data",action="store_true"); p.add_argument("--openfootball",action="store_true"); p.add_argument("--start-year",type=int,default=1993)
    p.add_argument("--end-year",type=int,default=datetime.now().year); p.add_argument("--leagues",nargs="*",default=list(FOOTBALL_DATA_CODES))
    p.add_argument("--export-csv",type=Path); p.add_argument("--audit",action="store_true")
    return p.parse_args()


def main() -> int:
    args=arguments(); wh=Warehouse(args.db); wh.initialize(); dl=Downloader(args.cache,args.refresh)
    try:
        if args.all or args.martj42: import_martj42(wh,dl)
        if args.all or args.worldcup: import_worldcup(wh,dl)
        if args.all or args.football_data: import_football_data(wh,dl,args.start_year,args.end_year,args.leagues)
        if args.all or args.openfootball: import_openfootball(wh,dl)
        wh.refresh_quality()
        if args.export_csv: wh.export(args.export_csv)
        if args.audit or not any((args.all,args.martj42,args.worldcup,args.football_data,args.openfootball)):
            print(json.dumps({"database":str(args.db),"audit":wh.audit()},indent=2,sort_keys=True))
        return 0
    finally: wh.close()


if __name__=="__main__": raise SystemExit(main())
