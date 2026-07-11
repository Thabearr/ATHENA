from models.prediction import Prediction

class RiskEngine:
    def evaluate(self, prediction: Prediction, environmental_context: dict = None) -> Prediction:
        risk = 0.0
        is_upset_alert = False
        
        # 1. Base Matchup Variance
        difference = abs(prediction.home_strength - prediction.away_strength)
        if difference < 5:
            risk += 35
        elif difference < 10:
            risk += 20
        else:
            risk += 10

        # 2. Upset Detection Matrix (Trap Games)
        if environmental_context:
            ref_impact = environmental_context.get("referee_upset_score", 0.0)
            fatigue_diff = environmental_context.get("fatigue_differential", 0.0)
            injury_mod = environmental_context.get("favorite_injury_modifier", 1.0)
            
            # If the favorite is exhausted, missing key players, AND has a strict ref
            if ref_impact > 0.20 and fatigue_diff > 0.30 and injury_mod < 0.85:
                is_upset_alert = True
                risk += 50  # Spikes the risk to immediately flag the accumulator engine

        prediction.risk_score = min(risk, 100)
        prediction.upset_alert = is_upset_alert

        return prediction
