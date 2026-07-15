import logging
from datetime import datetime

logger = logging.getLogger("athena.fatigue_engine")

class FatigueEngine:
    def __init__(self):
        pass

    def _parse_date(self, date_string: str) -> datetime:
        if not date_string:
            return None

        try:
            cleaned = date_string.strip()

            if 'T' in cleaned:
                if '+' in cleaned:
                    cleaned = cleaned.split('+')[0]
                if cleaned.endswith('Z'):
                    cleaned = cleaned[:-1]
                if '.' in cleaned:
                    cleaned = cleaned.split('.')[0]

                return datetime.strptime(cleaned, "%Y-%m-%dT%H:%M:%S")
            else:
                return datetime.strptime(cleaned.split()[0], "%Y-%m-%d")

        except Exception as e:
            logger.error(f"Failed to parse date '{date_string}': {e}")
            return None

    def analyze_fixture_fatigue_clash(self, home_team_id: int, away_team_id: int, current_date: str,
                                       home_last_date: str = None, away_last_date: str = None) -> dict:
        """
        Calculates real rest-day differentials between the two teams, using
        each team's actual last match date. If we don't have a real last
        match date for a team (no_data), we report that honestly instead
        of guessing — no fatigue penalty/bonus gets applied for that side.
        """
        current_dt = self._parse_date(current_date)
        home_last_dt = self._parse_date(home_last_date)
        away_last_dt = self._parse_date(away_last_date)

        if current_dt is None:
            return {
                "home_rest_days": None,
                "away_rest_days": None,
                "fatigue_differential": 0.0,
                "has_data": False,
            }

        home_rest_days = max((current_dt - home_last_dt).days, 0) if home_last_dt else None
        away_rest_days = max((current_dt - away_last_dt).days, 0) if away_last_dt else None

        if home_rest_days is None or away_rest_days is None:
            return {
                "home_rest_days": home_rest_days,
                "away_rest_days": away_rest_days,
                "fatigue_differential": 0.0,
                "has_data": False,
            }

        fatigue_differential = home_rest_days - away_rest_days

        modifier = 0.0
        if fatigue_differential < -2:
            modifier = 0.30
        elif fatigue_differential < 0:
            modifier = 0.10

        return {
            "home_rest_days": home_rest_days,
            "away_rest_days": away_rest_days,
            "fatigue_differential": modifier,
            "has_data": True,
        }
