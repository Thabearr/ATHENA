def _is_valid_structural_league(self, league_name: str, league_id: int = 0) -> bool:
        # Aggressive keyword matching
        blacklist = [
            "women", "womens", "w-league", "femenino", "frauen", "feminin", 
            "u19", "u21", "youth", "friendly", "amateur", "reserve", "u23"
        ]
        name_lower = league_name.lower()
        # If any blacklist term exists, drop the fixture immediately
        if any(b in name_lower for b in blacklist):
            return False
        return True
