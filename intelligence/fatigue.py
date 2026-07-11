import logging
from datetime import datetime

logger = logging.getLogger("athena.fatigue_engine")

class FatigueEngine:
    def __init__(self):
        pass

    def _parse_date(self, date_string: str) -> datetime:
        """
        Robustly parses date strings, stripping timezone offsets 
        to prevent 'unconverted data remains' errors.
        """
        if not date_string:
            return datetime.now()
            
        try:
            # If there is a 'T' and a '+', strip the timezone info
            if 'T' in date_string and '+' in date_string:
                date_string = date_string.split('+')[0]
                
            # Now parse the clean ISO string
            if 'T' in date_string:
                return datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S")
            else:
                # Fallback for standard SQL strings
                return datetime.strptime(date_string.split()[0], "%Y-%m-%d")
                
        except Exception as e:
            logger.error(f"Failed to parse date '{date_string}': {e}")
            # Fallback to current time so the engine doesn't crash the entire pipeline
            return datetime.now()

    def analyze_fixture_fatigue_clash(self, home_team_id: int, away_team_id: int, current_date: str, home_last_date: str, away_last_date: str) -> dict:
        """
        Calculates rest differentials.
        """
        current_dt = self._parse_date(current_date)
        home_last_dt = self._parse_date(home_last_date)
        away_last_dt = self._parse_date(away_last_date)
        
        home_rest_days = max((current_dt - home_last_dt).days, 0)
        away_rest_days = max((current_dt - away_last_dt).days, 0)
        
        # Calculate differential. If home had 5 days rest and away had 2, differential is +3 for home.
        fatigue_differential = home_rest_days - away_rest_days
        
        # Normalize the differential to a 0.0 - 1.0 modifier for the risk engine
        # Negative numbers mean the favorite is more fatigued than the underdog
        modifier = 0.0
        if fatigue_differential < -2:
            modifier = 0.30 # High fatigue penalty
        elif fatigue_differential < 0:
            modifier = 0.10 # Slight penalty
            
        return {
            "home_rest_days": home_rest_days,
            "away_rest_days": away_rest_days,
            "fatigue_differential": modifier
        }
