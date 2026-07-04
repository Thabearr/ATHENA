from dataclasses import dataclass
from datetime import datetime


@dataclass
class Fixture:
    fixture_id: int
    league: str
    league_id: int

    home_team: str
    away_team: str

    home_team_id: int
    away_team_id: int

    kickoff: datetime

    venue: str

    status: str
