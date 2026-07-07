from dataclasses import dataclass, field
from typing import List


@dataclass
class Prediction:

    fixture_id: int

    league: str

    home_team: str
    away_team: str

    home_form: float = 0.0
    away_form: float = 0.0

    home_strength: float = 0.0
    away_strength: float = 0.0

    predicted_home_goals: float = 0.0
    predicted_away_goals: float = 0.0

    home_win_probability: float = 0.0
    draw_probability: float = 0.0
    away_win_probability: float = 0.0

    confidence: float = 0.0
    risk_score: float = 0.0

    recommended_market: str = ""

    reasons: List[str] = field(default_factory=list)
