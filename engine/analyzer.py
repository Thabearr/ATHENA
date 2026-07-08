from models.prediction import Prediction

from engine.team_strength_engine import TeamStrengthEngine
from engine.score_engine import ScoreEngine


class Analyzer:

    def __init__(self):

        self.team_strength = TeamStrengthEngine()
        self.score_engine = ScoreEngine()

    def analyze(self, fixture):

        prediction = Prediction(
            fixture_id=fixture["fixture"]["id"],
            league=fixture["league"]["name"],
            home_team=fixture["teams"]["home"]["name"],
            away_team=fixture["teams"]["away"]["name"],
        )

        # =====================================
        # Temporary Team Statistics
        # (These will soon come from StatisticsService)
        # =====================================

        home_stats = self._build_team_stats(fixture, True)
        away_stats = self._build_team_stats(fixture, False)

        home_strength = self.team_strength.calculate(home_stats)
        away_strength = self.team_strength.calculate(away_stats)

        prediction.home_strength = home_strength
        prediction.away_strength = away_strength

        # =====================================
        # Expected Goals
        # =====================================

        goals = self.score_engine.calculate(
            home_strength,
            away_strength
        )

        prediction.home_xg = goals["home_xg"]
        prediction.away_xg = goals["away_xg"]
        prediction.expected_goals = goals["total_xg"]

        # =====================================
        # Extra Analysis
        # =====================================

        self._analyze_form(prediction)
        self._analyze_home_advantage(prediction)
        self._analyze_injuries(prediction)
        self._analyze_weather(prediction)
        self._analyze_news(prediction)

        return prediction

    def _build_team_stats(self, fixture, home=True):

        # -------------------------------------------------
        # TEMPORARY PLACEHOLDER
        #
        # Soon this will load from:
        #
        # StatisticsService
        # StandingsService
        # TeamRepository
        #
        # instead of hardcoded values.
        # -------------------------------------------------

        return {

            "position": 10,

            "form_points": 8,

            "goal_difference": 6,

            "goals_scored": 20,

            "goals_conceded": 15,

            "clean_sheets": 5,

            "is_home": home

        }

    def _analyze_form(self, prediction):
        pass

    def _analyze_home_advantage(self, prediction):
        pass

    def _analyze_injuries(self, prediction):
        pass

    def _analyze_weather(self, prediction):
        pass

    def _analyze_news(self, prediction):
        pass
