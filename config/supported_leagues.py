SUPPORTED_LEAGUES = {

    # England
    39,

    # Spain
    140,

    # Italy
    135,

    # Germany
    78,

    # France
    61,

    # Netherlands
    88,

    # Portugal
    94,

    # Turkey
    203,

    # Belgium
    144,

    # Switzerland
    207,

    # Scotland
    179,

    # Norway
    103,

    # Sweden
    113,

    # Denmark
    119,

    # Austria
    218,

    # Greece
    197,

    # Czech Republic
    345,

    # Croatia
    210,

    # Serbia
    286,

    # Poland
    106,

    # Romania
    283,

    # UEFA Champions League
    2,

    # Europa League
    3,

    # Europa Conference League
    848,

    # World Cup
    1,

    # EURO
    4,

    # Nations League
    5,

    # AFCON
    6

}

# Tournaments that use INTERNATIONAL_SEASON instead of CURRENT_SEASON
INTERNATIONAL_LEAGUE_IDS = {1, 4, 5, 6}


def season_for_league(league_id: int, settings) -> int:
    if league_id in INTERNATIONAL_LEAGUE_IDS:
        return settings.INTERNATIONAL_SEASON
    return settings.CURRENT_SEASON
