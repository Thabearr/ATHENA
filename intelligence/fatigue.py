import logging
from datetime import datetime

logger = logging.getLogger("athena.fatigue_engine")

class FatigueEngine:
    def __init__(self):
        pass

    def _parse_date(self, date_string: str) -> datetime:
        """
        Robustly parses date strings, stripping timezone offsets
        (both '+00:00' style and trailing 'Z' UTC suffix) to prevent
        'unconverted data remains' errors.
        """
        if not date_string:
            return datetime.now()

        try:
            cleaned = date_string.strip()

            if 'T' in cleaned:
                if '+' in cleaned:
                    cleaned = cleaned.split('+')[0]
                if cleaned.endswith('Z'):
                    cleaned = cleaned[:-1]
                # Some sources include fractional seconds — drop them too
                if '.' in cleaned:
                    cleaned = cleaned.split('.')[0]

                return datetime.strptime(cleaned, "%Y-%m-%dT%H:%M:%S")
            else:
                return datetime.strptime(cleaned.split()[0], "%Y-%m-%d")

        except Exception as e:
            logger.error(f"Failed to parse date '{date_string}': {e}")
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

        fatigue_differential = home_rest_days - away_rest_days

        modifier = 0.0
        if fatigue_differential < -2:
            modifier = 0.30
        elif fatigue_differential < 0:
            modifier = 0.10

        return {
            "home_rest_days": home_rest_days,
            "away_rest_days": away_rest_days,
            "fatigue_differential": modifier
        }
