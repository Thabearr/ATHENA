#!/usr/bin/env python3
"""Import official football-data.co.uk historical score CSV files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional
from urllib.request import Request, urlopen

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from database.database import Database  # noqa: E402
from domain.half_time_data import (  # noqa: E402
    HalfTimeObservation,
    HalfTimeValidationStatus,
    ScoreProvenance,
)
from services.half_time_observation_store import (  # noqa: E402
    HalfTimeObservationStore,
    ObservationWriteResult,
)


SOURCE = "football_data_uk_csv"
OFFICIAL_BASE_URL = "https://www.football-data.co.uk/mmz4281"
DEFAULT_LEAGUES = (
    "E0",
    "SC0",
    "D1",
    "I1",
    "SP1",
    "F1",
    "N1",
    "B1",
    "P1",
    "T1",
    "G1",
)
REQUIRED_FIELDS = (
    "Div",
    "Date",
    "Time",
    "HomeTeam",
    "AwayTeam",
    "FTHG",
    "FTAG",
    "FTR",
    "HTHG",
    "HTAG",
    "HTR",
)
_LEAGUE_PATTERN = re.compile(r"^[A-Z0-9]{1,8}$")
_SEASON_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")
_INTEGER_PATTERN = re.compile(r"^-?\d+$")


class RowImportError(ValueError):
    """One malformed CSV row that must not stop other rows."""


@dataclass(frozen=True)
class ParsedFixture:
    fixture_id: int
    source_fixture_id: str
    league: str
    season: str
    home_team: str
    away_team: str
    home_team_id: int
    away_team_id: int
    match_date: str
    kickoff_time: Optional[datetime]
    full_time_home_goals: int
    full_time_away_goals: int
    full_time_result: str
    half_time_result: str
    observation: Optional[HalfTimeObservation]


@dataclass
class ImportDiagnostics:
    files_requested: int = 0
    files_downloaded: int = 0
    files_cached: int = 0
    rows_seen: int = 0
    historical_inserted: int = 0
    historical_unchanged: int = 0
    half_time_valid: int = 0
    half_time_missing: int = 0
    half_time_invalid: int = 0
    half_time_inserted: int = 0
    half_time_updated: int = 0
    half_time_unchanged: int = 0
    half_time_conflicts: int = 0
    half_time_persistence_errors: int = 0
    malformed_rows: int = 0
    dry_run: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def season_to_archive_code(season: str) -> str:
    match = _SEASON_PATTERN.fullmatch(str(season).strip())
    if not match:
        raise ValueError(
            f"Invalid season {season!r}; expected YYYY-YY."
        )
    start_year = int(match.group(1))
    end_year = int(match.group(2))
    if end_year != (start_year + 1) % 100:
        raise ValueError(
            f"Invalid season {season!r}; years must be consecutive."
        )
    return f"{start_year % 100:02d}{end_year:02d}"


def normalize_league(league: str) -> str:
    normalized = str(league).strip().upper()
    if not _LEAGUE_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"Invalid football-data.co.uk league code: {league!r}."
        )
    return normalized


def official_csv_url(season: str, league: str) -> str:
    archive_code = season_to_archive_code(season)
    league_code = normalize_league(league)
    return f"{OFFICIAL_BASE_URL}/{archive_code}/{league_code}.csv"


def _sha256_hex(parts: Iterable[str]) -> str:
    canonical = json.dumps(
        [str(part).strip() for part in parts],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _positive_63_bit_identity(fingerprint: str) -> int:
    identity = int(fingerprint[:16], 16) & ((1 << 63) - 1)
    return identity or 1


def deterministic_fixture_identity(
    *,
    season: str,
    league: str,
    match_date: str,
    match_time: str,
    home_team: str,
    away_team: str,
) -> tuple[int, str]:
    fingerprint = _sha256_hex(
        (
            SOURCE,
            season,
            normalize_league(league),
            match_date,
            match_time,
            home_team.casefold(),
            away_team.casefold(),
        )
    )
    return _positive_63_bit_identity(fingerprint), fingerprint


def deterministic_team_identity(team_name: str) -> int:
    fingerprint = _sha256_hex((SOURCE, "team", team_name.casefold()))
    return _positive_63_bit_identity(fingerprint)


def _parse_date(value: str) -> date:
    stripped = str(value or "").strip()
    for date_format in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(stripped, date_format).date()
        except ValueError:
            continue
    raise RowImportError(f"invalid Date value {stripped!r}")


def _parse_kickoff(
    match_date: date,
    value: str,
) -> Optional[datetime]:
    stripped = str(value or "").strip()
    if not stripped:
        return None
    for time_format in ("%H:%M", "%H:%M:%S", "%H.%M"):
        try:
            parsed_time = datetime.strptime(
                stripped,
                time_format,
            ).time()
            return datetime.combine(match_date, parsed_time)
        except ValueError:
            continue
    raise RowImportError(f"invalid Time value {stripped!r}")


def _parse_required_score(value: str, field_name: str) -> int:
    stripped = str(value or "").strip()
    if not _INTEGER_PATTERN.fullmatch(stripped):
        raise RowImportError(
            f"{field_name} must be an explicit integer"
        )
    parsed = int(stripped)
    if parsed < 0:
        raise RowImportError(f"{field_name} must be non-negative")
    return parsed


def _parse_optional_score(value: str):
    stripped = str(value or "").strip()
    if not stripped:
        return None
    if _INTEGER_PATTERN.fullmatch(stripped):
        return int(stripped)
    return stripped


def _expected_result(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "H"
    if home_goals < away_goals:
        return "A"
    return "D"


def _normalize_result(value: str, field_name: str) -> str:
    result = str(value or "").strip().upper()
    if result and result not in {"H", "D", "A"}:
        raise RowImportError(f"{field_name} must be H, D, A, or blank")
    return result


def _decode_csv(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1252")


class FootballDataUkImporter:
    def __init__(
        self,
        *,
        seasons: Iterable[str],
        leagues: Iterable[str] = DEFAULT_LEAGUES,
        database_path: str = "database/athena.db",
        download_directory: str = ".cache/football-data-uk",
        dry_run: bool = False,
        request_timeout_seconds: int = 60,
    ):
        self.seasons = tuple(str(season).strip() for season in seasons)
        if not self.seasons:
            raise ValueError("at least one season is required")
        for season in self.seasons:
            season_to_archive_code(season)
        self.leagues = tuple(normalize_league(league) for league in leagues)
        if not self.leagues:
            raise ValueError("at least one league is required")
        self.database_path = str(database_path)
        self.download_directory = Path(download_directory)
        self.dry_run = bool(dry_run)
        self.request_timeout_seconds = request_timeout_seconds
        self.database = Database(self.database_path)
        self.half_time_store = HalfTimeObservationStore()

    def _cache_path(self, season: str, league: str) -> Path:
        return self.download_directory / (
            f"{season_to_archive_code(season)}_{normalize_league(league)}.csv"
        )

    def _download(self, season: str, league: str) -> tuple[Path, bool]:
        destination = self._cache_path(season, league)
        if destination.is_file() and destination.stat().st_size > 0:
            return destination, False

        destination.parent.mkdir(parents=True, exist_ok=True)
        url = official_csv_url(season, league)
        request = Request(
            url,
            headers={"User-Agent": "ATHENA historical importer"},
        )
        with urlopen(
            request,
            timeout=self.request_timeout_seconds,
        ) as response:
            content = response.read()
        if not content:
            raise RuntimeError(
                f"Official CSV download returned no data for {season} {league}."
            )

        temporary = destination.with_suffix(".csv.tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return destination, True

    @staticmethod
    def _rows(csv_path: Path):
        content = _decode_csv(csv_path.read_bytes())
        reader = csv.DictReader(io.StringIO(content, newline=""))
        fieldnames = {
            str(field or "").strip()
            for field in (reader.fieldnames or ())
        }
        missing_fields = sorted(set(REQUIRED_FIELDS) - fieldnames)
        if missing_fields:
            raise RuntimeError(
                f"{csv_path.name} is missing required fields: "
                + ", ".join(missing_fields)
            )
        for row_number, raw_row in enumerate(reader, start=2):
            row = {
                str(key or "").strip(): value
                for key, value in raw_row.items()
            }
            yield row_number, row

    @staticmethod
    def _parse_row(
        row: dict,
        *,
        requested_season: str,
        requested_league: str,
    ) -> ParsedFixture:
        league = normalize_league(row.get("Div") or requested_league)
        home_team = str(row.get("HomeTeam") or "").strip()
        away_team = str(row.get("AwayTeam") or "").strip()
        if not home_team or not away_team:
            raise RowImportError("HomeTeam and AwayTeam are required")

        parsed_date = _parse_date(row.get("Date"))
        raw_time = str(row.get("Time") or "").strip()
        kickoff_time = _parse_kickoff(parsed_date, raw_time)
        match_date = parsed_date.isoformat()
        full_time_home = _parse_required_score(row.get("FTHG"), "FTHG")
        full_time_away = _parse_required_score(row.get("FTAG"), "FTAG")
        full_time_result = _normalize_result(row.get("FTR"), "FTR")
        if (
            full_time_result
            and full_time_result
            != _expected_result(full_time_home, full_time_away)
        ):
            raise RowImportError("FTR conflicts with full-time scores")

        half_time_home = _parse_optional_score(row.get("HTHG"))
        half_time_away = _parse_optional_score(row.get("HTAG"))
        half_time_result = _normalize_result(row.get("HTR"), "HTR")
        if (
            half_time_result
            and isinstance(half_time_home, int)
            and isinstance(half_time_away, int)
            and half_time_home >= 0
            and half_time_away >= 0
            and half_time_result
            != _expected_result(half_time_home, half_time_away)
        ):
            raise RowImportError("HTR conflicts with half-time scores")

        fixture_id, source_fixture_id = deterministic_fixture_identity(
            season=requested_season,
            league=league,
            match_date=match_date,
            match_time=raw_time,
            home_team=home_team,
            away_team=away_team,
        )
        observation = None
        if half_time_home is not None or half_time_away is not None:
            observation = HalfTimeObservation(
                fixture_identity=str(fixture_id),
                home_team=home_team,
                away_team=away_team,
                kickoff_time=kickoff_time,
                full_time_home_goals=full_time_home,
                full_time_away_goals=full_time_away,
                half_time_home_goals=half_time_home,
                half_time_away_goals=half_time_away,
                source=SOURCE,
                observed_at=None,
                source_fixture_id=source_fixture_id,
                half_time_score_provenance=ScoreProvenance.OBSERVED,
                league=league,
                season=requested_season,
            )

        stored_match_date = (
            kickoff_time.isoformat()
            if kickoff_time is not None
            else match_date
        )
        return ParsedFixture(
            fixture_id=fixture_id,
            source_fixture_id=source_fixture_id,
            league=league,
            season=requested_season,
            home_team=home_team,
            away_team=away_team,
            home_team_id=deterministic_team_identity(home_team),
            away_team_id=deterministic_team_identity(away_team),
            match_date=stored_match_date,
            kickoff_time=kickoff_time,
            full_time_home_goals=full_time_home,
            full_time_away_goals=full_time_away,
            full_time_result=full_time_result,
            half_time_result=half_time_result,
            observation=observation,
        )

    @staticmethod
    def _record_half_time_input(
        diagnostics: ImportDiagnostics,
        parsed: ParsedFixture,
    ) -> None:
        observation = parsed.observation
        if observation is None:
            diagnostics.half_time_missing += 1
        elif (
            observation.validation_status
            == HalfTimeValidationStatus.VALID
        ):
            diagnostics.half_time_valid += 1
        else:
            diagnostics.half_time_invalid += 1

    @staticmethod
    def _upsert_team(
        cursor,
        *,
        team_id: int,
        team_name: str,
        league: str,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO teams (team_id, name, league)
            VALUES (?, ?, ?)
            ON CONFLICT(team_id) DO UPDATE SET
                name = excluded.name,
                league = excluded.league
            """,
            (team_id, team_name, league),
        )

    def _persist_fixture(
        self,
        cursor,
        parsed: ParsedFixture,
        diagnostics: ImportDiagnostics,
    ) -> None:
        cursor.execute("SAVEPOINT football_data_uk_row")
        try:
            self._upsert_team(
                cursor,
                team_id=parsed.home_team_id,
                team_name=parsed.home_team,
                league=parsed.league,
            )
            self._upsert_team(
                cursor,
                team_id=parsed.away_team_id,
                team_name=parsed.away_team,
                league=parsed.league,
            )
            cursor.execute(
                """
                INSERT INTO historical_matches (
                    fixture_id, home_id, away_id, home_goals, away_goals,
                    match_date, data_source, season_label
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fixture_id) DO NOTHING
                """,
                (
                    parsed.fixture_id,
                    parsed.home_team_id,
                    parsed.away_team_id,
                    parsed.full_time_home_goals,
                    parsed.full_time_away_goals,
                    parsed.match_date,
                    SOURCE,
                    parsed.season,
                ),
            )
            if cursor.rowcount == 1:
                diagnostics.historical_inserted += 1
            else:
                diagnostics.historical_unchanged += 1

            if parsed.observation is not None:
                cursor.execute("SAVEPOINT football_data_uk_half_time")
                try:
                    write_result = self.half_time_store.upsert(
                        cursor,
                        parsed.observation,
                    )
                except Exception:
                    cursor.execute(
                        "ROLLBACK TO football_data_uk_half_time"
                    )
                    cursor.execute(
                        "RELEASE football_data_uk_half_time"
                    )
                    diagnostics.half_time_persistence_errors += 1
                else:
                    cursor.execute(
                        "RELEASE football_data_uk_half_time"
                    )
                    result_field = {
                        ObservationWriteResult.INSERTED: (
                            "half_time_inserted"
                        ),
                        ObservationWriteResult.UPDATED: (
                            "half_time_updated"
                        ),
                        ObservationWriteResult.UNCHANGED: (
                            "half_time_unchanged"
                        ),
                        ObservationWriteResult.CONFLICT: (
                            "half_time_conflicts"
                        ),
                    }[write_result]
                    setattr(
                        diagnostics,
                        result_field,
                        getattr(diagnostics, result_field) + 1,
                    )
        except Exception:
            cursor.execute("ROLLBACK TO football_data_uk_row")
            cursor.execute("RELEASE football_data_uk_row")
            raise
        else:
            cursor.execute("RELEASE football_data_uk_row")

    def _import_file(
        self,
        csv_path: Path,
        *,
        season: str,
        league: str,
        cursor,
        diagnostics: ImportDiagnostics,
    ) -> None:
        for _row_number, row in self._rows(csv_path):
            diagnostics.rows_seen += 1
            try:
                parsed = self._parse_row(
                    row,
                    requested_season=season,
                    requested_league=league,
                )
            except (RowImportError, TypeError, ValueError):
                diagnostics.malformed_rows += 1
                continue

            self._record_half_time_input(diagnostics, parsed)
            if self.dry_run:
                continue
            try:
                self._persist_fixture(
                    cursor,
                    parsed,
                    diagnostics,
                )
            except sqlite3.Error:
                diagnostics.malformed_rows += 1
                continue

    def run(self) -> ImportDiagnostics:
        diagnostics = ImportDiagnostics(dry_run=self.dry_run)
        downloads = []
        for season in self.seasons:
            for league in self.leagues:
                diagnostics.files_requested += 1
                csv_path, downloaded = self._download(season, league)
                downloads.append((csv_path, season, league))
                if downloaded:
                    diagnostics.files_downloaded += 1
                else:
                    diagnostics.files_cached += 1

        if self.dry_run:
            for csv_path, season, league in downloads:
                self._import_file(
                    csv_path,
                    season=season,
                    league=league,
                    cursor=None,
                    diagnostics=diagnostics,
                )
            return diagnostics

        self.database.initialize()
        connection = self.database.connect()
        try:
            cursor = connection.cursor()
            cursor.execute("BEGIN")
            for csv_path, season, league in downloads:
                self._import_file(
                    csv_path,
                    season=season,
                    league=league,
                    cursor=cursor,
                    diagnostics=diagnostics,
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return diagnostics


def _season_argument(value: str) -> str:
    try:
        season_to_archive_code(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return value


def _league_argument(value: str) -> str:
    try:
        return normalize_league(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import official football-data.co.uk historical full-time and "
            "half-time scores into ATHENA."
        )
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        required=True,
        type=_season_argument,
        help="Season labels in YYYY-YY format.",
    )
    parser.add_argument(
        "--leagues",
        nargs="+",
        type=_league_argument,
        default=list(DEFAULT_LEAGUES),
        help=(
            "football-data.co.uk division codes. Defaults to supported "
            "European top divisions."
        ),
    )
    parser.add_argument(
        "--database",
        default="database/athena.db",
        help="SQLite database path.",
    )
    parser.add_argument(
        "--download-directory",
        default=".cache/football-data-uk",
        help="Directory used to cache official CSV downloads.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and validate rows without initializing or writing a DB.",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    importer = FootballDataUkImporter(
        seasons=args.seasons,
        leagues=args.leagues,
        database_path=args.database,
        download_directory=args.download_directory,
        dry_run=args.dry_run,
    )
    diagnostics = importer.run()
    print(json.dumps(diagnostics.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
