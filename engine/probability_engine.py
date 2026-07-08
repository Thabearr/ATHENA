from models.prediction import Prediction


class ProbabilityEngine:

    def calculate(self, prediction: Prediction):

        total_strength = (
            prediction.home_strength +
            prediction.away_strength
        )

        if total_strength == 0:
            return prediction

        prediction.home_win_probability = (
            prediction.home_strength /
            total_strength
        ) * 100

        prediction.away_win_probability = (
            prediction.away_strength /
            total_strength
        ) * 100

        prediction.draw_probability = max(
            0,
            100 -
            prediction.home_win_probability -
            prediction.away_win_probability
        )

        return prediction
