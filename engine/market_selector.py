from models.prediction import Prediction


class MarketSelector:
    """
    ATHENA Market Intelligence Engine v1

    Scores every supported betting market and ranks them.
    """

    def select(self, prediction: Prediction):

        scores = {}

        home = prediction.home_win_probability
        draw = prediction.draw_probability
        away = prediction.away_win_probability

        xg = prediction.expected_goals

        # ============================================
        # TO QUALIFY
        # ============================================

        scores["To Qualify - Home"] = home
        scores["To Qualify - Away"] = away

        # ============================================
        # OVER / UNDER
        # ============================================

        scores["Over 0.5"] = min(99, xg * 40)

        scores["Over 1.5"] = min(99, xg * 30)

        scores["Over 2.5"] = min(99, xg * 22)

        scores["Over 3.5"] = max(0, (xg - 1.5) * 25)

        scores["Over 4.5"] = max(0, (xg - 2.5) * 20)

        scores["Over 5.5"] = max(0, (xg - 3.5) * 15)

        # ============================================
        # DOUBLE CHANCE
        # ============================================

        scores["Home or Draw"] = home + draw

        scores["Draw or Away"] = draw + away

        scores["Home or Away"] = home + away

        # ============================================
        # DRAW / HOME / AWAY + OVER 2.5
        # ============================================

        over25 = scores["Over 2.5"]

        scores["Home Team or Over 2.5"] = (
            home + over25
        ) / 2

        scores["Away Team or Over 2.5"] = (
            away + over25
        ) / 2

        scores["Draw or Over 2.5"] = (
            draw + over25
        ) / 2

        # ============================================
        # GG / NG
        # ============================================

        if prediction.home_xg > 0.8 and prediction.away_xg > 0.8:
            scores["GG Yes"] = 82
            scores["GG No"] = 18
        else:
            scores["GG Yes"] = 40
            scores["GG No"] = 60

        # ============================================
        # WIN EITHER HALF
        # ============================================

        scores["Home Team to Win Either Half"] = min(
            99,
            home + 15
        )

        scores["Away Team to Win Either Half"] = min(
            99,
            away + 15
        )

        # ============================================
        # WIN TO NIL
        # ============================================

        scores["Home Team Win To Nil"] = max(
            0,
            home - prediction.away_xg * 15
        )

        scores["Away Team Win To Nil"] = max(
            0,
            away - prediction.home_xg * 15
        )

        # ============================================
        # DRAW NO BET
        # ============================================

        scores["Draw No Bet Home"] = home

        scores["Draw No Bet Away"] = away

        # ============================================
        # ASIAN HANDICAP
        # ============================================

        scores["Home -0.5"] = home

        scores["Away +0.5"] = away + draw

        scores["Home -1.0"] = max(0, home - 8)

        scores["Away +1.0"] = min(99, away + draw + 5)

        scores["Home -1.5"] = max(0, home - 15)

        scores["Away +1.5"] = min(99, away + draw + 8)

        scores["Home -2.0"] = max(0, home - 20)

        scores["Away +2.0"] = min(99, away + draw + 10)

        scores["Home -2.5"] = max(0, home - 25)

        scores["Away +2.5"] = min(99, away + draw + 12)

        scores["Home -3.0"] = max(0, home - 30)

        scores["Away +3.0"] = min(99, away + draw + 15)

        scores["Home -3.5"] = max(0, home - 35)

        scores["Away +3.5"] = min(99, away + draw + 18)

        # ============================================
        # 1UP / 2UP
        # ============================================

        scores["1UP Home"] = home
        scores["1UP Draw"] = draw
        scores["1UP Away"] = away

        scores["2UP Home"] = home
        scores["2UP Draw"] = draw
        scores["2UP Away"] = away

        # ============================================
        # SORT
        # ============================================

        ranked = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        prediction.market_scores = scores

        prediction.ranked_markets = ranked

        prediction.recommended_market = ranked[0][0]

        prediction.market_confidence = round(
            ranked[0][1],
            1
        )

        return prediction
