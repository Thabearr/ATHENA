import unittest
from unittest.mock import DEFAULT, patch

import build_acca


class AccaBuilderDatabaseInitTests(unittest.TestCase):
    def test_builder_initializes_database_before_pipeline_setup(self):
        with patch.multiple(
            "build_acca",
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
