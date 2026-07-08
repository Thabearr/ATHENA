from models.prediction import Prediction


class RiskEngine:

    def evaluate(self, prediction: Prediction):

        risk = 0

        # Close matches are riskier
        difference = abs(
            prediction.home_strength -
            prediction.away_strength
        )

        if difference < 5:
            risk += 35

        elif difference < 10:
            risk += 20

        else:
            risk += 10

        # Low confidence increases risk
        if prediction.confidence < 70:
            risk += 20

        prediction.risk_score = min(risk, 100)

        return prediction
