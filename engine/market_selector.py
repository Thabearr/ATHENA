from models.prediction import Prediction


class MarketSelector:

    def select(self, prediction: Prediction):

        # Default recommendation
        prediction.recommended_market = "No Recommendation"

        # Very high confidence
        if prediction.confidence >= 90:

            if prediction.home_win_probability > 70:
                prediction.recommended_market = "Home -0.5"

            elif prediction.away_win_probability > 70:
                prediction.recommended_market = "Away +0.5"

            else:
                prediction.recommended_market = "Home or Draw"

        # Medium confidence
        elif prediction.confidence >= 75:

            prediction.recommended_market = "Home or Draw"

        # Low confidence
        else:

            prediction.recommended_market = "No Recommendation"

        return prediction
