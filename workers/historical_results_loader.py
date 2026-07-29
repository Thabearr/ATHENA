import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from config.settings import settings
from config.supported_leagues import SUPPORTED_LEAGUES, season_for_league
from config.competition_mapping import FOOTBALL_DATA_ORG_MAPPING
from api.football_api import FootballProvider
from api.football_data_org_provider import FootballDataOrgProvider
from database.database import Database
from domain.half_time_data import (
    HalfTimeObservation,
    HalfTimeValidationStatus,
    ScoreProvenance,
)
from services.half_time_observation_store import (
    HalfTimeObservationStore,
    ObservationWriteResult,
)

logger = logging.getLogger("athena.historical_results_loader")

FDO_ID_OFFSET = 10_000_000
FDO_SOURCE = "football_data_org_live"
FDO_SEASON_LABEL = "2025-26"

_HALF_TIME_DIAGNOSTIC_KEYS = (
    "football_data_org_half_time_valid",
    "football_data_org_half_time_missing",
    "football_data_org_half_time_invalid",
    "football_data_org_half_time_unchanged",
    "football_data_org_half_time_conflicts",
    "football_data_org_half_time_persistence_errors",
)


def _parse_provider_datetime(
    value,
    *,
    require_timezone: bool,
):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None
    if require_timezone and (
        parsed.tzinfo is None or parsed.utcoffset() is None
    ):
        return None
    return parsed


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

    def __init__(self, days_back: int = 120, request_delay_seconds: float = 6.5):
        self.days_back = days_back
        self.request_delay_seconds = request_delay_seconds
        self.db = Database()
        self.half_time_store = HalfTimeObservationStore()
        self._half_time_diagnostics = self._new_half_time_diagnostics()

        self.fdo_provider = (
            FootballDataOrgProvider(settings.FOOTBALL_DATA_ORG_API_KEY)
            if settings.FOOTBALL_DATA_ORG_API_KEY else None
        )
        self.af_provider = (
            FootballProvider(settings.FOOTBALL_API_KEY)
            if settings.FOOTBALL_API_KEY else None
        )

    @staticmethod
    def _new_half_time_diagnostics() -> dict:
        return {key: 0 for key in _HALF_TIME_DIAGNOSTIC_KEYS}

    def _capture_football_data_half_time(
        self,
        cursor,
        match: dict,
        *,
        fixture_identity: int,
        competition_code: str,
        full_time: dict,
        half_time: dict,
    ) -> None:
        half_time_home = half_time.get("home")
        half_time_away = half_time.get("away")
        if half_time_home is None and half_time_away is None:
            self._half_time_diagnostics[
                "football_data_org_half_time_missing"
            ] += 1
            return

        observation = HalfTimeObservation(
            fixture_identity=str(fixture_identity),
            home_team=match.get("homeTeam", {}).get("name", ""),
            away_team=match.get("awayTeam", {}).get("name", ""),
            kickoff_time=_parse_provider_datetime(
                match.get("utcDate"),
                require_timezone=False,
            ),
            full_time_home_goals=full_time.get("home"),
            full_time_away_goals=full_time.get("away"),
            half_time_home_goals=half_time_home,
            half_time_away_goals=half_time_away,
            source=FDO_SOURCE,
            observed_at=_parse_provider_datetime(
                match.get("lastUpdated"),
                require_timezone=True,
            ),
            source_fixture_id=str(match.get("id")),
            half_time_score_provenance=ScoreProvenance.OBSERVED,
            league=competition_code,
            season=FDO_SEASON_LABEL,
        )
        diagnostic_key = (
            "football_data_org_half_time_valid"
            if observation.validation_status
            == HalfTimeValidationStatus.VALID
            else "football_data_org_half_time_invalid"
        )
        self._half_time_diagnostics[diagnostic_key] += 1
        write_result = self.half_time_store.upsert(
            cursor,
            observation,
        )
        if write_result == ObservationWriteResult.UNCHANGED:
            self._half_time_diagnostics[
                "football_data_org_half_time_unchanged"
            ] += 1
        elif write_result == ObservationWriteResult.CONFLICT:
            self._half_time_diagnostics[
                "football_data_org_half_time_conflicts"
            ] += 1
            logger.warning(
                "Conflicting football-data.org half-time evidence for "
                "fixture %s was not persisted.",
                fixture_identity,
            )
        if observation.validation_status == HalfTimeValidationStatus.INVALID:
            logger.warning(
                "Invalid football-data.org half-time evidence for fixture %s: %s",
                fixture_identity,
                "; ".join(observation.rejection_reasons),
            )

    def _load_football_data_org(self, cursor, date_from, date_to) -> int:
        self._half_time_diagnostics = self._new_half_time_diagnostics()
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
                    provider_match_id = m.get("id")
                    if provider_match_id is None:
                        continue
                    fixture_identity = FDO_ID_OFFSET + provider_match_id
                    score_payload = m.get("score", {})
                    if not isinstance(score_payload, dict):
                        score_payload = {}
                    full_time = score_payload.get("fullTime", {})
                    if not isinstance(full_time, dict):
                        full_time = {}
                    half_time = score_payload.get("halfTime", {})
                    if not isinstance(half_time, dict):
                        half_time = {}

                    cursor.execute(
                        "SAVEPOINT football_data_org_half_time_write"
                    )
                    try:
                        self._capture_football_data_half_time(
                            cursor,
                            m,
                            fixture_identity=fixture_identity,
                            competition_code=code,
                            full_time=full_time,
                            half_time=half_time,
                        )
                    except Exception as error:
                        cursor.execute(
                            "ROLLBACK TO football_data_org_half_time_write"
                        )
                        cursor.execute(
                            "RELEASE football_data_org_half_time_write"
                        )
                        self._half_time_diagnostics[
                            "football_data_org_half_time_persistence_errors"
                        ] += 1
                        logger.error(
                            "football-data.org half-time evidence could not "
                            "be persisted for fixture %s: %s",
                            fixture_identity,
                            error,
                        )
                    else:
                        cursor.execute(
                            "RELEASE football_data_org_half_time_write"
                        )

                    home_id = m.get("homeTeam", {}).get("id")
                    away_id = m.get("awayTeam", {}).get("id")

                    if home_id is None or away_id is None:
                        continue

                    if (
                        full_time.get("home") is None
                        or full_time.get("away") is None
                    ):
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
                            fixture_identity,
                            FDO_ID_OFFSET + home_id,
                            FDO_ID_OFFSET + away_id,
                            full_time.get("home"),
                            full_time.get("away"),
                            m.get("utcDate", ""),
                            FDO_SOURCE,
                            FDO_SEASON_LABEL,
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

        self.db.initialize()
        conn = self.db.connect()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN")
            fdo_count = self._load_football_data_org(cursor, date_from, date_to)
            af_count = self._load_api_football(cursor, date_from, date_to)
            conn.commit()
        finally:
            conn.close()

        logger.info(
            "Loaded %s full-time football-data.org results and %s "
            "API-Football results into historical_matches.",
            fdo_count,
            af_count,
        )
        logger.info(
            "football-data.org half-time evidence: valid=%s, missing=%s, "
            "invalid=%s, unchanged=%s, conflicts=%s, persistence_errors=%s.",
            self._half_time_diagnostics[
                "football_data_org_half_time_valid"
            ],
            self._half_time_diagnostics[
                "football_data_org_half_time_missing"
            ],
            self._half_time_diagnostics[
                "football_data_org_half_time_invalid"
            ],
            self._half_time_diagnostics[
                "football_data_org_half_time_unchanged"
            ],
            self._half_time_diagnostics[
                "football_data_org_half_time_conflicts"
            ],
            self._half_time_diagnostics[
                "football_data_org_half_time_persistence_errors"
            ],
        )
        return {
            "football_data_org_live": fdo_count,
            "api_football_2022_2024": af_count,
            **self._half_time_diagnostics,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load historical full-time results and explicit half-time "
            "evidence into ATHENA."
        )
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=120,
        help="Number of historical calendar days to request.",
    )
    parser.add_argument(
        "--request-delay-seconds",
        type=float,
        default=6.5,
        help="Delay between provider competition requests.",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    loader = HistoricalResultsLoader(
        days_back=args.days_back,
        request_delay_seconds=args.request_delay_seconds,
    )
    counts = loader.load()
    print(f"✅ Loaded {counts['football_data_org_live']} live results and "
          f"{counts['api_football_2022_2024']} 2022-2024 results into historical_matches.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
