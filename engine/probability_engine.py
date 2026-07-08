from models.prediction import Prediction


class ProbabilityEngine:
    """
    ATHENA Probability Engine v2

    Uses:
    - Team Strength
    - Expected Goals
    - Home Advantage

    Produces realistic Home/Draw/Away probabilities
    that always sum to 100%.
    """

    def calculate(self, prediction: Prediction):

        home_strength = prediction.home_strength
        away_strength = prediction.away_strength

        total_strength = home_strength + away_strength

        if total_strength <= 0:
            return prediction

        # ----------------------------------------
        # Base strength probabilities
        # ----------------------------------------

        home = (home_strength / total_strength) * 100
        away = (away_strength / total_strength) * 100

        # ----------------------------------------
        # Draw probability
        # ----------------------------------------

        difference = abs(home_strength - away_strength)

        if difference <= 3:
            draw = 28

        elif difference <= 7:
            draw = 24

        elif difference <= 12:
            draw = 20

        elif difference <= 18:
            draw = 16

        else:
            draw = 12

        # High expected goals reduce draw chance

        total_xg = prediction.expected_goals

        if total_xg >= 3.5:
            draw -= 4

        elif total_xg >= 3.0:
            draw -= 2

        elif total_xg <= 2.0:
            draw += 3

        draw = max(8, min(draw, 35))

        # ----------------------------------------
        # Redistribute remaining probability
        # ----------------------------------------

        remaining = 100 - draw

        home_share = home_strength / total_strength
        away_share = away_strength / total_strength

        home = remaining * home_share
        away = remaining * away_share

        # ----------------------------------------
        # Home advantage
        # ----------------------------------------

        home += 2
        away -= 2

        # Clamp values

        home = max(1, home)
        away = max(1, away)

        # ----------------------------------------
        # Normalize
        # ----------------------------------------

        total = home + draw + away

        prediction.home_win_probability = round(
            home / total * 100,
            1
        )

        prediction.draw_probability = round(
            draw / total * 100,
            1
        )

        prediction.away_win_probability = round(
            away / total * 100,
            1
        )

        return prediction
