"""
FotMob Advanced Scraper - Zero API Key Required
Extracts comprehensive match intelligence from FotMob's internal Next.js endpoints.
Includes: fixtures, lineups, injuries, form, weather, odds, referee data.

Uses FotmobBypassClient for TLS fingerprint spoofing to bypass Cloudflare.
"""

import logging
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

from database.database import Database
from workers.fotmob_bypass_client import FotmobBypassClient

logger = logging.getLogger("athena.fotmob_advanced_scraper")


class FotMobAdvancedScraper:
    """
    Industrial-grade FotMob scraper using the bypass client.
    No authentication or paid API keys required.
    """

    def __init__(self):
        self.db = Database()
        self.client = FotmobBypassClient()
        logger.info("FotMob Advanced Scraper initialized with bypass client.")

    def _parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """Parse datetime string from FotMob (always returns UTC-aware)."""
        if not dt_str:
            return None
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            try:
                dt = datetime.fromisoformat(dt_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, TypeError):
                logger.warning(f"Could not parse datetime: {dt_str}")
                return None

    def fetch_upcoming_matches(self, days_ahead: int = 3) -> List[Dict]:
        """
        Fetch all upcoming matches within N days using the bypass client.
        Returns enriched fixture data with lineups, injuries, odds, weather, etc.
        """
        logger.info(f"Fetching FotMob matches for next {days_ahead} days...")

        all_matches = []
        now_utc = datetime.now(timezone.utc)

        for day_offset in range(days_ahead):
            target_date = now_utc + timedelta(days=day_offset)
            date_str = target_date.strftime("%Y%m%d")

            data = self.client.fetch_matches_by_date(date_str)
            if not data:
                logger.warning(f"No data returned for date {date_str}")
                continue

            leagues = data.get("leagues", [])
            logger.info(f"  [{date_str}] Found {len(leagues)} leagues")

            for league in leagues:
                league_name = league.get("name", "Unknown")
                matches = league.get("matches", [])

                for match in matches:
                    try:
                        match_date_str = (
                            match.get("status", {}).get("utcTime", "")
                        )
                        match_date = self._parse_datetime(match_date_str)

                        if not match_date:
                            continue

                        # Skip already-started/finished matches
                        status_info = match.get("status", {})
                        if status_info.get("finished", False):
                            continue

                        fixture_id = match.get("id")
                        home = match.get("home", {})
                        away = match.get("away", {})
                        home_team = home.get("longName") or home.get("name", "Unknown")
                        away_team = away.get("longName") or away.get("name", "Unknown")

                        if not all([fixture_id, home_team, away_team]):
                            continue

                        # Build enriched fixture object
                        enriched = {
                            "fixture_id": fixture_id,
                            "league": league_name,
                            "league_id": league.get("id"),
                            "home_team": home_team,
                            "home_id": home.get("id"),
                            "away_team": away_team,
                            "away_id": away.get("id"),
                            "match_date": match_date_str,
                            "status": "NS" if not status_info.get("started") else "LIVE",
                            "data_source": "fotmob_bypass",
                            "season_label": str(now_utc.year),
                            "tournament_stage": match.get("tournamentStage"),
                        }

                        all_matches.append(enriched)

                    except Exception as e:
                        logger.warning(
                            f"Error processing match {match.get('id')}: {e}"
                        )
                        continue

        logger.info(f"Fetched {len(all_matches)} upcoming fixtures from FotMob")
        return all_matches

    def enrich_match(self, fixture_id: int) -> Dict:
        """
        Fetch deep match details: lineups, injuries, weather, referee, h2h.
        Call this for high-priority matches only (rate-limit friendly).
        """
        details = {}
        match_info = self.client.fetch_match_details(fixture_id)
        if not match_info:
            return details

        try:
            content = match_info.get("content", {})
            header = match_info.get("header", {})
            general = match_info.get("general", {})

            # === LINEUPS ===
            lineup_data = content.get("lineup", {})
            if isinstance(lineup_data, dict):
                details["home_lineup"] = self._extract_lineup(
                    lineup_data.get("homeTeam", lineup_data.get("lineup", [{}])[:1])
                )
                details["away_lineup"] = self._extract_lineup(
                    lineup_data.get("awayTeam", lineup_data.get("lineup", [{}])[1:2])
                )

            # === WEATHER ===
            weather = content.get("weather", {})
            if weather:
                details["weather"] = {
                    "temperature": weather.get("temperature"),
                    "condition": weather.get("shortPhrase", weather.get("condition", "Unknown")),
                    "wind_speed": weather.get("windSpeed"),
                }

            # === MATCH FACTS ===
            facts = content.get("matchFacts", {})
            if facts:
                # Referee
                referee_info = facts.get("infoBox", {})
                if isinstance(referee_info, dict):
                    ref = referee_info.get("Referee", {})
                    if isinstance(ref, dict):
                        details["referee"] = ref.get("text", "Unknown")
                    elif isinstance(ref, str):
                        details["referee"] = ref

                # Head-to-head
                h2h = facts.get("h2h", {})
                if h2h:
                    summary = h2h.get("summary", [])
                    if isinstance(summary, list) and len(summary) >= 3:
                        details["head_to_head"] = {
                            "home_wins": summary[0],
                            "draws": summary[1],
                            "away_wins": summary[2],
                        }

                # Injuries / suspensions
                injuries = facts.get("injuries", {})
                if injuries:
                    details["home_injuries"] = self._extract_injuries(
                        injuries.get("homeTeam", [])
                    )
                    details["away_injuries"] = self._extract_injuries(
                        injuries.get("awayTeam", [])
                    )

                # Team form
                team_form = facts.get("teamForm", [])
                if isinstance(team_form, list) and len(team_form) >= 2:
                    details["home_form"] = self._extract_form(team_form[0])
                    details["away_form"] = self._extract_form(team_form[1])

            # === MATCH STATS (xG, Possession) ===
            stats_block = content.get("stats", {})
            if stats_block:
                periods = stats_block.get("Periods", {})
                all_stats = periods.get("All", {}).get("stats", [])
                for stat_category in all_stats:
                    stats_array = stat_category.get("stats", [])
                    for stat_item in stats_array:
                        title = stat_item.get("title", "")
                        if title == "Expected goals (xG)":
                            vals = stat_item.get("stats", [None, None])
                            if vals and len(vals) >= 2 and vals[0] is not None and vals[1] is not None:
                                try:
                                    details["home_xg"] = float(vals[0])
                                    details["away_xg"] = float(vals[1])
                                except (ValueError, TypeError):
                                    pass
                        elif title == "Ball possession":
                            vals = stat_item.get("stats", [None, None])
                            if vals and len(vals) >= 2 and vals[0] is not None and vals[1] is not None:
                                try:
                                    details["home_possession"] = int(str(vals[0]).replace('%', ''))
                                    details["away_possession"] = int(str(vals[1]).replace('%', ''))
                                except (ValueError, TypeError):
                                    pass

        except Exception as e:
            logger.warning(f"Error enriching match {fixture_id}: {e}")

        return details

    def _extract_lineup(self, lineup_data) -> List[Dict]:
        """Extract player list from lineup data."""
        players = []
        if not lineup_data:
            return players

        # Handle different lineup formats
        if isinstance(lineup_data, dict):
            starters = lineup_data.get("starters", lineup_data.get("players", []))
            for p in starters:
                if isinstance(p, dict):
                    players.append({
                        "name": p.get("name", p.get("shortName", "")),
                        "number": p.get("shirt", p.get("number")),
                        "position": p.get("positionStringShort", p.get("position", "")),
                        "status": "starting",
                    })
            bench = lineup_data.get("bench", [])
            for p in bench:
                if isinstance(p, dict):
                    players.append({
                        "name": p.get("name", p.get("shortName", "")),
                        "number": p.get("shirt", p.get("number")),
                        "position": p.get("positionStringShort", p.get("position", "")),
                        "status": "bench",
                    })

        return players

    def _extract_injuries(self, injury_list) -> List[Dict]:
        """Extract injury information."""
        injuries = []
        if not isinstance(injury_list, list):
            return injuries

        for p in injury_list:
            if isinstance(p, dict):
                injuries.append({
                    "name": p.get("name", p.get("playerName", "")),
                    "reason": p.get("injuryType", p.get("reason", "Unknown")),
                    "return_date": p.get("expectedReturn"),
                })
        return injuries

    def _extract_form(self, form_data) -> Dict:
        """Extract recent form from team form data."""
        if not form_data:
            return {"matches": [], "summary": ""}

        if isinstance(form_data, dict):
            form_list = form_data.get("recentResults", form_data.get("form", []))
        elif isinstance(form_data, list):
            form_list = form_data
        else:
            return {"matches": [], "summary": ""}

        recent = []
        for m in form_list[:5]:
            if isinstance(m, dict):
                recent.append({
                    "result": m.get("resultString", m.get("result", "")),
                    "opponent": m.get("against", m.get("opponent", "")),
                })

        summary = "".join(
            m.get("result", "")[:1].upper() for m in recent
        )
        return {"matches": recent, "summary": summary}

    def sync_to_db(self, matches: List[Dict]) -> bool:
        """Persist enriched fixtures to the database."""
        if not matches:
            logger.warning("No matches to sync")
            return False

        try:
            with self.db.connect() as conn:
                cursor = conn.cursor()

                # Ensure extended tables exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS fixture_extended (
                        fixture_id INTEGER PRIMARY KEY,
                        home_lineup TEXT,
                        away_lineup TEXT,
                        home_injuries TEXT,
                        away_injuries TEXT,
                        live_odds TEXT,
                        weather TEXT,
                        referee TEXT,
                        head_to_head TEXT,
                        head_to_head TEXT,
                        home_form TEXT,
                        away_form TEXT,
                        home_xg REAL,
                        away_xg REAL,
                        home_possession INTEGER,
                        away_possession INTEGER,
                        synced_at TEXT
                    )
                """)

                for match in matches:
                    fixture_id = match.get("fixture_id")

                    # Main fixtures table
                    cursor.execute("""
                        INSERT INTO fixtures
                            (fixture_id, league, season, home_team, away_team,
                             match_date, status, data_source, season_label)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(fixture_id) DO UPDATE SET
                            league=excluded.league,
                            status=excluded.status,
                            match_date=excluded.match_date,
                            data_source=excluded.data_source
                    """, (
                        fixture_id, match.get("league"), match.get("season_label"),
                        match.get("home_team"), match.get("away_team"),
                        match.get("match_date"), match.get("status"),
                        match.get("data_source"), match.get("season_label"),
                    ))

                    # Extended metadata (if enriched)
                    if any(k in match for k in ["home_lineup", "weather", "referee"]):
                        cursor.execute("""
                            INSERT INTO fixture_extended
                                (fixture_id, home_lineup, away_lineup, home_injuries,
                                 away_injuries, live_odds, weather, referee, 
                                 head_to_head, home_form, away_form, home_xg, away_xg, 
                                 home_possession, away_possession, synced_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(fixture_id) DO UPDATE SET
                                home_lineup=excluded.home_lineup,
                                away_lineup=excluded.away_lineup,
                                home_injuries=excluded.home_injuries,
                                away_injuries=excluded.away_injuries,
                                live_odds=excluded.live_odds,
                                weather=excluded.weather,
                                referee=excluded.referee,
                                head_to_head=excluded.head_to_head,
                                home_form=excluded.home_form,
                                away_form=excluded.away_form,
                                home_xg=excluded.home_xg,
                                away_xg=excluded.away_xg,
                                home_possession=excluded.home_possession,
                                away_possession=excluded.away_possession,
                                synced_at=excluded.synced_at
                        """, (
                            fixture_id,
                            json.dumps(match.get("home_lineup", [])),
                            json.dumps(match.get("away_lineup", [])),
                            json.dumps(match.get("home_injuries", [])),
                            json.dumps(match.get("away_injuries", [])),
                            json.dumps(match.get("live_odds", {})),
                            json.dumps(match.get("weather", {})),
                            match.get("referee", "Unknown"),
                            json.dumps(match.get("head_to_head", {})),
                            json.dumps(match.get("home_form", {})),
                            json.dumps(match.get("away_form", {})),
                            match.get("home_xg"),
                            match.get("away_xg"),
                            match.get("home_possession"),
                            match.get("away_possession"),
                            datetime.now(timezone.utc).isoformat(),
                        ))

                conn.commit()
                logger.info(f"Synced {len(matches)} enriched fixtures to DB")
                return True

        except Exception as e:
            logger.error(f"Failed to sync fixtures: {e}")
            return False


def main():
    """CLI: Fetch and sync FotMob data."""
    logging.basicConfig(level=logging.INFO)
    scraper = FotMobAdvancedScraper()

    # Fetch next 3 days
    matches = scraper.fetch_upcoming_matches(days_ahead=3)

    if matches:
        # Enrich the first 5 matches with deep data
        for match in matches[:5]:
            fid = match["fixture_id"]
            details = scraper.enrich_match(fid)
            match.update(details)
            print(
                f"  {match['home_team']} vs {match['away_team']} "
                f"[{match['league']}] "
                f"Injuries: H={len(match.get('home_injuries', []))} "
                f"A={len(match.get('away_injuries', []))}"
            )

        scraper.sync_to_db(matches)
        print(f"\nSynced {len(matches)} FotMob fixtures with full enrichment")
    else:
        print("No matches fetched from FotMob")


if __name__ == "__main__":
    main()
