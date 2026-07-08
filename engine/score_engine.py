class ScoreEngine:

    def expected_goals(self, home_strength, away_strength):
        """
        Estimate expected goals from relative team strength.
        This is a temporary model that will later be replaced
        by Poisson + Dixon-Coles + xG.
        """

        difference = home_strength - away_strength

        home_xg = 1.50 + (difference * 0.04)
        away_xg = 1.20 - (difference * 0.03)

        home_xg = max(0.20, min(home_xg, 4.50))
        away_xg = max(0.20, min(away_xg, 4.50))

        return {
            "home_xg": round(home_xg, 2),
            "away_xg": round(away_xg, 2)
        }

    def expected_total_goals(self, home_strength, away_strength):

        goals = self.expected_goals(
            home_strength,
            away_strength
        )

        return round(
            goals["home_xg"] + goals["away_xg"],
            2
        )
