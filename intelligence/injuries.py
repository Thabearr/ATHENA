import logging

logger = logging.getLogger("athena.injury_engine")

class InjuryEngine:
    def __init__(self):
        pass

    def calculate_squad_degradation(self, missing_players: list) -> dict:
        """
        Evaluates a list of absent players and calculates a total degradation score.
        1.0 represents a completely full-strength squad.
        """
        squad_integrity = 1.0
        impact_details = []

        # Impact weightings based on squad status
        importance_weights = {
            "critical": 0.12,  # Key talisman, top scorer, elite playmaker
            "key": 0.06,       # Regular undisputed starting XI player
            "rotation": 0.02,  # Bench option / squad rotation player
            "fringe": 0.00     # Minimal impact on core team metrics
        }

        for player in missing_players:
            name = player.get("name", "Unknown Player")
            role = player.get("role", "fringe").lower()
            reason = player.get("reason", "absent")

            # Get penalty weight with fallback
            penalty = importance_weights.get(role, 0.00)
            squad_integrity -= penalty

            if penalty > 0:
                impact_details.append(f"Missing {name} ({role.upper()}) due to {reason} [-{penalty}]")

        # Keep squad integrity within realistic bounds (e.g., max 40% performance hit)
        squad_integrity = max(round(squad_integrity, 2), 0.60)

        return {
            "squad_integrity_modifier": squad_integrity,
            "absences_tracked": len(missing_players),
            "tactical_impact_notes": impact_details if impact_details else ["No significant squad absences."]
        }
