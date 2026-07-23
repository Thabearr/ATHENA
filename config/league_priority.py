# config/league_priority.py

# Tier 1: Highest priority (Core European + Major International)
TIER_1_LEAGUES = [
    "Premier League",
    "La Liga",
    "Serie A",
    "Bundesliga",
    "Ligue 1",
    "UEFA Champions League",
    "FIFA World Cup",
    "UEFA European Championship",
    "UEFA EURO"
]

# Tier 2: Strong Coverage (Continental + Solid Leagues)
TIER_2_LEAGUES = [
    "Eredivisie",
    "Primeira Liga",
    "Süper Lig",
    "First Division A",
    "Belgian Pro League",
    "Premiership",
    "Scottish Premiership",
    "Bundesliga (Austria)",
    "Austrian Bundesliga",
    "Super League (Greece)",
    "UEFA Europa League"
]

# Tier 3: Wanted, Not Yet Live (Higher Variance)
TIER_3_LEAGUES = [
    "Super League (Switzerland)",
    "Swiss Super League",
    "Eliteserien",
    "Allsvenskan",
    "Superliga (Denmark)",
    "Danish Superliga",
    "First League (Czech Republic)",
    "HNL",
    "SuperLiga (Serbia)",
    "Ekstraklasa",
    "Liga I",
    "UEFA Europa Conference League",
    "UEFA Conference League",
    "UEFA Nations League",
    "Africa Cup of Nations"
]

def get_league_tier(league_name: str) -> int:
    """Returns the priority tier of the league (1 = highest, 3 = lowest)."""
    name_lower = league_name.lower()
    
    if any(t.lower() in name_lower for t in TIER_1_LEAGUES):
        return 1
    if any(t.lower() in name_lower for t in TIER_2_LEAGUES) or "europa" in name_lower:
        return 2
    if any(t.lower() in name_lower for t in TIER_3_LEAGUES) or "conference" in name_lower:
        return 3
    
    # Default to tier 4 for unclassified leagues
    return 4
