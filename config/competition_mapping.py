# Leagues covered by football-data.org's free tier (real, current 2025-26
# season data). Mapped from our existing API-Football league_id so both
# sources can share the same SUPPORTED_LEAGUES list without double-counting
# a competition.
FOOTBALL_DATA_ORG_MAPPING = {
    39: "PL",     # Premier League
    140: "PD",    # La Liga
    135: "SA",    # Serie A
    78: "BL1",    # Bundesliga
    61: "FL1",    # Ligue 1
    88: "DED",    # Eredivisie
    94: "PPL",    # Primeira Liga
    2: "CL",      # Champions League
    1: "WC",      # World Cup
    4: "EC",      # Euro
}
