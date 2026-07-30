import csv
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from domain.half_time_data import (
    HalfTimeValidationStatus,
    ResearchReadiness,
    audit_half_time_coverage,
)
from domain.markets import MarketId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.source_capabilities import (
    CapabilityAvailability,
    SOURCE_CAPABILITY_REGISTRY,
)
from scripts.audit_half_time_coverage import (
    load_observations_from_database,
)
from scripts.import_football_data_uk import (
    OFFICIAL_BASE_URL,
    SOURCE,
    FootballDataUkImporter,
    deterministic_fixture_identity,
    official_csv_url,
    season_to_archive_code,
)


class _MockResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.close()


class FootballDataUkImporterTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    FIELDNAMES = (
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
        "B365H",
        "B365D",
        "B365A",
    )

    @classmethod
    def _csv_bytes(cls, rows) -> bytes:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(
            output,
            fieldnames=cls.FIELDNAMES,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            values = {field: "" for field in cls.FIELDNAMES}
            values.update(row)
            writer.writerow(values)
        return output.getvalue().encode("utf-8")

    @staticmethod
    def _row(**overrides):
        row = {
            "Div": "E0",
            "Date": "10/08/2024",
            "Time": "15:00",
            "HomeTeam": "Malmö Athletic",
            "AwayTeam": "São Paulo United",
            "FTHG": "2",
            "FTAG": "1",
            "FTR": "H",
            "HTHG": "1",
            "HTAG": "0",
            "HTR": "H",
            "B365H": "1.90",
            "B365D": "3.40",
            "B365A": "4.20",
        }
        row.update(overrides)
        return row

    @staticmethod
    def _cache_file(
        directory: Path,
        content: bytes,
        *,
        season: str = "2024-25",
        league: str = "E0",
    ) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (
            f"{season_to_archive_code(season)}_{league}.csv"
        )
        path.write_bytes(content)
        return path

    @staticmethod
    def _database_rows(database_path: Path, table: str):
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        try:
            return [
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM {table} ORDER BY id"
                )
            ]
        finally:
            connection.close()

    def _importer(
        self,
        directory: str,
        *,
        dry_run: bool = False,
    ) -> FootballDataUkImporter:
        root = Path(directory)
        return FootballDataUkImporter(
            seasons=("2024-25",),
            leagues=("E0",),
            database_path=str(root / "athena.db"),
            download_directory=str(root / "downloads"),
            dry_run=dry_run,
        )

    def test_module_cli_help_has_no_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "help.db"
            download_directory = Path(directory) / "downloads"
            environment = os.environ.copy()

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.import_football_data_uk",
                    "--help",
                ],
                cwd=self.REPOSITORY_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                shell=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--seasons", result.stdout)
            self.assertIn("--leagues", result.stdout)
            self.assertIn("--database", result.stdout)
            self.assertIn("--download-directory", result.stdout)
            self.assertIn("--dry-run", result.stdout)
            self.assertFalse(database_path.exists())
            self.assertFalse(download_directory.exists())

    def test_official_urls_and_archive_season_codes(self):
        self.assertEqual(season_to_archive_code("2020-21"), "2021")
        self.assertEqual(season_to_archive_code("2021-22"), "2122")
        self.assertEqual(season_to_archive_code("2025-26"), "2526")
        self.assertEqual(
            official_csv_url("2024-25", "e0"),
            f"{OFFICIAL_BASE_URL}/2425/E0.csv",
        )

    def test_download_uses_official_url_and_then_cache(self):
        content = self._csv_bytes([self._row()])
        with tempfile.TemporaryDirectory() as directory:
            importer = self._importer(directory)

            with patch(
                "scripts.import_football_data_uk.urlopen",
                return_value=_MockResponse(content),
            ) as download:
                first_path, first_downloaded = importer._download(
                    "2024-25",
                    "E0",
                )
                second_path, second_downloaded = importer._download(
                    "2024-25",
                    "E0",
                )

            self.assertTrue(first_downloaded)
            self.assertFalse(second_downloaded)
            self.assertEqual(first_path, second_path)
            self.assertEqual(first_path.read_bytes(), content)
            self.assertEqual(download.call_count, 1)
            request = download.call_args.args[0]
            self.assertEqual(
                request.full_url,
                f"{OFFICIAL_BASE_URL}/2425/E0.csv",
            )

    def test_valid_missing_invalid_and_malformed_rows_are_isolated(self):
        rows = [
            self._row(),
            self._row(
                Date="11/08/2024",
                HomeTeam="Draw FC",
                AwayTeam="Level Town",
                FTHG="0",
                FTAG="0",
                FTR="D",
                HTHG="",
                HTAG="",
                HTR="",
                B365H="not-imported",
            ),
            self._row(
                Date="12/08/2024",
                HomeTeam="Invalid HT",
                AwayTeam="Evidence FC",
                FTHG="1",
                FTAG="0",
                FTR="H",
                HTHG="2",
                HTAG="0",
                HTR="H",
            ),
            self._row(
                Date="13/08/2024",
                HomeTeam="Malformed FC",
                AwayTeam="Skipped Town",
                FTHG="not-a-score",
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            importer = self._importer(directory)
            self._cache_file(
                importer.download_directory,
                self._csv_bytes(rows),
            )

            diagnostics = importer.run()
            historical = self._database_rows(
                Path(importer.database_path),
                "historical_matches",
            )
            observations = self._database_rows(
                Path(importer.database_path),
                "half_time_observations",
            )
            odds = self._database_rows(
                Path(importer.database_path),
                "odds",
            )

            self.assertEqual(diagnostics.rows_seen, 4)
            self.assertEqual(diagnostics.historical_inserted, 3)
            self.assertEqual(diagnostics.half_time_valid, 1)
            self.assertEqual(diagnostics.half_time_missing, 1)
            self.assertEqual(diagnostics.half_time_invalid, 1)
            self.assertEqual(diagnostics.malformed_rows, 1)
            self.assertEqual(len(historical), 3)
            self.assertEqual(len(observations), 2)
            self.assertEqual(
                {
                    row["validation_status"]
                    for row in observations
                },
                {"VALID", "INVALID"},
            )
            self.assertEqual(odds, [])
            self.assertTrue(
                all(
                    row["data_source"] == SOURCE
                    for row in historical
                )
            )

    def test_fixture_identity_is_deterministic_sha256(self):
        arguments = {
            "season": "2024-25",
            "league": "E0",
            "match_date": "2024-08-10",
            "match_time": "15:00",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
        }
        first_id, first_fingerprint = deterministic_fixture_identity(
            **arguments
        )
        second_id, second_fingerprint = deterministic_fixture_identity(
            **arguments
        )
        canonical = json.dumps(
            [
                SOURCE,
                "2024-25",
                "E0",
                "2024-08-10",
                "15:00",
                "alpha fc",
                "beta fc",
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        expected = hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()

        self.assertEqual(first_id, second_id)
        self.assertEqual(first_fingerprint, second_fingerprint)
        self.assertEqual(first_fingerprint, expected)
        self.assertEqual(
            first_id,
            int(expected[:16], 16) & ((1 << 63) - 1),
        )

    def test_repeated_import_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            importer = self._importer(directory)
            self._cache_file(
                importer.download_directory,
                self._csv_bytes([self._row()]),
            )

            first = importer.run()
            second = importer.run()

            self.assertEqual(first.historical_inserted, 1)
            self.assertEqual(second.historical_inserted, 0)
            self.assertEqual(second.historical_unchanged, 1)
            self.assertEqual(second.half_time_unchanged, 1)
            self.assertEqual(
                len(
                    self._database_rows(
                        Path(importer.database_path),
                        "historical_matches",
                    )
                ),
                1,
            )
            self.assertEqual(
                len(
                    self._database_rows(
                        Path(importer.database_path),
                        "half_time_observations",
                    )
                ),
                1,
            )

    def test_material_conflict_is_preserved_and_visible_to_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            importer = self._importer(directory)
            cache_path = self._cache_file(
                importer.download_directory,
                self._csv_bytes([self._row()]),
            )
            importer.run()
            cache_path.write_bytes(
                self._csv_bytes(
                    [
                        self._row(
                            HTHG="0",
                            HTAG="0",
                            HTR="D",
                        )
                    ]
                )
            )

            second = importer.run()
            stored = self._database_rows(
                Path(importer.database_path),
                "half_time_observations",
            )[0]
            observations = load_observations_from_database(
                importer.database_path
            )
            report = audit_half_time_coverage(observations)

            self.assertEqual(second.half_time_conflicts, 1)
            self.assertEqual(stored["half_time_home_goals"], 1)
            self.assertEqual(stored["half_time_away_goals"], 0)
            self.assertEqual(stored["conflict_status"], 1)
            self.assertIn(
                stored["fixture_identity"],
                report.conflicting_fixtures,
            )
            self.assertEqual(
                report.fixtures_with_valid_half_time_scores,
                0,
            )
            self.assertEqual(
                report.readiness,
                ResearchReadiness.DATA_INVALID,
            )

    def test_dry_run_does_not_initialize_or_write_database(self):
        with tempfile.TemporaryDirectory() as directory:
            importer = self._importer(directory, dry_run=True)
            self._cache_file(
                importer.download_directory,
                self._csv_bytes([self._row()]),
            )

            diagnostics = importer.run()

            self.assertTrue(diagnostics.dry_run)
            self.assertEqual(diagnostics.rows_seen, 1)
            self.assertEqual(diagnostics.half_time_valid, 1)
            self.assertEqual(diagnostics.historical_inserted, 0)
            self.assertFalse(Path(importer.database_path).exists())

    def test_valid_import_is_visible_to_read_only_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            importer = self._importer(directory)
            self._cache_file(
                importer.download_directory,
                self._csv_bytes([self._row()]),
            )
            importer.run()

            observations = load_observations_from_database(
                importer.database_path
            )
            report = audit_half_time_coverage(observations)

            self.assertEqual(len(observations), 1)
            self.assertEqual(
                observations[0].validation_status,
                HalfTimeValidationStatus.VALID,
            )
            self.assertEqual(
                report.fixtures_with_valid_half_time_scores,
                1,
            )
            self.assertEqual(
                report.coverage_by_league["E0"]["valid"],
                1,
            )
            self.assertEqual(
                report.coverage_by_season["2024-25"]["valid"],
                1,
            )

    def test_win_either_half_markets_remain_disabled(self):
        capabilities = SOURCE_CAPABILITY_REGISTRY[SOURCE]
        self.assertEqual(
            capabilities.full_time_score,
            CapabilityAvailability.CONFIRMED,
        )
        self.assertEqual(
            capabilities.half_time_score,
            CapabilityAvailability.CONFIRMED,
        )
        self.assertEqual(
            capabilities.freshness_metadata,
            CapabilityAvailability.NOT_CAPTURED,
        )
        self.assertEqual(
            MODEL_STATUS_REGISTRY[
                MarketId.HOME_WIN_EITHER_HALF
            ].status,
            ModelStatus.DISABLED,
        )
        self.assertEqual(
            MODEL_STATUS_REGISTRY[
                MarketId.AWAY_WIN_EITHER_HALF
            ].status,
            ModelStatus.DISABLED,
        )


if __name__ == "__main__":
    unittest.main()
