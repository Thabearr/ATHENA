from dataclasses import dataclass


@dataclass
class Prediction:

    fixture_id: int

    home_team: str
    away_team: str

    home_strength: float
    away_strength: float

    home_form: float
    away_form: float

    predicted_home_goals: float
    predicted_away_goals: float

    win_probability: float
    draw_probability: float
    away_probability: float

    confidence: float

    recommended_market: str
