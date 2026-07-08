from models.prediction import Prediction


class ReliabilityEngine:

    def evaluate(self, prediction: Prediction):

        confidence = 50

        difference = abs(
            prediction.home_strength -
            prediction.away_strength
        )

        confidence += difference

        confidence -= prediction.risk_score / 2

        prediction.confidence = min(confidence, 99)

        return prediction
