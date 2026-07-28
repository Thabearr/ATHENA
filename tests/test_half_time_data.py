import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from domain.half_time_data import (
    HalfTimeObservation,
    HalfTimeValidationStatus,
    ReadinessThresholds,
    ResearchReadiness,
    ScoreProvenance,
    audit_half_time_coverage,
    deduplicate_observations,
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


class HalfTimeObservationTests(unittest.TestCase):
    OBSERVED_AT = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)

    def _observation(self, **overrides):
        values = {
            "fixture_identity": "fixture-1",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "kickoff_time": datetime(
                2026,
                7,
                27,
                18,
                0,
                tzinfo=timezone.utc,
            ),
            "full_time_home_goals": 2,
            "full_time_away_goals": 1,
            "half_time_home_goals": 1,
            "half_time_away_goals": 0,
            "source": "verified_test_source",
            "observed_at": self.OBSERVED_AT,
            "source_fixture_id": "source-1",
            "half_time_score_provenance": ScoreProvenance.OBSERVED,
            "league": "Test League",
            "season": "2025-26",
        }
        values.update(overrides)
        return HalfTimeObservation(**values)

    def test_valid_half_time_observation_is_accepted(self):
        observation = self._observation()

        self.assertEqual(
            observation.validation_status,
            HalfTimeValidationStatus.VALID,
        )
        self.assertEqual(observation.rejection_reasons, ())

    def test_missing_half_time_scores_remain_missing(self):
        observation = self._observation(
            half_time_home_goals=None,
            half_time_away_goals=None,
            half_time_score_provenance=ScoreProvenance.MISSING,
        )

        self.assertEqual(
            observation.validation_status,
            HalfTimeValidationStatus.MISSING,
        )
        self.assertIsNone(observation.half_time_home_goals)
        self.assertIsNone(observation.half_time_away_goals)

    def test_half_time_scores_are_never_inferred_from_full_time(self):
        missing = self._observation(
            half_time_home_goals=None,
            half_time_away_goals=None,
            half_time_score_provenance=ScoreProvenance.MISSING,
        )
        inferred = self._observation(
            half_time_home_goals=2,
            half_time_away_goals=1,
            half_time_score_provenance=ScoreProvenance.INFERRED,
        )

        self.assertIsNone(missing.half_time_home_goals)
        self.assertIsNone(missing.half_time_away_goals)
        self.assertEqual(
            inferred.validation_status,
            HalfTimeValidationStatus.INVALID,
        )
        self.assertTrue(
            any(
                "inferred or fabricated" in reason
                for reason in inferred.rejection_reasons
            )
        )

    def test_half_time_scores_cannot_exceed_full_time_scores(self):
        for field_name, value in (
            ("half_time_home_goals", 3),
            ("half_time_away_goals", 2),
        ):
            with self.subTest(field_name=field_name):
                observation = self._observation(**{field_name: value})

                self.assertEqual(
                    observation.validation_status,
                    HalfTimeValidationStatus.INVALID,
                )
                self.assertTrue(
                    any(
                        "cannot exceed" in reason
                        for reason in observation.rejection_reasons
                    )
                )

    def test_negative_boolean_and_non_integer_scores_are_rejected(self):
        for field_name in (
            "full_time_home_goals",
            "full_time_away_goals",
            "half_time_home_goals",
            "half_time_away_goals",
        ):
            for invalid_value in (-1, True, 1.5):
                with self.subTest(
                    field_name=field_name,
                    invalid_value=invalid_value,
                ):
                    observation = self._observation(
                        **{field_name: invalid_value}
                    )

                    self.assertEqual(
                        observation.validation_status,
                        HalfTimeValidationStatus.INVALID,
                    )

    def test_missing_fixture_identity_is_rejected(self):
        observation = self._observation(fixture_identity="")

        self.assertEqual(
            observation.validation_status,
            HalfTimeValidationStatus.INVALID,
        )
        self.assertIn(
            "fixture identity is required",
            observation.rejection_reasons,
        )

    def test_duplicate_fixture_source_observations_are_deterministic(self):
        older = self._observation(
            half_time_home_goals=0,
            observed_at=self.OBSERVED_AT - timedelta(hours=1),
        )
        newer = self._observation(
            half_time_home_goals=1,
            observed_at=self.OBSERVED_AT,
        )

        forward = deduplicate_observations((older, newer))
        reverse = deduplicate_observations((newer, older))

        self.assertEqual(forward, reverse)
        self.assertEqual(forward, (newer,))


class HalfTimeCoverageTests(unittest.TestCase):
    OBSERVED_AT = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)

    def _observation(
        self,
        fixture_identity,
        *,
        valid=True,
        source="verified_test_source",
        half_time_score=(1, 0),
        league="League A",
        season="2025-26",
    ):
        return HalfTimeObservation(
            fixture_identity=fixture_identity,
            home_team="Alpha FC",
            away_team="Beta FC",
            kickoff_time=self.OBSERVED_AT - timedelta(days=1),
            full_time_home_goals=2,
            full_time_away_goals=1,
            half_time_home_goals=half_time_score[0] if valid else None,
            half_time_away_goals=half_time_score[1] if valid else None,
            source=source,
            observed_at=self.OBSERVED_AT,
            source_fixture_id=fixture_identity,
            half_time_score_provenance=(
                ScoreProvenance.OBSERVED
                if valid
                else ScoreProvenance.MISSING
            ),
            league=league,
            season=season,
        )

    def test_coverage_calculation_is_deterministic(self):
        observations = (
            self._observation("fixture-1"),
            self._observation(
                "fixture-2",
                valid=False,
                league="League B",
                season="2024-25",
            ),
        )
        thresholds = ReadinessThresholds(
            minimum_valid_observations=1,
            minimum_overall_coverage=0.5,
            minimum_league_coverage=0.0,
            maximum_invalid_record_percentage=0.0,
        )

        forward = audit_half_time_coverage(
            observations,
            thresholds,
        ).to_dict()
        reverse = audit_half_time_coverage(
            reversed(observations),
            thresholds,
        ).to_dict()

        self.assertEqual(forward, reverse)
        self.assertEqual(forward["coverage_percentage"], 50.0)
        self.assertEqual(
            forward["fixtures_with_valid_half_time_scores"],
            1,
        )
        self.assertEqual(forward["fixtures_missing_half_time_scores"], 1)

    def test_dataset_below_threshold_is_insufficient(self):
        report = audit_half_time_coverage(
            (self._observation("fixture-1"),),
            ReadinessThresholds(
                minimum_valid_observations=2,
                minimum_overall_coverage=1.0,
                minimum_league_coverage=1.0,
                maximum_invalid_record_percentage=0.0,
            ),
        )

        self.assertEqual(
            report.readiness,
            ResearchReadiness.INSUFFICIENT_DATA,
        )
        self.assertTrue(report.readiness_reasons)

    def test_no_observations_returns_no_data(self):
        report = audit_half_time_coverage(())

        self.assertEqual(report.readiness, ResearchReadiness.NO_DATA)
        self.assertEqual(report.total_historical_fixtures_inspected, 0)

    def test_excess_invalid_records_returns_data_invalid(self):
        invalid = HalfTimeObservation(
            fixture_identity="invalid-fixture",
            home_team="Alpha FC",
            away_team="Beta FC",
            kickoff_time=self.OBSERVED_AT - timedelta(days=1),
            full_time_home_goals=1,
            full_time_away_goals=0,
            half_time_home_goals=2,
            half_time_away_goals=0,
            source="verified_test_source",
            observed_at=self.OBSERVED_AT,
            half_time_score_provenance=ScoreProvenance.OBSERVED,
            league="League A",
            season="2025-26",
        )
        report = audit_half_time_coverage(
            (invalid,),
            ReadinessThresholds(
                minimum_valid_observations=1,
                minimum_overall_coverage=0.0,
                minimum_league_coverage=0.0,
                maximum_invalid_record_percentage=0.0,
            ),
        )

        self.assertEqual(
            report.readiness,
            ResearchReadiness.DATA_INVALID,
        )

    def test_invalid_source_record_is_not_erased_by_valid_source(self):
        valid = self._observation(
            "multi-source-fixture",
            source="valid_source",
        )
        invalid = HalfTimeObservation(
            fixture_identity="multi-source-fixture",
            home_team="Alpha FC",
            away_team="Beta FC",
            kickoff_time=self.OBSERVED_AT - timedelta(days=1),
            full_time_home_goals=2,
            full_time_away_goals=1,
            half_time_home_goals=3,
            half_time_away_goals=0,
            source="invalid_source",
            observed_at=self.OBSERVED_AT,
            half_time_score_provenance=ScoreProvenance.OBSERVED,
            league="League A",
            season="2025-26",
        )
        report = audit_half_time_coverage(
            (valid, invalid),
            ReadinessThresholds(
                minimum_valid_observations=1,
                minimum_overall_coverage=1.0,
                minimum_league_coverage=1.0,
                maximum_invalid_record_percentage=0.40,
            ),
        )

        self.assertEqual(report.total_historical_fixtures_inspected, 1)
        self.assertEqual(report.invalid_observations, 0)
        self.assertEqual(report.total_source_observations, 2)
        self.assertEqual(report.invalid_source_observations, 1)
        self.assertEqual(
            set(report.source_breakdown),
            {"valid_source", "invalid_source"},
        )
        self.assertEqual(
            report.readiness,
            ResearchReadiness.DATA_INVALID,
        )

    def test_conflicting_valid_half_time_scores_prevent_readiness(self):
        first = self._observation(
            "conflicting-fixture",
            source="source_a",
            half_time_score=(1, 0),
        )
        second = self._observation(
            "conflicting-fixture",
            source="source_b",
            half_time_score=(0, 1),
        )
        report = audit_half_time_coverage(
            (first, second),
            ReadinessThresholds(
                minimum_valid_observations=1,
                minimum_overall_coverage=1.0,
                minimum_league_coverage=1.0,
                maximum_invalid_record_percentage=1.0,
            ),
        )

        self.assertEqual(
            report.conflicting_fixtures,
            ("conflicting-fixture",),
        )
        self.assertEqual(
            report.readiness,
            ResearchReadiness.DATA_INVALID,
        )
        self.assertEqual(
            set(report.source_breakdown),
            {"source_a", "source_b"},
        )

    def test_win_either_half_remains_disabled_when_research_ready(self):
        report = audit_half_time_coverage(
            (self._observation("fixture-1"),),
            ReadinessThresholds(
                minimum_valid_observations=1,
                minimum_overall_coverage=1.0,
                minimum_league_coverage=1.0,
                maximum_invalid_record_percentage=0.0,
            ),
        )

        self.assertEqual(
            report.readiness,
            ResearchReadiness.READY_FOR_RESEARCH,
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


class SourceCapabilityTests(unittest.TestCase):
    def test_no_source_claims_confirmed_half_time_support(self):
        confirmed = [
            source
            for source, capabilities in SOURCE_CAPABILITY_REGISTRY.items()
            if (
                capabilities.half_time_score
                == CapabilityAvailability.CONFIRMED
            )
        ]

        self.assertEqual(confirmed, [])
        self.assertEqual(
            SOURCE_CAPABILITY_REGISTRY[
                "fotmob_unofficial"
            ].half_time_score,
            CapabilityAvailability.UNKNOWN,
        )


class HalfTimeCoverageDatabaseTests(unittest.TestCase):
    @staticmethod
    def _create_database(database_path, statements):
        connection = sqlite3.connect(database_path)
        try:
            connection.executescript(
                Path("database/schema.sql").read_text(encoding="utf-8")
            )
            for table, column, column_type in (
                ("fixtures", "data_source", "TEXT"),
                ("fixtures", "season_label", "TEXT"),
                ("historical_matches", "data_source", "TEXT"),
                ("historical_matches", "season_label", "TEXT"),
            ):
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
                )
            connection.executescript(statements)
            connection.commit()
        finally:
            connection.close()

    def test_schema_uses_additive_half_time_observation_storage(self):
        connection = sqlite3.connect(":memory:")
        try:
            connection.executescript(
                Path("database/schema.sql").read_text(encoding="utf-8")
            )
            half_time_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(half_time_observations)"
                )
            }
            historical_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(historical_matches)"
                )
            }
        finally:
            connection.close()

        self.assertIn("half_time_home_goals", half_time_columns)
        self.assertIn("half_time_away_goals", half_time_columns)
        self.assertNotIn("half_time_home_goals", historical_columns)
        self.assertNotIn("half_time_away_goals", historical_columns)

    def test_finished_fotmob_fixture_from_results_is_inspected(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "fotmob.db"
            self._create_database(
                database_path,
                """
                INSERT INTO fixtures (
                    fixture_id, league, season, home_team, away_team,
                    match_date, status, data_source, season_label
                ) VALUES (
                    200, 'Test League', 2025, 'Alpha FC', 'Beta FC',
                    '2026-07-27T18:00:00+00:00', 'FT',
                    'fotmob_historical', '2025-26'
                );
                INSERT INTO results (
                    fixture_id, home_score, away_score, finished
                ) VALUES (200, 2, 1, 1);
                """,
            )

            observations = load_observations_from_database(
                str(database_path)
            )
            report = audit_half_time_coverage(observations)

            self.assertEqual(len(observations), 1)
            self.assertEqual(observations[0].fixture_identity, "200")
            self.assertEqual(observations[0].source, "fotmob_historical")
            self.assertEqual(observations[0].full_time_home_goals, 2)
            self.assertEqual(
                report.total_historical_fixtures_inspected,
                1,
            )

    def test_half_time_observation_without_full_time_store_is_inspected(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "observation-only.db"
            self._create_database(
                database_path,
                """
                INSERT INTO half_time_observations (
                    fixture_identity, home_team, away_team, kickoff_time,
                    full_time_home_goals, full_time_away_goals,
                    half_time_home_goals, half_time_away_goals,
                    source, observed_at, source_fixture_id,
                    half_time_score_provenance, validation_status,
                    rejection_reasons, league, season
                ) VALUES (
                    'observation-only', 'Alpha FC', 'Beta FC',
                    '2026-07-27T18:00:00+00:00', 2, 1, 1, 0,
                    'verified_test_source',
                    '2026-07-28T12:00:00+00:00', 'source-only',
                    'OBSERVED', 'VALID', '[]', 'Test League', '2025-26'
                );
                """,
            )

            observations = load_observations_from_database(
                str(database_path)
            )
            report = audit_half_time_coverage(observations)

            self.assertEqual(len(observations), 1)
            self.assertEqual(
                observations[0].fixture_identity,
                "observation-only",
            )
            self.assertEqual(
                observations[0].validation_status,
                HalfTimeValidationStatus.VALID,
            )
            self.assertEqual(
                report.total_historical_fixtures_inspected,
                1,
            )

    def test_historical_full_time_score_overrides_and_flags_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "full-time-conflict.db"
            self._create_database(
                database_path,
                """
                INSERT INTO teams (team_id, name) VALUES (1, 'Alpha FC');
                INSERT INTO teams (team_id, name) VALUES (2, 'Beta FC');
                INSERT INTO historical_matches (
                    fixture_id, home_id, away_id, home_goals, away_goals,
                    match_date, data_source, season_label
                ) VALUES (
                    300, 1, 2, 2, 1,
                    '2026-07-27T18:00:00+00:00',
                    'football_data_org_live', '2025-26'
                );
                INSERT INTO half_time_observations (
                    fixture_identity, home_team, away_team, kickoff_time,
                    full_time_home_goals, full_time_away_goals,
                    half_time_home_goals, half_time_away_goals,
                    source, observed_at, source_fixture_id,
                    half_time_score_provenance, validation_status,
                    rejection_reasons, league, season
                ) VALUES (
                    '300', 'Alpha FC', 'Beta FC',
                    '2026-07-27T18:00:00+00:00', 1, 1, 1, 0,
                    'conflicting_source',
                    '2026-07-28T12:00:00+00:00', 'source-300',
                    'OBSERVED', 'VALID', '[]', 'Test League', '2025-26'
                );
                """,
            )

            observation = load_observations_from_database(
                str(database_path)
            )[0]

            self.assertEqual(observation.full_time_home_goals, 2)
            self.assertEqual(observation.full_time_away_goals, 1)
            self.assertEqual(observation.stored_full_time_home_goals, 1)
            self.assertEqual(observation.stored_full_time_away_goals, 1)
            self.assertEqual(
                observation.authoritative_full_time_source,
                "historical_matches",
            )
            self.assertEqual(
                observation.validation_status,
                HalfTimeValidationStatus.INVALID,
            )
            self.assertTrue(
                any(
                    "conflict with authoritative historical_matches"
                    in reason
                    for reason in observation.rejection_reasons
                )
            )

    def test_duplicate_full_time_stores_use_historical_precedence_once(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "precedence.db"
            self._create_database(
                database_path,
                """
                INSERT INTO teams (team_id, name) VALUES (1, 'Alpha FC');
                INSERT INTO teams (team_id, name) VALUES (2, 'Beta FC');
                INSERT INTO fixtures (
                    fixture_id, league, season, home_team, away_team,
                    match_date, status, data_source, season_label
                ) VALUES (
                    400, 'Test League', 2025, 'Alpha FC', 'Beta FC',
                    '2026-07-27T18:00:00+00:00', 'FT',
                    'fotmob_historical', '2025-26'
                );
                INSERT INTO results (
                    fixture_id, home_score, away_score, finished
                ) VALUES (400, 1, 1, 1);
                INSERT INTO historical_matches (
                    fixture_id, home_id, away_id, home_goals, away_goals,
                    match_date, data_source, season_label
                ) VALUES (
                    400, 1, 2, 3, 0,
                    '2026-07-27T18:00:00+00:00',
                    'football_data_org_live', '2025-26'
                );
                """,
            )

            observations = load_observations_from_database(
                str(database_path)
            )
            report = audit_half_time_coverage(observations)

            self.assertEqual(len(observations), 1)
            self.assertEqual(observations[0].full_time_home_goals, 3)
            self.assertEqual(observations[0].full_time_away_goals, 0)
            self.assertEqual(
                observations[0].authoritative_full_time_source,
                "historical_matches",
            )
            self.assertEqual(
                report.total_historical_fixtures_inspected,
                1,
            )

    def test_database_audit_is_read_only_and_preserves_missing_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "coverage.db"
            self._create_database(
                database_path,
                """
                INSERT INTO teams (team_id, name) VALUES (1, 'Alpha FC');
                INSERT INTO teams (team_id, name) VALUES (2, 'Beta FC');
                INSERT INTO historical_matches (
                    fixture_id, home_id, away_id, home_goals, away_goals,
                    match_date, data_source, season_label
                ) VALUES (
                    100, 1, 2, 2, 1,
                    '2026-07-27T18:00:00+00:00',
                    'football_data_org_live', '2025-26'
                );
                INSERT INTO fixtures (
                    fixture_id, league, season, home_team, away_team,
                    match_date, status, data_source, season_label
                ) VALUES (
                    101, 'Test League', 2025, 'Gamma FC', 'Delta FC',
                    '2026-07-27T20:00:00+00:00', 'FT',
                    'fotmob_historical', '2025-26'
                );
                INSERT INTO results (
                    fixture_id, home_score, away_score, finished
                ) VALUES (101, 1, 0, 1);
                INSERT INTO half_time_observations (
                    fixture_identity, home_team, away_team, kickoff_time,
                    full_time_home_goals, full_time_away_goals,
                    half_time_home_goals, half_time_away_goals,
                    source, observed_at, source_fixture_id,
                    half_time_score_provenance, validation_status,
                    rejection_reasons, league, season
                ) VALUES (
                    '102', 'Epsilon FC', 'Zeta FC',
                    '2026-07-27T21:00:00+00:00', 3, 1, 1, 0,
                    'verified_test_source',
                    '2026-07-28T12:00:00+00:00', 'source-102',
                    'OBSERVED', 'VALID', '[]', 'Test League', '2025-26'
                );
                """,
            )
            before = hashlib.sha256(database_path.read_bytes()).hexdigest()

            observations = load_observations_from_database(
                str(database_path)
            )

            after = hashlib.sha256(database_path.read_bytes()).hexdigest()
            self.assertEqual(before, after)
            self.assertEqual(len(observations), 3)
            missing = next(
                observation
                for observation in observations
                if observation.fixture_identity == "100"
            )
            self.assertEqual(
                missing.validation_status,
                HalfTimeValidationStatus.MISSING,
            )
            self.assertIsNone(missing.half_time_home_goals)
            self.assertIsNone(missing.half_time_away_goals)


if __name__ == "__main__":
    unittest.main()
