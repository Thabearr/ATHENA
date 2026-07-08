class ScoreEngine:
    """
    Estimates expected goals for both teams.
    This is ATHENA's first xG approximation before
    Poisson and Dixon-Coles are introduced.
    """

    def calculate(self, home_strength, away_strength):

        difference = home_strength - away_strength

        # Base goals
        home_goals = 1.40
        away_goals = 1.10

        # Strength adjustment
        home_goals += difference * 0.045
        away_goals -= difference * 0.035

        # Clamp values
        home_goals = max(0.2, min(5.0, home_goals))
        away_goals = max(0.2, min(5.0, away_goals))

        return {
            "home_xg": round(home_goals, 2),
            "away_xg": round(away_goals, 2),
            "total_xg": round(home_goals + away_goals, 2)
        }
