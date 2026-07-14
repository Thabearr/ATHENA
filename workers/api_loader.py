import logging
from datetime import date, timedelta

from config.settings import settings
from config.supported_leagues import SUPPORTED_LEAGUES, season_for_league
from api.football_api import FootballProvider
from database.database import Database

logger = logging.getLogger("athena.api_loader")


class LiveAPILoader:
    """
    Pulls REAL upcoming fixtures from API-Football for every league in
    SUPPORTED_LEAGUES. No fabricated data: if the API key is missing or a
    league request fails, that league is skipped and logged — never
    silently replaced with invented matches.
    """

    def __init__(self, days_ahead: int = 7):
        self.days_ahead = days_ahead
        self.db = Database()
        self.provider = FootballProvider(settings.FOOTBALL_API_KEY) if settings.FOOTBALL_API_KEY else None

    def fetch_upcoming_fixtures(self) -> list:
        if not self.provider:
            logger.error("FOOTBALL_API_KEY is not set — cannot fetch real fixtures.")
            return []

        date_from = date.today().strftime("%Y-%m-%d")
        date_to = (date.today() + timedelta(days=self.days_ahead)).strftime("%Y-%m-%d")

        all_fixtures = []
        for league_id in SUPPORTED_LEAGUES:
            season = season_for_league(league_id, settings)
            try:
                response = self.provider.get_fixtures_by_league(
                    league_id=league_id,
                    season=season,
                    date_from=date_from,
                    date_to=date_to,
                )
            except Exception as e:
                logger.error(f"Failed to fetch fixtures for league {league_id}: {e}")
                continue

            for item in response:
                try:
                    fixture = item["fixture"]
                    league = item["league"]
                    teams = item["teams"]

                    all_fixtures.append({
                        "fixture_id": fixture["id"],
                        "league": league.get("name", str(league_id)),
                        "season": league.get("season", season),
                        "home_team": teams["home"]["name"],
                        "away_team": teams["away"]["name"],
                        "home_team_id": teams["home"]["id"],
                        "away_team_id": teams["away"]["id"],
                        "match_date": fixture.get("date", ""),
                        "status": fixture.get("status", {}).get("short", "NS"),
                    })
                except Exception as e:
                    logger.error(f"Malformed fixture payload skipped: {e}")
                    continue

        return all_fixtures

    def sync_fixtures_to_db(self, raw_fixtures: list = None) -> bool:
        if not raw_fixtures:
            logger.warning("No real fixtures to sync — database left untouched.")
            return False

        try:
            with self.db.connect() as conn:
                cursor = conn.cursor()
                for fx in raw_fixtures:
                    cursor.execute(
                        """
                        INSERT INTO fixtures (fixture_id, league, season, home_team, away_team, match_date, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(fixture_id) DO UPDATE SET
                            league=excluded.league,
                            season=excluded.season,
                            home_team=excluded.home_team,
                            away_team=excluded.away_team,
                            match_date=excluded.match_date,
                            status=excluded.status
                        """,
                        (fx["fixture_id"], fx["league"], fx["season"], fx["home_team"],
                         fx["away_team"], fx["match_date"], fx["status"]),
                    )

                    # Keep the teams table in sync with real API team IDs so
                    # AnalysisPipeline._resolve_team_id finds real IDs by name
                    # instead of falling back to a meaningless hash.
                    for side in ("home", "away"):
                        team_id = fx.get(f"{side}_team_id")
                        team_name = fx.get(f"{side}_team")
                        if team_id and team_name:
                            cursor.execute(
                                """
                                INSERT INTO teams (team_id, name, league)
                                VALUES (?, ?, ?)
                                ON CONFLICT(team_id) DO UPDATE SET name=excluded.name
                                """,
                                (team_id, team_name, fx["league"]),
                            )
                conn.commit()
            logger.info(f"Synced {len(raw_fixtures)} real fixtures to the database.")
            return True
        except Exception as e:
            logger.error(f"Failed to sync fixtures to DB: {e}")
            return False
