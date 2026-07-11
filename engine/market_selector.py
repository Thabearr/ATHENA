from models.prediction import Prediction


class MarketSelector:
    """
    ATHENA Market Selection Engine

    Ranks every supported betting market and selects
    the safest value market.

    Over 0.5 is intentionally NOT supported because
    the odds are usually too small to provide value.
    """

    def select(self, prediction: Prediction):

        markets = []

        home = prediction.home_win_probability
        draw = prediction.draw_probability
        away = prediction.away_win_probability

        total_xg = prediction.expected_goals

        # -----------------------------
        # Match Winner
        # -----------------------------

        markets.append((
            "Home Win",
            home
        ))

        markets.append((
            "Away Win",
            away
        ))

        # -----------------------------
        # Double Chance
        # -----------------------------

        markets.append((
            "Home or Draw",
            home + draw
        ))

        markets.append((
            "Away or Draw",
            away + draw
        ))

        markets.append((
            "Home or Away",
            home + away
        ))

        # -----------------------------
        # Goals Markets
        # -----------------------------

        if total_xg >= 1.60:
            markets.append((
                "Over 1.5",
                min(98, total_xg * 28)
            ))

        if total_xg >= 2.35:
            markets.append((
                "Over 2.5",
                min(95, total_xg * 24)
            ))

        if total_xg >= 3.20:
            markets.append((
                "Over 3.5",
                min(90, total_xg * 18)
            ))

        if total_xg <= 2.40:
            markets.append((
                "Under 2.5",
                70 + (2.5 - total_xg) * 10
            ))

        # -----------------------------
        # BTTS
        # -----------------------------

        if (
            prediction.home_xg >= 0.90 and
            prediction.away_xg >= 0.90
        ):

            markets.append((
                "Both Teams To Score",
                72 + total_xg * 5
            ))

        # -----------------------------
        # Combo Markets
        # -----------------------------

        if (
            home >= 55 and
            total_xg >= 2.10
        ):

            markets.append((
                "Home or Over 1.5",
                min(99, home + 18)
            ))

        if (
            away >= 55 and
            total_xg >= 2.10
        ):

            markets.append((
                "Away or Over 1.5",
                min(99, away + 18)
            ))

        if (
            home >= 60 and
            total_xg >= 2.60
        ):

            markets.append((
                "Home or Over 2.5",
                min(99, home + 15)
            ))

        if (
            away >= 60 and
            total_xg >= 2.60
        ):

            markets.append((
                "Away or Over 2.5",
                min(99, away + 15)
            ))

        if (
            prediction.home_xg >= 1.0 and
            prediction.away_xg >= 1.0 and
            total_xg >= 2.70
        ):

            markets.append((
                "BTTS & Over 2.5",
                78 + total_xg * 3
            ))

        # -----------------------------
        # Remove weak selections
        # -----------------------------

        markets = [

            (name, score)

            for name, score in markets

            if score >= 60

        ]

        # -----------------------------
        # Sort
        # -----------------------------

        markets.sort(
            key=lambda x: x[1],
            reverse=True
        )

        prediction.ranked_markets = markets

        if markets:

            prediction.recommended_market = markets[0][0]

            prediction.market_confidence = round(
                markets[0][1],
                1
            )

        else:

            prediction.recommended_market = "No Recommendation"

            prediction.market_confidence = 0.0

        return prediction
