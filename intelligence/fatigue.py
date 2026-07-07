import logging
from datetime import datetime
from database.database import Database

logger = logging.getLogger("athena.fatigue_engine")

class FatigueEngine:
    def __init__(self):
        self.db = Database()

    def calculate_rest_days(self, current_match_date: str, last_match_date: str) -> int:
        """
        Calculates the exact number of days between two fixture dates.
        Expects date strings formatted as YYYY-MM-DD.
        """
        if not current_match_date or not last_match_date:
            return 7  # Default to a standard full week of rest if missing data
            
        try:
            # Handle split if timestamp is attached
            date_fmt = "%Y-%m-%d"
            d1 = datetime.strptime(current_match_date.split(" ")[0], date_fmt)
            d2 = datetime.strptime(last_match_date.split(" ")[0], date_fmt)
            return abs((d1 - d2).days)
        except Exception as e:
            logger.error(f"Failed to calculate rest days interval: {e}")
            return 7

    def evaluate_squad_fatigue(self, rest_days: int, is_away: bool = False, continental_travel: bool = False) -> float:
        """
        Derives a fatigue index from 0.0 (Perfectly Fresh) to 1.0 (Critically Exhausted).
        """
        fatigue_index = 0.0

        # 1. Evaluate Rest Windows
        if rest_days <= 2:
            fatigue_index += 0.85  # Critical compression (48 hours or less)
        elif rest_days == 3:
            fatigue_index += 0.55  # Standard midweek turn-around stress
        elif rest_days == 4:
            fatigue_index += 0.25  # Borderline congestion
        else:
            fatigue_index += 0.00  # Optimal recovery (5+ days)

        # 2. Append Travel Overheads
        if is_away:
            fatigue_index += 0.05  # Standard domestic travel taxation
            if continental_travel:
                fatigue_index += 0.15  # Cross-border flights deplete physical reserves

        return min(round(fatigue_index, 2), 1.0)

    def analyze_fixture_fatigue_clash(self, home_team_id: int, away_team_id: int, current_date: str, home_last_date: str, away_last_date: str, away_has_continental_travel: bool = False) -> dict:
        """
        Compares fatigue metrics between opposing clubs ahead of kickoff.
        """
        home_rest = self.calculate_rest_days(current_date, home_last_date)
        away_rest = self.calculate_rest_days(current_date, away_last_date)

        home_fatigue = self.evaluate_squad_fatigue(home_rest, is_away=False)
        away_fatigue = self.evaluate_squad_fatigue(away_rest, is_away=True, continental_travel=away_has_continental_travel)

        return {
            "home_rest_days": home_rest,
            "away_rest_days": away_rest,
            "home_fatigue_score": home_fatigue,
            "away_fatigue_score": away_fatigue,
            "fatigue_differential": round(home_fatigue - away_fatigue, 2)  # Negative means Home is fresher
        }
