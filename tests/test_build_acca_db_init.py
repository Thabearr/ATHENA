import unittest
from unittest.mock import DEFAULT, patch

from services import legacy_acca_builder_compat as build_acca


class AccaBuilderDatabaseInitTests(unittest.TestCase):
    def test_legacy_builder_is_explicitly_noncanonical_compatibility(self):
        self.assertIs(build_acca.DEPRECATED_COMPATIBILITY_ONLY, True)
        self.assertIs(build_acca.SUPPORTED_CANONICAL_CLI_AUTHORITY, False)
        self.assertEqual(
            build_acca.REPLACEMENT_SERVICE,
            "services.athena_run_service.AthenaRunService",
        )

    def test_p3_capture_helper_preserves_legacy_pipeline_accessor_shape(self):
        from scripts._p3_0_paired_capture_part1 import _legacy_pipeline

        with patch.object(build_acca, "AccaBuilder") as mock_builder:
            expected_pipeline = object()
            mock_builder.return_value.pipeline = expected_pipeline
            self.assertIs(_legacy_pipeline(), expected_pipeline)
            mock_builder.assert_called_once_with(days_ahead=1)

    def test_builder_initializes_database_before_pipeline_setup(self):
        with patch.multiple(
            "services.legacy_acca_builder_compat",
            Database=DEFAULT,
            FotMobAdvancedScraper=DEFAULT,
            OpenFootballLoader=DEFAULT,
            StatisticsService=DEFAULT,
            TeamFormService=DEFAULT,
            FormEngine=DEFAULT,
            MotivationEngine=DEFAULT,
            WeatherEngine=DEFAULT,
            FatigueEngine=DEFAULT,
            InjuryEngine=DEFAULT,
            RefereeEngine=DEFAULT,
            RiskEngine=DEFAULT,
            MatchAnalyst=DEFAULT,
            AnalysisPipeline=DEFAULT,
            AccumulatorEngine=DEFAULT,
            AccaFilter=DEFAULT,
            KellyCalculator=DEFAULT,
        ) as mocks:
            build_acca.AccaBuilder()
            mocks["Database"].return_value.initialize.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
