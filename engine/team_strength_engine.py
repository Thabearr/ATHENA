class TeamStrengthEngine:

    BASE_STRENGTH = 50

    def calculate(self, team_stats):

        strength = self.BASE_STRENGTH

        # League Position
        position = team_stats.get("position", 20)

        if position <= 4:
            strength += 20
        elif position <= 8:
            strength += 12
        elif position <= 12:
            strength += 5

        # Recent Form (last 5 matches)
        strength += team_stats.get("form_points", 0)

        # Goal Difference
        strength += team_stats.get("goal_difference", 0) * 0.30

        # Goals Scored
        strength += team_stats.get("goals_scored", 0) * 0.20

        # Defensive Strength
        strength -= team_stats.get("goals_conceded", 0) * 0.20

        # Home / Away bonus
        if team_stats.get("is_home", False):
            strength += 5

        # Clean Sheet Bonus
        strength += team_stats.get("clean_sheets", 0) * 0.50

        # Clamp between 1 and 100
        strength = max(1, min(100, strength))

        return round(strength, 2)
