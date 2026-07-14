import logging
import time
from datetime import date, timedelta

from config.settings import settings
from config.supported_leagues import SUPPORTED_LEAGUES, season_for_league
from config.competition_mapping import FOOTBALL_DATA_ORG_MAPPING
from api.football_api import FootballProvider
from api.football_data_org_provider import FootballDataOrgProvider
from database.database import Database

logger = logging.getLogger("athena.api_loader")

# Offset added to football-data.org match/team IDs before storing, so they
# can never collide with API-Football's numeric IDs in the same tables.
FDO_ID_OFFSET = 10_000_000


class LiveAPILoader:
    """
    Pulls REAL upcoming fixtures from two sources:
      - football-data.org: current 2025-26 season, for competitions in
        FOOTBALL_DATA_ORG_MAPPING. Tagged data_source='football_data_org_live'.
      - API-Football: every other SUPPORTED_LEAGUES league. Free tier there
        is locked to 2022-2024, so these rows are tagged
        data_source='api_football_2022_2024' — never presented as current.

    No fabricated fallback data. A league that fails is skipped and logged.
    """

    def __init__(self, days_ahead: int = 7, request_delay_seconds: float = 1.0):
        self.days_ahead = days_ahead
        self.request_delay_seconds = request_delay_seconds
        self.db = Database()

        self.fdo_provider = (
            FootballDataOrgProvider(settings.FOOTBALL_DATA_ORG_API_KEY)
            if settings.FOOTBALL_DATA_ORG_API_KEY else None
        )
        self.af_provider = (
            FootballProvider(settings.FOOTBALL_API_KEY)
            if settings.FOOTBALL_API_KEY else None
        )

    def _fetch_from_football_data_org(self, date_from, date_to):
        fixtures = []
        if not self.fdo_provider:
            logger.warning("FOOTBALL_DATA_ORG_API_KEY not set — skipping football-data.org fixtures.")
            return fixtures

        for league_id, code in FOOTBALL_DATA_ORG_MAPPING.items():
            try:
                matches = self.fdo_provider.get_matches(
                    competition_code=code,
                    date_from=date_from,
                    date_to=date_to,
                    status="SCHEDULED",
                )
            except Exception as e:
                logger.error(f"football-data.org fetch failed for {code}: {e}")
                time.sleep(self.request_delay_seconds)
                continue

            for m in matches:
                try:
                    fixtures.append({
                        "fixture_id": FDO_ID_OFFSET + m["id"],
                        "league": m.get("competition", {}).get("name", code),
                        "season": (m.get("season", {}).get("startDate", "2025") or "2025")[:4],
                        "home_team": m["homeTeam"]["name"],
                        "away_team": m["awayTeam"]["name"],
                        "home_team_id": FDO_ID_OFFSET + m["homeTeam"]["id"],
                        "away_team_id": FDO_ID_OFFSET + m["awayTeam"]["id"],
                        "match_date": m.get("utcDate", ""),
                        "status": m.get("status", "SCHEDULED"),
                        "data_source": "football_data_org_live",
                        "season_label": "2025-26",
                    })
                except Exception as e:
                    logger.error(f"Malformed football-data.org match skipped: {e}")
                    continue

            time.sleep(self.request_delay_seconds)

        return fixtures

    def _fetch_from_api_football(self, date_from, date_to):
        fixtures = []
        if not self.af_provider:
            logger.warning("FOOTBALL_API_KEY not set — skipping API-Football fixtures.")
            return fixtures

        unmapped_leagues = [lid for lid in SUPPORTED_LEAGUES if lid not in FOOTBALL_DATA_ORG_MAPPING]

        for league_id in unmapped_leagues:
            season = season_for_league(league_id, settings)
            try:
                response = self.af_provider.get_fixtures_by_league(
                    league_id=league_id,
                    season=season,
                    date_from=date_from,
                    date_to=date_to,
                )
            except Exception as e:
                logger.error(f"API-Football fetch failed for league {league_id}: {e}")
                time.sleep(self.request_delay_seconds)
                continue

            for item in response:
                try:
                    fixture = item["fixture"]
                    league = item["league"]
                    teams = item["teams"]

                    fixtures.append({
                        "fixture_id": fixture["id"],
                        "league": league.get("name", str(league_id)),
                        "season": league.get("season", season),
                        "home_team": teams["home"]["name"],
                        "away_team": teams["away"]["name"],
                        "home_team_id": teams["home"]["id"],
                        "away_team_id": teams["away"]["id"],
                        "match_date": fixture.get("date", ""),
                        "status": fixture.get("status", {}).get("short", "NS"),
                        "data_source": "api_football_2022_2024",
                        "season_label": str(season),
                    })
                except Exception as e:
                    logger.error(f"Malformed API-Football fixture skipped: {e}")
                    continue

            time.sleep(self.request_delay_seconds)

        return fixtures

    def fetch_upcoming_fixtures(self) -> list:
        date_from = date.today().strftime("%Y-%m-%d")
        date_to = (date.today() + timedelta(days=self.days_ahead)).strftime("%Y-%m-%d")

        fdo_fixtures = self._fetch_from_football_data_org(date_from, date_to)
        af_fixtures = self._fetch_from_api_football(date_from, date_to)

        logger.info(
            f"Fetched {len(fdo_fixtures)} live fixtures from football-data.org "
            f"and {len(af_fixtures)} 2022-2024 fixtures from API-Football."
        )

        return fdo_fixtures + af_fixtures

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
                        INSERT INTO fixtures
                            (fixture_id, league, season, home_team, away_team,
                             match_date, status, data_source, season_label)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(fixture_id) DO UPDATE SET
                            league=excluded.league,
                            season=excluded.season,
                            home_team=excluded.home_team,
                            away_team=excluded.away_team,
                            match_date=excluded.match_date,
                            status=excluded.status,
                            data_source=excluded.data_source,
                            season_label=excluded.season_label
                        """,
                        (
                            fx["fixture_id"], fx["league"], fx.get("season"),
                            fx["home_team"], fx["away_team"], fx["match_date"],
                            fx["status"], fx.get("data_source", "unknown"),
                            fx.get("season_label", ""),
                        ),
                    )

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
