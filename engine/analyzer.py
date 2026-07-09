from models.prediction import Prediction

from engine.team_strength_engine import TeamStrengthEngine
from engine.score_engine import ScoreEngine

from repositories.team_repository import TeamRepository
from services.statistics_service import StatisticsService


class Analyzer:

    def __init__(self):

        self.team_strength = TeamStrengthEngine()
        self.score_engine = ScoreEngine()

        self.team_repo = TeamRepository()
        self.statistics = StatisticsService()

    def analyze(self, fixture):

        prediction = Prediction(
            fixture_id=fixture["fixture"]["id"],
            league=fixture["league"]["name"],
            home_team=fixture["teams"]["home"]["name"],
            away_team=fixture["teams"]["away"]["name"],
        )

        home_stats = self._build_team_stats(fixture, True)
        away_stats = self._build_team_stats(fixture, False)

        prediction.home_position = home_stats["position"]
        prediction.away_position = away_stats["position"]

        prediction.home_strength = self.team_strength.calculate(home_stats)
        prediction.away_strength = self.team_strength.calculate(away_stats)

        goals = self.score_engine.calculate(
            prediction.home_strength,
            prediction.away_strength
        )

        prediction.home_xg = goals["home_xg"]
        prediction.away_xg = goals["away_xg"]
        prediction.expected_goals = goals["total_xg"]

        self._analyze_form(prediction)
        self._analyze_home_advantage(prediction)
        self._analyze_injuries(prediction)
        self._analyze_weather(prediction)
        self._analyze_news(prediction)

        return prediction

    def _build_team_stats(self, fixture, home=True):

        team = (
            fixture["teams"]["home"]
            if home
            else fixture["teams"]["away"]
        )

        league = fixture["league"]

        team_id = team["id"]
        league_id = league["id"]
        season = league["season"]

        stats = self.statistics.get_team_statistics(
            team_id,
            league_id,
            season
        )

        # Database not populated yet
        if not stats:

            return {
                "position": 10,
                "form_points": 8,
                "goal_difference": 0,
                "goals_scored": 0,
                "goals_conceded": 0,
                "clean_sheets": 0,
                "is_home": home
            }

        form = stats.get("form", "")

        form_points = (
            form.count("W") * 3 +
            form.count("D")
        )

        return {

            "position": stats.get("position", 10),

            "form_points": form_points,

            "goal_difference":
                stats.get("goals_for", 0)
                -
                stats.get("goals_against", 0),

            "goals_scored":
                stats.get("goals_for", 0),

            "goals_conceded":
                stats.get("goals_against", 0),

            "clean_sheets":
                stats.get("clean_sheets", 0),

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
