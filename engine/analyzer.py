
from models.prediction import Prediction


class Analyzer:

    def analyze(self, fixture):

        prediction = Prediction(
            fixture_id=fixture["fixture"]["id"],
            league=fixture["league"]["name"],
            home_team=fixture["teams"]["home"]["name"],
            away_team=fixture["teams"]["away"]["name"],
        )

        self._analyze_form(prediction)
        self._analyze_strength(prediction)
        self._analyze_home_advantage(prediction)
        self._analyze_injuries(prediction)
        self._analyze_weather(prediction)
        self._analyze_news(prediction)

        return prediction

    def _analyze_form(self, prediction):
        pass

    def _analyze_strength(self, prediction):
        pass

    def _analyze_home_advantage(self, prediction):
        pass

    def _analyze_injuries(self, prediction):
        pass

    def _analyze_weather(self, prediction):
        pass

    def _analyze_news(self, prediction):
        pass
