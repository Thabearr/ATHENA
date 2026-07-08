class TeamStrengthEngine:

    def calculate(self, team_stats):

        strength = 50

        # League Position
        if team_stats.get("position", 20) <= 4:
            strength += 20

        elif team_stats.get("position", 20) <= 8:
            strength += 12

        elif team_stats.get("position", 20) <= 12:
            strength += 5

        # Recent Form
        strength += team_stats.get("form_points", 0)

        # Goal Difference
        strength += team_stats.get("goal_difference", 0) * 0.3

        # Goals Scored
        strength += team_stats.get("goals_scored", 0) * 0.2

        # Goals Conceded
        strength -= team_stats.get("goals_conceded", 0) * 0.2

        return max(1, min(100, strength))
