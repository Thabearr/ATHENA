from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Prediction:

    # =====================================================
    # Fixture Information
    # =====================================================

    fixture_id: int

    league: str

    home_team: str
    away_team: str

    # =====================================================
    # Team Analysis
    # =====================================================

    home_form: float = 0.0
    away_form: float = 0.0

    home_strength: float = 0.0
    away_strength: float = 0.0

    home_position: int = 0
    away_position: int = 0

    # =====================================================
    # Expected Goals
    # =====================================================

    home_xg: float = 0.0
    away_xg: float = 0.0

    expected_goals: float = 0.0

    predicted_home_goals: float = 0.0
    predicted_away_goals: float = 0.0

    # =====================================================
    # Match Probabilities
    # =====================================================

    home_win_probability: float = 0.0
    draw_probability: float = 0.0
    away_win_probability: float = 0.0

    # =====================================================
    # Engine Scores
    # =====================================================

    confidence: float = 0.0
    risk_score: float = 0.0
    reliability: float = 0.0

    # =====================================================
    # Betting Markets
    # =====================================================

    recommended_market: str = ""
    market_confidence: float = 0.0

    # Every supported betting market
    market_scores: Dict[str, float] = field(default_factory=dict)

    # Highest ranked markets
    ranked_markets: List = field(default_factory=list)

    # =====================================================
    # Individual Market Confidence
    # =====================================================

    over05: float = 0.0
    over15: float = 0.0
    over25: float = 0.0
    over35: float = 0.0
    over45: float = 0.0
    over55: float = 0.0

    gg_yes: float = 0.0
    gg_no: float = 0.0

    home_or_draw: float = 0.0
    away_or_draw: float = 0.0
    home_or_away: float = 0.0

    draw_no_bet_home: float = 0.0
    draw_no_bet_away: float = 0.0

    home_or_over25: float = 0.0
    away_or_over25: float = 0.0
    draw_or_over25: float = 0.0

    home_win_either_half: float = 0.0
    away_win_either_half: float = 0.0

    home_win_to_nil: float = 0.0
    away_win_to_nil: float = 0.0

    handicap_home_minus05: float = 0.0
    handicap_home_minus10: float = 0.0
    handicap_home_minus15: float = 0.0
    handicap_home_minus20: float = 0.0
    handicap_home_minus25: float = 0.0
    handicap_home_minus30: float = 0.0
    handicap_home_minus35: float = 0.0

    handicap_away_plus05: float = 0.0
    handicap_away_plus10: float = 0.0
    handicap_away_plus15: float = 0.0
    handicap_away_plus20: float = 0.0
    handicap_away_plus25: float = 0.0
    handicap_away_plus30: float = 0.0
    handicap_away_plus35: float = 0.0

    qualify_home: float = 0.0
    qualify_away: float = 0.0

    oneup_home: float = 0.0
    oneup_draw: float = 0.0
    oneup_away: float = 0.0

    twoup_home: float = 0.0
    twoup_draw: float = 0.0
    twoup_away: float = 0.0

    # =====================================================
    # Explainability
    # =====================================================

    reasons: List[str] = field(default_factory=list)
