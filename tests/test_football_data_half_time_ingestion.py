import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

from database.database import Database
from domain.half_time_data import (
    HalfTimeValidationStatus,
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
from workers.historical_results_loader import (
    FDO_ID_OFFSET,
    HistoricalResultsLoader,
)


class FootballDataHalfTimeIngestionTests(unittest.TestCase):
    PROVIDER_MATCH_ID = 12345
    UTC_DATE = "2026-07-27T18:00:00Z"
    LAST_UPDATED = "2026-07-28T12:30:00Z"

    @staticmethod
    def _initialize_database(database_path):
        connection = sqlite3.connect(database_path)
        try:
            connection.executescript(
                """
                CREATE TABLE historical_matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id INTEGER UNIQUE,
                    home_id INTEGER,
                    away_id INTEGER,
                    home_goals INTEGER,
                    away_goals INTEGER,
                    match_date TEXT,
                    data_source TEXT,
                    season_label TEXT
                );
                CREATE TABLE half_time_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_identity TEXT NOT NULL,
                    home_team TEXT,
                    away_team TEXT,
                    kickoff_time TEXT,
                    full_time_home_goals INTEGER,
                    full_time_away_goals INTEGER,
                    half_time_home_goals INTEGER,
                    half_time_away_goals INTEGER,
                    source TEXT NOT NULL,
                    observed_at TEXT,
                    source_fixture_id TEXT,
                    half_time_score_provenance TEXT NOT NULL,
                    validation_status TEXT NOT NULL,
                    rejection_reasons TEXT NOT NULL,
                    league TEXT,
                    season TEXT,
                    UNIQUE(fixture_identity, source)
                );
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _payload(
        self,
        *,
        match_id=None,
        full_time=(2, 1),
        half_time=(1, 0),
        last_updated=LAST_UPDATED,
    ):
        match = {
            "id": match_id or self.PROVIDER_MATCH_ID,
            "utcDate": self.UTC_DATE,
            "homeTeam": {"id": 10, "name": "Alpha FC"},
            "awayTeam": {"id": 20, "name": "Beta FC"},
            "score": {
                "fullTime": {
                    "home": full_time[0],
                    "away": full_time[1],
                },
                "halfTime": {
                    "home": half_time[0],
                    "away": half_time[1],
                },
            },
        }
        if last_updated is not None:
            match["lastUpdated"] = last_updated
        return match

    def _loader(self, database_path, matches):
        provider = Mock()
        provider.get_matches.return_value = matches
        loader = HistoricalResultsLoader(request_delay_seconds=0)
        loader.db = Database(str(database_path))
        loader.fdo_provider = provider
        loader.af_provider = None
        return loader, provider

    @staticmethod
    def _load(loader):
        with patch(
            "workers.historical_results_loader.FOOTBALL_DATA_ORG_MAPPING",
            {1: "TEST"},
        ):
            return loader.load()

    @staticmethod
    def _observation_rows(database_path):
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        try:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM half_time_observations
                    ORDER BY fixture_identity, source
                    """
                )
            ]
        finally:
            connection.close()

    @staticmethod
    def _historical_rows(database_path):
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        try:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM historical_matches ORDER BY fixture_id"
                )
            ]
        finally:
            connection.close()

    def test_valid_pair_persists_identity_metadata_and_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "valid.db"
            self._initialize_database(database_path)
            loader, provider = self._loader(
                database_path,
                [self._payload()],
            )

            counts = self._load(loader)
            rows = self._observation_rows(database_path)
            historical = self._historical_rows(database_path)

            self.assertEqual(provider.get_matches.call_count, 1)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            expected_identity = FDO_ID_OFFSET + self.PROVIDER_MATCH_ID
            self.assertEqual(row["fixture_identity"], str(expected_identity))
            self.assertEqual(historical[0]["fixture_id"], expected_identity)
            self.assertEqual(
                row["source_fixture_id"],
                str(self.PROVIDER_MATCH_ID),
            )
            self.assertEqual(
                row["kickoff_time"],
                "2026-07-27T18:00:00+00:00",
            )
            self.assertEqual(
                row["observed_at"],
                "2026-07-28T12:30:00+00:00",
            )
            self.assertEqual(
                row["half_time_score_provenance"],
                "OBSERVED",
            )
            self.assertEqual(row["validation_status"], "VALID")
            self.assertEqual(row["half_time_home_goals"], 1)
            self.assertEqual(row["half_time_away_goals"], 0)
            self.assertEqual(
                counts["football_data_org_half_time_valid"],
                1,
            )
            self.assertEqual(
                counts["football_data_org_half_time_missing"],
                0,
            )
            self.assertEqual(
                counts["football_data_org_half_time_invalid"],
                0,
            )
            self.assertEqual(
                counts["football_data_org_half_time_unchanged"],
                0,
            )

    def test_missing_or_naive_last_updated_remains_null(self):
        for last_updated in (None, "2026-07-28T12:30:00"):
            with self.subTest(last_updated=last_updated):
                with tempfile.TemporaryDirectory() as directory:
                    database_path = Path(directory) / "no-freshness.db"
                    self._initialize_database(database_path)
                    loader, _ = self._loader(
                        database_path,
                        [self._payload(last_updated=last_updated)],
                    )

                    self._load(loader)
                    row = self._observation_rows(database_path)[0]

                    self.assertIsNone(row["observed_at"])
                    self.assertNotEqual(
                        row["observed_at"],
                        row["kickoff_time"],
                    )

    def test_missing_half_time_creates_no_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "missing.db"
            self._initialize_database(database_path)
            loader, _ = self._loader(
                database_path,
                [self._payload(half_time=(None, None))],
            )

            counts = self._load(loader)

            self.assertEqual(self._observation_rows(database_path), [])
            self.assertEqual(len(self._historical_rows(database_path)), 1)
            self.assertEqual(
                counts["football_data_org_half_time_missing"],
                1,
            )

    def test_partial_half_time_pair_is_stored_as_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "partial.db"
            self._initialize_database(database_path)
            loader, _ = self._loader(
                database_path,
                [self._payload(half_time=(1, None))],
            )

            counts = self._load(loader)
            row = self._observation_rows(database_path)[0]

            self.assertEqual(row["validation_status"], "INVALID")
            self.assertIn(
                "both present or both missing",
                " ".join(json.loads(row["rejection_reasons"])),
            )
            self.assertEqual(
                counts["football_data_org_half_time_invalid"],
                1,
            )

    def test_malformed_scores_are_stored_as_invalid_evidence(self):
        invalid_pairs = (
            (True, 0),
            (-1, 0),
            (0.5, 0),
        )
        for index, half_time in enumerate(invalid_pairs):
            with self.subTest(half_time=half_time):
                with tempfile.TemporaryDirectory() as directory:
                    database_path = Path(directory) / f"invalid-{index}.db"
                    self._initialize_database(database_path)
                    loader, _ = self._loader(
                        database_path,
                        [
                            self._payload(
                                match_id=self.PROVIDER_MATCH_ID + index,
                                half_time=half_time,
                            )
                        ],
                    )

                    counts = self._load(loader)
                    row = self._observation_rows(database_path)[0]
                    audited = load_observations_from_database(
                        str(database_path)
                    )[0]

                    self.assertEqual(row["validation_status"], "INVALID")
                    self.assertTrue(json.loads(row["rejection_reasons"]))
                    self.assertEqual(
                        audited.validation_status,
                        HalfTimeValidationStatus.INVALID,
                    )
                    self.assertEqual(
                        counts["football_data_org_half_time_invalid"],
                        1,
                    )

    def test_half_time_above_full_time_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "above-full-time.db"
            self._initialize_database(database_path)
            loader, _ = self._loader(
                database_path,
                [self._payload(full_time=(1, 1), half_time=(2, 0))],
            )

            self._load(loader)
            row = self._observation_rows(database_path)[0]

            self.assertEqual(row["validation_status"], "INVALID")
            self.assertIn(
                "cannot exceed full-time",
                " ".join(json.loads(row["rejection_reasons"])),
            )

    def test_repeated_loader_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "idempotent.db"
            self._initialize_database(database_path)
            loader, provider = self._loader(
                database_path,
                [self._payload()],
            )

            first = self._load(loader)
            second = self._load(loader)

            self.assertEqual(len(self._observation_rows(database_path)), 1)
            self.assertEqual(first["football_data_org_half_time_unchanged"], 0)
            self.assertEqual(
                second["football_data_org_half_time_unchanged"],
                1,
            )
            self.assertEqual(provider.get_matches.call_count, 2)

    def test_older_or_untimestamped_payload_cannot_replace_newer(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "stale.db"
            self._initialize_database(database_path)
            loader, provider = self._loader(
                database_path,
                [self._payload(half_time=(1, 0))],
            )
            self._load(loader)

            provider.get_matches.return_value = [
                self._payload(
                    half_time=(0, 0),
                    last_updated="2026-07-27T12:30:00Z",
                )
            ]
            older_counts = self._load(loader)
            provider.get_matches.return_value = [
                self._payload(
                    half_time=(0, 1),
                    last_updated=None,
                )
            ]
            untimestamped_counts = self._load(loader)
            row = self._observation_rows(database_path)[0]

            self.assertEqual(row["half_time_home_goals"], 1)
            self.assertEqual(row["half_time_away_goals"], 0)
            self.assertEqual(
                row["observed_at"],
                "2026-07-28T12:30:00+00:00",
            )
            self.assertEqual(
                older_counts["football_data_org_half_time_unchanged"],
                1,
            )
            self.assertEqual(
                untimestamped_counts[
                    "football_data_org_half_time_unchanged"
                ],
                1,
            )

    def test_ingestion_adds_no_provider_request(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "request-count.db"
            self._initialize_database(database_path)
            loader, provider = self._loader(
                database_path,
                [self._payload()],
            )

            self._load(loader)

            provider.get_matches.assert_called_once_with(
                competition_code="TEST",
                date_from=ANY,
                date_to=ANY,
                status="FINISHED",
            )

    def test_coverage_audit_sees_persisted_valid_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "audit.db"
            self._initialize_database(database_path)
            loader, _ = self._loader(
                database_path,
                [self._payload()],
            )
            self._load(loader)

            observations = load_observations_from_database(
                str(database_path)
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

    def test_capability_and_market_status_safety(self):
        confirmed_half_time_sources = {
            source
            for source, capabilities in SOURCE_CAPABILITY_REGISTRY.items()
            if (
                capabilities.half_time_score
                == CapabilityAvailability.CONFIRMED
            )
        }

        self.assertEqual(
            confirmed_half_time_sources,
            {"football_data_org_live"},
        )
        football_data = SOURCE_CAPABILITY_REGISTRY[
            "football_data_org_live"
        ]
        self.assertEqual(
            football_data.freshness_metadata,
            CapabilityAvailability.CONFIRMED,
        )
        self.assertEqual(
            football_data.event_timestamps,
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
