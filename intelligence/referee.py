import logging

logger = logging.getLogger("athena.referee_engine")

class RefereeEngine:
    def __init__(self):
        pass

    def evaluate_referee_impact(self, referee_name: str, ref_stats: dict, home_style: str, away_style: str) -> dict:
        """
        Calculates how a specific referee's tendencies impact the match dynamic.
        Returns a risk modifier where higher numbers mean increased upset probability.
        """
        if not referee_name or not ref_stats:
            return {"upset_catalyst_score": 0.0, "red_card_risk": "Low"}

        avg_fouls = ref_stats.get("avg_fouls_per_game", 22.0)
        avg_cards = ref_stats.get("avg_cards_per_game", 3.5)
        red_card_ratio = ref_stats.get("red_card_ratio", 0.10)

        upset_catalyst = 0.0

        # 1. Flow Disruption (High fouls benefit the underdog by breaking momentum)
        if avg_fouls > 26.0:
            if home_style == "possession":
                upset_catalyst += 0.15
            if away_style == "possession":
                upset_catalyst += 0.15

        # 2. Card Happiness (High card variance increases red card probability)
        if avg_cards > 5.0 or red_card_ratio > 0.25:
            upset_catalyst += 0.25  # High risk of a red card ruining the favorite

        red_risk = "Critical" if red_card_ratio > 0.25 else "Moderate" if red_card_ratio > 0.15 else "Low"

        return {
            "referee_name": referee_name,
            "upset_catalyst_score": min(upset_catalyst, 1.0),
            "red_card_risk": red_risk
        }
