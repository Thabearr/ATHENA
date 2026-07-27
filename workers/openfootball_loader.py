import logging
import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.openfootball_mapping import OPENFOOTBALL_LEAGUE_CODES, OPENFOOTBALL_SEASON
from api.openfootball_provider import OpenFootballProvider
from database.database import Database

logger = logging.getLogger("athena.openfootball_loader")

OFB_ID_OFFSET = 30_000_000


class OpenFootballLoader:
    """
    Pulls real, current fixtures AND finished results from the openfootball
    project (public domain, CC0, no API key, no rate limit — plain GitHub
    JSON files) for leagues in OPENFOOTBALL_LEAGUE_CODES.

    Replaces the stale 2022-2024 API-Football fallback for these specific
    leagues with real, current data. Tagged
    data_source='openfootball_public_domain' throughout.
    """

    def __init__(self):
        self.provider = OpenFootballProvider()
        self.db = Database()

    def _team_id(self, name: str) -> int:
        return OFB_ID_OFFSET + (abs(hash(name)) % 1_000_000)

    def fetch_and_sync(self) -> dict:
        today_str = date.today().strftime("%Y-%m-%d")
        upcoming_count = 0
        historical_count = 0
        skipped_count = 0

        with self.db.connect() as conn:
            cursor = conn.cursor()

            for league_id, code in OPENFOOTBALL_LEAGUE_CODES.items():
                try:
                    data = self.provider.get_league_season(OPENFOOTBALL_SEASON, code)
                except Exception as e:
                    logger.error(f"openfootball fetch failed for {code}: {e}")
                    continue

                league_name = data.get("name", code)
                matches = data.get("matches", [])

                for m in matches:
                    try:
                        team1 = m.get("team1")
                        team2 = m.get("team2")
                        match_date = m.get("date")
                        if not team1 or not team2 or not match_date:
                            skipped_count += 1
                            continue

                        from services.gender_filter import is_womens_fixture
                        if is_womens_fixture(league_name, team1, team2):
                            skipped_count += 1
                            continue

                        home_id = self._team_id(team1)
                        away_id = self._team_id(team2)

                        for tid, tname in ((home_id, team1), (away_id, team2)):
                            cursor.execute(
                                """
                                INSERT INTO teams (team_id, name, league)
                                VALUES (?, ?, ?)
                                ON CONFLICT(team_id) DO UPDATE SET name=excluded.name
                                """,
                                (tid, tname, league_name),
                            )

                        score = m.get("score")
                        ft = None
                        if isinstance(score, dict):
                            ft = score.get("ft")
                        elif isinstance(score, list) and len(score) == 2:
                            # Some entries store the fulltime score as a bare
                            # [home, away] list instead of {"ft": [...]}
                            ft = score

                        fixture_id = OFB_ID_OFFSET + (abs(hash(f"{team1}-{team2}-{match_date}")) % 1_000_000_000)

                        if ft and isinstance(ft, list) and len(ft) == 2:
                            cursor.execute(
                                """
                                INSERT INTO historical_matches
                                    (fixture_id, home_id, away_id, home_goals, away_goals,
                                     match_date, data_source, season_label)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT(fixture_id) DO UPDATE SET
                                    home_goals=excluded.home_goals,
                                    away_goals=excluded.away_goals
                                """,
                                (fixture_id, home_id, away_id, ft[0], ft[1], match_date,
                                 "openfootball_public_domain", OPENFOOTBALL_SEASON),
                            )
                            historical_count += 1
                        elif match_date >= today_str:
                            cursor.execute(
                                """
                                INSERT INTO fixtures
                                    (fixture_id, league, season, home_team, away_team,
                                     match_date, status, data_source, season_label)
                                VALUES (?, ?, ?, ?, ?, ?, 'NS', ?, ?)
                                ON CONFLICT(fixture_id) DO UPDATE SET
                                    match_date=excluded.match_date,
                                    status=excluded.status
                                """,
                                (fixture_id, league_name, OPENFOOTBALL_SEASON, team1, team2,
                                 match_date, "openfootball_public_domain", OPENFOOTBALL_SEASON),
                            )
                            upcoming_count += 1
                        else:
                            skipped_count += 1
                    except Exception as e:
                        logger.error(f"Malformed openfootball match skipped: {e}")
                        skipped_count += 1
                        continue

            conn.commit()

        logger.info(
            f"openfootball: synced {upcoming_count} upcoming fixtures, "
            f"{historical_count} historical results, skipped {skipped_count}."
        )
        return {"upcoming": upcoming_count, "historical": historical_count, "skipped": skipped_count}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loader = OpenFootballLoader()
    counts = loader.fetch_and_sync()
    print(
        f"SUCCESS: openfootball: {counts['upcoming']} upcoming fixtures, "
        f"{counts['historical']} historical results synced, {counts['skipped']} skipped."
    )
