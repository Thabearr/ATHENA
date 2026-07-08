from models.prediction import Prediction


class ReportGenerator:

    def generate(self, prediction: Prediction):

        print("\n" + "=" * 60)

        print(f"{prediction.home_team} vs {prediction.away_team}")

        print("=" * 60)

        print(f"League: {prediction.league}")

        print()

        print(f"Home Win Probability : {prediction.home_win_probability:.1f}%")
        print(f"Draw Probability     : {prediction.draw_probability:.1f}%")
        print(f"Away Win Probability : {prediction.away_win_probability:.1f}%")

        print()

        print(f"Confidence : {prediction.confidence:.1f}%")
        print(f"Risk Score : {prediction.risk_score:.1f}")

        print()

        print(f"Recommended Market : {prediction.recommended_market}")

        print()

        if prediction.reasons:

            print("Reasons:")

            for reason in prediction.reasons:
                print(f"✓ {reason}")

        print("=" * 60)
