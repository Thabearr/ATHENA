import logging
from database.database import Database

logger = logging.getLogger("athena.motivation_engine")

class MotivationEngine:
    def __init__(self):
        self.db = Database()

    def evaluate_situational_motivation(self, team_id: int, league_id: int, season: int, current_position: int, total_teams: int) -> dict:
        """
        Calculates a numeric motivation coefficient based on proximity to 
        critical structural milestones (Title, Promotion, Relegation).
        Returns a score between 0.0 (Dead rubber) and 1.0 (Maximum jeopardy).
        """
        # Default baseline motivation (neutral mid-table game)
        motivation_score = 0.5
        context = "Mid-Table Neutral"

        if not current_position or not total_teams:
            return {"score": motivation_score, "context": "Unknown/Baseline"}

        # 1. Title/Championship Jeopardy (Positions 1 - 2)
        if current_position <= 2:
            motivation_score = 0.95
            context = "Title Race / Automatic Promotion Fight"
        
        # 2. Continental / Playoff Contenders (Positions 3 - 6 depending on league size)
        elif 3 <= current_position <= 6:
            motivation_score = 0.85
            context = "European Spot / Promotional Playoff Push"

        # 3. Severe Relegation Jeopardy (Bottom 3 positions)
        elif current_position > (total_teams - 3):
            motivation_score = 1.00
            context = "Critical Relegation Survival Fight"

        # 4. Relegation Buffer Zone (Just above bottom 3)
        elif current_position > (total_teams - 6):
            motivation_score = 0.75
            context = "Relegation Danger Buffer Zone"

        return {
            "team_id": team_id,
            "motivation_score": round(motivation_score, 2),
            "context": context
        }

    def analyze_fixture_motivation_clash(self, fixture_data: dict, league_size: int = 20) -> dict:
        """
        Compares the motivation profiles of both teams for an upcoming fixture.
        """
        # Fallback values if explicit positions aren't provided yet
        h_pos = fixture_data.get('home_position', 10)
        a_pos = fixture_data.get('away_position', 10)
        
        home_profile = self.evaluate_situational_motivation(
            team_id=fixture_data.get('home_id'),
            league_id=fixture_data.get('league_id'),
            season=fixture_data.get('season'),
            current_position=h_pos,
            total_teams=league_size
        )
        
        away_profile = self.evaluate_situational_motivation(
            team_id=fixture_data.get('away_id'),
            league_id=fixture_data.get('league_id'),
            season=fixture_data.get('season'),
            current_position=a_pos,
            total_teams=league_size
        )

        # Calculate absolute motivation differential
        differential = home_profile["motivation_score"] - away_profile["motivation_score"]

        return {
            "home_motivation": home_profile["motivation_score"],
            "home_context": home_profile["context"],
            "away_motivation": away_profile["motivation_score"],
            "away_context": away_profile["context"],
            "motivation_differential": round(differential, 2)
        }
