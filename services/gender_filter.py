"""
ATHENA Gender & Women's Match Filter Service
Ensures zero women's matches leak into the male accumulator analysis pipeline.
"""
import re
from typing import Dict, Any

WOMEN_KEYWORDS = [
    r"\bwomen\b", r"\bwfc\b", r"\bfem\b", r"femenin", r"femení", r"femenina", r"femenino",
    r"\bfrauen\b", r"\bdames\b", r"\bfemmes\b", r"\bnwsl\b", r"\bwsl\b", r"liga f\b",
    r"w-league\b", r"kvinna", r"kvinnor", r"damallsvenskan", r"uwcl",
    r"women's", r"\(w\)", r"\b\(w\)\b", r" w$", r" wfc$"
]

_WOMEN_REGEX = re.compile("|".join(WOMEN_KEYWORDS), re.IGNORECASE)

def is_womens_fixture(league: str = "", home_team: str = "", away_team: str = "") -> bool:
    """
    Returns True if the league name, home team, or away team matches any women's keywords.
    """
    combined = f"{league} {home_team} {away_team}"
    return bool(_WOMEN_REGEX.search(combined))

def filter_mens_fixtures_only(fixtures: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """
    Filters out any fixtures that are identified as women's matches.
    """
    valid = []
    for f in fixtures:
        league = f.get("league", "")
        home = f.get("home_team", "")
        away = f.get("away_team", "")
        if not is_womens_fixture(league, home, away):
            valid.append(f)
    return valid
