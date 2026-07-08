from dataclasses import dataclass, field
from typing import List


@dataclass
class Prediction:

    # -----------------------------
    # Fixture Information
    # -----------------------------

    fixture_id: int

    league: str

    home_team: str
    away_team: str

    # -----------------------------
    # Team Analysis
    # -----------------------------

    home_form: float = 0.0
    away_form: float = 0.0

    home_strength: float = 0.0
    away_strength: float = 0.0

    home_position: int = 0
    away_position: int = 0

    # -----------------------------
    # Expected Goals
    # -----------------------------

    home_xg: float = 0.0
    away_xg: float = 0.0

    expected_goals: float = 0.0

    predicted_home_goals: float = 0.0
    predicted_away_goals: float = 0.0

    # -----------------------------
    # Match Probabilities
    # -----------------------------

    home_win_probability: float = 0.0
    draw_probability: float = 0.0
    away_win_probability: float = 0.0

    # -----------------------------
    # Engine Scores
    # -----------------------------

    confidence: float = 0.0
    risk_score: float = 0.0

    # -----------------------------
    # Market Selection
    # -----------------------------

    recommended_market: str = ""

    market_confidence: float = 0.0

    # Future:
    # [
    #   ("Home or Over 2.5",96),
    #   ("Over 2.5",92),
    #   ...
    # ]
    ranked_markets: List = field(default_factory=list)

    # -----------------------------
    # Explainability
    # -----------------------------

    reasons: List[str] = field(default_factory=list)
