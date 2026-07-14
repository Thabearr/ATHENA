import logging
import time
from datetime import date, timedelta

from config.settings import settings
from config.supported_leagues import SUPPORTED_LEAGUES, season_for_league
from config.competition_mapping import FOOTBALL_DATA_ORG_MAPPING
from api.football_api import FootballProvider
from api.football_data_org_provider import FootballDataOrgProvider
from database.database import Database

logger = logging.getLogger("athena.historical_results_loader")

FDO_ID_OFFSET = 10_000_000


class HistoricalResultsLoader:
    """
    Populates historical_matches from two sources:
      - football-data.org: real, current-season results for competitions in
        FOOTBALL_DATA_ORG_MAPPING. Tagged data_source='football_data_org_live'.
      - API-Football: 2022-2024 results for every other supported league.
        Tagged data_source='api_football_2022_2024'.

    Every row is tagged so TeamFormService/MatchAnalyst can tell fresh data
    from stale data instead of treating them the same.
    """

    def __init__(self, days_back: int = 120, request_delay_seconds: float = 1.0):
        self.days_back = days_back
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

    def _load_football_data_org(self, cursor, date_from, date_to) -> int:
        if not self.fdo_provider:
            logger.warning("FOOTBALL_DATA_ORG_API_KEY not set — skipping football-data.org results.")
            return 0

        inserted = 0
        for league_id, code in FOOTBALL_DATA_ORG_MAPPING.items():
            try:
                matches = self.fdo_provider.get_matches(
                    competition_code=code,
                    date_from=date_from,
                    date_to=date_to,
                    status="FINISHED",
                )
            except Exception as e:
                logger.error(f"football-data.org results fetch failed for {code}: {e}")
                time.sleep(self.request_delay_seconds)
                continue

            for m in matches:
                try:
                    score = m.get("score", {}).get("fullTime", {})
                    if score.get("home") is None or score.get("away") is None:
                        continue

                    cursor.execute(
                        """
                        INSERT INTO historical_matches
                            (fixture_id, home_id, away_id, home_goals, away_goals,
                             match_date, data_source, season_label)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(fixture_id) DO UPDATE SET
                            home_goals=excluded.home_goals,
                            away_goals=excluded.away_goals,
                            data_source=excluded.data_source,
                            season_label=excluded.season_label
                        """,
                        (
                            FDO_ID_OFFSET + m["id"],
                            FDO_ID_OFFSET + m["homeTeam"]["id"],
                            FDO_ID_OFFSET + m["awayTeam"]["id"],
                            score.get("home"),
                            score.get("away"),
                            m.get("utcDate", ""),
                            "football_data_org_live",
                            "2025-26",
                        ),
                    )
                    inserted += 1
                except Exception as e:
                    logger.error(f"Malformed football-data.org result skipped: {e}")
                    continue

            time.sleep(self.request_delay_seconds)

        return inserted

    def _load_api_football(self, cursor, date_from, date_to) -> int:
        if not self.af_provider:
            logger.warning("FOOTBALL_API_KEY not set — skipping API-Football results.")
            return 0

        inserted = 0
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
                logger.error(f"API-Football results fetch failed for league {league_id}: {e}")
                time.sleep(self.request_delay_seconds)
                continue

            for item in response:
                try:
                    fixture = item["fixture"]
                    if fixture.get("status", {}).get("short") != "FT":
                        continue

                    teams = item["teams"]
                    goals = item["goals"]

                    cursor.execute(
                        """
                        INSERT INTO historical_matches
                            (fixture_id, home_id, away_id, home_goals, away_goals,
                             match_date, data_source, season_label)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(fixture_id) DO UPDATE SET
                            home_goals=excluded.home_goals,
                            away_goals=excluded.away_goals,
                            data_source=excluded.data_source,
                            season_label=excluded.season_label
                        """,
                        (
                            fixture["id"],
                            teams["home"]["id"],
                            teams["away"]["id"],
                            goals.get("home"),
                            goals.get("away"),
                            fixture.get("date", ""),
                            "api_football_2022_2024",
                            str(season),
                        ),
                    )
                    inserted += 1
                except Exception as e:
                    logger.error(f"Malformed API-Football result skipped: {e}")
                    continue

            time.sleep(self.request_delay_seconds)

        return inserted

    def load(self) -> dict:
        date_from = (date.today() - timedelta(days=self.days_back)).strftime("%Y-%m-%d")
        date_to = date.today().strftime("%Y-%m-%d")

        with self.db.connect() as conn:
            cursor = conn.cursor()
            fdo_count = self._load_football_data_org(cursor, date_from, date_to)
            af_count = self._load_api_football(cursor, date_from, date_to)
            conn.commit()

        logger.info(
            f"Loaded {fdo_count} live results (football-data.org) and "
            f"{af_count} 2022-2024 results (API-Football) into historical_matches."
        )
        return {"football_data_org_live": fdo_count, "api_football_2022_2024": af_count}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loader = HistoricalResultsLoader(days_back=120)
    counts = loader.load()
    print(f"✅ Loaded {counts['football_data_org_live']} live results and "
          f"{counts['api_football_2022_2024']} 2022-2024 results into historical_matches.")
