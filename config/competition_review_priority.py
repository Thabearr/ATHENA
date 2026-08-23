"""ATHENA Football Competition Hierarchy v1.0 for accumulator review order.

The hierarchy controls where ATHENA looks first. It never creates model,
pricing, selection, execution or BET authority. Club and international football
have separate rank spaces and must not be mechanically compared.

Source-qualified matching remains strict whenever provider country/name metadata
is available. Canonical internal matching is exact normalized-alias matching and
is intended only for already-reviewed internal competition identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from config.league_priority import normalize_league_name


COMPETITION_REVIEW_PRIORITY_POLICY_VERSION = "athena-competition-review-priority-v2"
COMPETITION_REVIEW_PRIORITY_BASIS = "ATHENA_FOOTBALL_COMPETITION_HIERARCHY_V1"
UNPRIORITIZED_COMPETITION_TIER = 99
UNPRIORITIZED_COMPETITION_RANK = 999


class CompetitionScope(str, Enum):
    CLUB = "CLUB"
    INTERNATIONAL = "INTERNATIONAL"


class CompetitionKind(str, Enum):
    DOMESTIC_LEAGUE = "DOMESTIC_LEAGUE"
    DOMESTIC_CUP = "DOMESTIC_CUP"
    CONTINENTAL_CLUB_CUP = "CONTINENTAL_CLUB_CUP"
    INTERNATIONAL_TOURNAMENT = "INTERNATIONAL_TOURNAMENT"
    INTERNATIONAL_QUALIFIER = "INTERNATIONAL_QUALIFIER"
    INTERNATIONAL_NATIONS_LEAGUE = "INTERNATIONAL_NATIONS_LEAGUE"
    INTERNATIONAL_FRIENDLY = "INTERNATIONAL_FRIENDLY"
    INTERNATIONAL_YOUTH = "INTERNATIONAL_YOUTH"


@dataclass(frozen=True)
class SourceCompetitionIdentity:
    ccode: str
    source_name: str


@dataclass(frozen=True)
class CompetitionReviewPriorityEntry:
    canonical_name: str
    scope: CompetitionScope
    kind: CompetitionKind
    tier: int
    priority_band: str
    base_score: int
    rank: int
    source_identities: tuple[SourceCompetitionIdentity, ...]
    aliases: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class StagePriorityAdjustment:
    base_tier: int
    effective_tier: int
    base_band: str
    effective_band: str
    band_delta: int
    reason: str | None
    confidence_focus: bool


CLUB_TIER_TO_BAND = {
    1: "S",
    2: "A",
    3: "B",
    4: "C1",
    5: "C2",
    6: "D",
    7: "E",
    8: "F",
    9: "G",
}


def _club(
    name: str,
    kind: CompetitionKind,
    tier: int,
    score: int,
    rank: int,
    source: tuple[SourceCompetitionIdentity, ...] = (),
    aliases: tuple[str, ...] = (),
    rationale: str = "",
) -> CompetitionReviewPriorityEntry:
    return CompetitionReviewPriorityEntry(
        canonical_name=name,
        scope=CompetitionScope.CLUB,
        kind=kind,
        tier=tier,
        priority_band=CLUB_TIER_TO_BAND[tier],
        base_score=score,
        rank=rank,
        source_identities=source,
        aliases=aliases,
        rationale=rationale,
    )


def _intl(
    name: str,
    tier: int,
    band: str,
    rank: int,
    kind: CompetitionKind,
    aliases: tuple[str, ...] = (),
) -> CompetitionReviewPriorityEntry:
    return CompetitionReviewPriorityEntry(
        canonical_name=name,
        scope=CompetitionScope.INTERNATIONAL,
        kind=kind,
        tier=tier,
        priority_band=band,
        base_score=0,
        rank=rank,
        source_identities=(),
        aliases=aliases,
        rationale="International hierarchy v1.0; separate from club ranks.",
    )


# PDF v1.0 club order:
# S UEFA -> A Big Five -> B Big Five cups -> C1 -> C2 -> D Championship
# -> E MLS -> F Saudi -> G other explicitly approved leagues.
#
# Exact FotMob source identities below are literal reviewed pairs only. Generic
# same-name competitions in another country never inherit priority. The three
# UEFA root pairs and Saudi pair are preserved source literals observed in the
# existing ATHENA evidence archive; stage/wrapper variants are not inferred.
#
# Scottish Premiership is retained only as Tier G. It already exists in ATHENA's
# historical approved competition registry, but the attached hierarchy does not
# place it in C1/C2. This keeps it available without silently restoring its older
# higher review rank.
DEFAULT_COMPETITION_REVIEW_PRIORITY: tuple[CompetitionReviewPriorityEntry, ...] = (
    _club(
        "UEFA Champions League",
        CompetitionKind.CONTINENTAL_CLUB_CUP,
        1,
        100,
        1,
        (SourceCompetitionIdentity("INT", "Champions League"),),
        ("Champions League",),
    ),
    _club(
        "UEFA Europa League",
        CompetitionKind.CONTINENTAL_CLUB_CUP,
        1,
        100,
        2,
        (SourceCompetitionIdentity("INT", "Europa League"),),
        ("Europa League",),
    ),
    _club(
        "UEFA Conference League",
        CompetitionKind.CONTINENTAL_CLUB_CUP,
        1,
        100,
        3,
        (SourceCompetitionIdentity("INT", "Conference League"),),
        ("UEFA Europa Conference League", "Conference League"),
    ),
    _club(
        "Premier League",
        CompetitionKind.DOMESTIC_LEAGUE,
        2,
        88,
        10,
        (SourceCompetitionIdentity("ENG", "Premier League"),),
        ("English Premier League", "England Premier League"),
    ),
    _club(
        "La Liga",
        CompetitionKind.DOMESTIC_LEAGUE,
        2,
        86,
        11,
        (
            SourceCompetitionIdentity("ESP", "LaLiga"),
            SourceCompetitionIdentity("ESP", "La Liga"),
        ),
        ("LaLiga", "Primera Division"),
    ),
    _club(
        "Serie A",
        CompetitionKind.DOMESTIC_LEAGUE,
        2,
        84,
        12,
        (SourceCompetitionIdentity("ITA", "Serie A"),),
    ),
    _club(
        "Bundesliga",
        CompetitionKind.DOMESTIC_LEAGUE,
        2,
        82,
        13,
        (SourceCompetitionIdentity("GER", "Bundesliga"),),
        ("German Bundesliga",),
    ),
    _club(
        "Ligue 1",
        CompetitionKind.DOMESTIC_LEAGUE,
        2,
        80,
        14,
        (SourceCompetitionIdentity("FRA", "Ligue 1"),),
    ),
    _club(
        "FA Cup",
        CompetitionKind.DOMESTIC_CUP,
        3,
        78,
        20,
        (SourceCompetitionIdentity("ENG", "FA Cup"),),
    ),
    _club(
        "EFL Cup",
        CompetitionKind.DOMESTIC_CUP,
        3,
        78,
        20,
        (
            SourceCompetitionIdentity("ENG", "EFL Cup"),
            SourceCompetitionIdentity("ENG", "League Cup"),
        ),
        ("League Cup", "Carabao Cup"),
    ),
    _club(
        "Copa del Rey",
        CompetitionKind.DOMESTIC_CUP,
        3,
        78,
        20,
        (SourceCompetitionIdentity("ESP", "Copa del Rey"),),
    ),
    _club(
        "Coppa Italia",
        CompetitionKind.DOMESTIC_CUP,
        3,
        78,
        20,
        (SourceCompetitionIdentity("ITA", "Coppa Italia"),),
    ),
    _club(
        "DFB-Pokal",
        CompetitionKind.DOMESTIC_CUP,
        3,
        78,
        20,
        (
            SourceCompetitionIdentity("GER", "DFB Pokal"),
            SourceCompetitionIdentity("GER", "DFB-Pokal"),
        ),
        ("DFB Pokal",),
    ),
    _club(
        "Coupe de France",
        CompetitionKind.DOMESTIC_CUP,
        3,
        78,
        20,
        (SourceCompetitionIdentity("FRA", "Coupe de France"),),
    ),
    _club(
        "Eredivisie",
        CompetitionKind.DOMESTIC_LEAGUE,
        4,
        76,
        30,
        (SourceCompetitionIdentity("NED", "Eredivisie"),),
    ),
    _club(
        "Primeira Liga",
        CompetitionKind.DOMESTIC_LEAGUE,
        4,
        74,
        31,
        (
            SourceCompetitionIdentity("POR", "Liga Portugal"),
            SourceCompetitionIdentity("POR", "Primeira Liga"),
        ),
        ("Liga Portugal",),
    ),
    _club(
        "Süper Lig",
        CompetitionKind.DOMESTIC_LEAGUE,
        4,
        72,
        32,
        (
            SourceCompetitionIdentity("TUR", "Super Lig"),
            SourceCompetitionIdentity("TUR", "Süper Lig"),
        ),
        ("Super Lig",),
    ),
    _club(
        "Belgian Pro League",
        CompetitionKind.DOMESTIC_LEAGUE,
        4,
        70,
        33,
        (
            SourceCompetitionIdentity("BEL", "Belgian Pro League"),
            SourceCompetitionIdentity("BEL", "First Division A"),
        ),
        ("First Division A", "Jupiler Pro League"),
    ),
    _club(
        "Eliteserien",
        CompetitionKind.DOMESTIC_LEAGUE,
        5,
        68,
        40,
        (SourceCompetitionIdentity("NOR", "Eliteserien"),),
        ("Norway Eliteserien", "Tippeligaen"),
    ),
    _club(
        "Danish Superliga",
        CompetitionKind.DOMESTIC_LEAGUE,
        5,
        66,
        41,
        (
            SourceCompetitionIdentity("DEN", "Superliga"),
            SourceCompetitionIdentity("DEN", "Superligaen"),
        ),
        ("Superliga", "Superligaen"),
    ),
    _club(
        "Allsvenskan",
        CompetitionKind.DOMESTIC_LEAGUE,
        5,
        64,
        42,
        (SourceCompetitionIdentity("SWE", "Allsvenskan"),),
        ("Swedish Allsvenskan",),
    ),
    _club(
        "Swiss Super League",
        CompetitionKind.DOMESTIC_LEAGUE,
        5,
        62,
        43,
        (
            SourceCompetitionIdentity("SUI", "Super League"),
            SourceCompetitionIdentity("SUI", "Swiss Super League"),
        ),
        ("Swiss Superleague",),
    ),
    _club(
        "Greek Super League",
        CompetitionKind.DOMESTIC_LEAGUE,
        5,
        60,
        44,
        (
            SourceCompetitionIdentity("GRE", "Super League"),
            SourceCompetitionIdentity("GRE", "Greek Super League"),
        ),
        ("Super League Greece", "Super League 1"),
    ),
    _club(
        "EFL Championship",
        CompetitionKind.DOMESTIC_LEAGUE,
        6,
        58,
        50,
        (
            SourceCompetitionIdentity("ENG", "Championship"),
            SourceCompetitionIdentity("ENG", "EFL Championship"),
        ),
        ("Championship",),
    ),
    _club(
        "Major League Soccer",
        CompetitionKind.DOMESTIC_LEAGUE,
        7,
        54,
        60,
        (SourceCompetitionIdentity("USA", "Major League Soccer"),),
        ("MLS",),
    ),
    _club(
        "Saudi Pro League",
        CompetitionKind.DOMESTIC_LEAGUE,
        8,
        50,
        70,
        (SourceCompetitionIdentity("KSA", "Saudi Pro League"),),
        ("Saudi League", "Roshn Saudi League"),
    ),
    _club(
        "Scottish Premiership",
        CompetitionKind.DOMESTIC_LEAGUE,
        9,
        45,
        80,
        (
            SourceCompetitionIdentity("SCO", "Premiership"),
            SourceCompetitionIdentity("SCO", "Scottish Premiership"),
        ),
        ("Scotland Premiership", "Scottish Premier League"),
        "Existing reviewed historical top flight retained in Tier G only.",
    ),
)


INTERNATIONAL_COMPETITION_REVIEW_PRIORITY: tuple[
    CompetitionReviewPriorityEntry, ...
] = (
    _intl(
        "FIFA World Cup",
        1,
        "INT-S",
        1,
        CompetitionKind.INTERNATIONAL_TOURNAMENT,
        ("World Cup",),
    ),
    _intl(
        "UEFA European Championship",
        2,
        "INT-A",
        10,
        CompetitionKind.INTERNATIONAL_TOURNAMENT,
        ("Euros", "UEFA Euro", "European Championship"),
    ),
    _intl(
        "Copa America",
        2,
        "INT-A",
        11,
        CompetitionKind.INTERNATIONAL_TOURNAMENT,
        ("Copa América",),
    ),
    _intl(
        "Africa Cup of Nations",
        2,
        "INT-A",
        12,
        CompetitionKind.INTERNATIONAL_TOURNAMENT,
        ("AFCON", "African Cup of Nations"),
    ),
    _intl(
        "AFC Asian Cup",
        2,
        "INT-A",
        13,
        CompetitionKind.INTERNATIONAL_TOURNAMENT,
    ),
    _intl(
        "CONCACAF Gold Cup",
        2,
        "INT-A",
        14,
        CompetitionKind.INTERNATIONAL_TOURNAMENT,
        ("Gold Cup",),
    ),
    _intl(
        "FIFA World Cup qualification",
        3,
        "INT-B",
        20,
        CompetitionKind.INTERNATIONAL_QUALIFIER,
        ("World Cup qualification", "World Cup qualifiers"),
    ),
    _intl(
        "Continental Championship Qualification",
        4,
        "INT-C",
        30,
        CompetitionKind.INTERNATIONAL_QUALIFIER,
        ("Euro qualifiers", "AFCON qualifiers", "Asian Cup qualifiers", "Gold Cup qualification"),
    ),
    _intl(
        "Nations League",
        5,
        "INT-D",
        40,
        CompetitionKind.INTERNATIONAL_NATIONS_LEAGUE,
        ("UEFA Nations League", "CONCACAF Nations League"),
    ),
    _intl(
        "Official Secondary Senior Tournament",
        6,
        "INT-E",
        50,
        CompetitionKind.INTERNATIONAL_TOURNAMENT,
    ),
    _intl(
        "International Friendly",
        7,
        "INT-F",
        60,
        CompetitionKind.INTERNATIONAL_FRIENDLY,
        ("Friendly", "Friendlies"),
    ),
    _intl(
        "Youth / Olympic International",
        8,
        "INT-G",
        70,
        CompetitionKind.INTERNATIONAL_YOUTH,
        ("Olympic Football", "Youth International", "Age Grade International"),
    ),
)


_SOURCE_IDENTITY_TO_ENTRY: dict[
    tuple[str, str], CompetitionReviewPriorityEntry
] = {}
_CANONICAL_BY_SCOPE: dict[
    tuple[CompetitionScope, str], CompetitionReviewPriorityEntry
] = {}
for _entry in (
    *DEFAULT_COMPETITION_REVIEW_PRIORITY,
    *INTERNATIONAL_COMPETITION_REVIEW_PRIORITY,
):
    for _name in (_entry.canonical_name, *_entry.aliases):
        _key = (_entry.scope, normalize_league_name(_name))
        if not _key[1]:
            raise RuntimeError("competition hierarchy alias normalized empty")
        _existing = _CANONICAL_BY_SCOPE.get(_key)
        if _existing is not None and _existing != _entry:
            raise RuntimeError(f"ambiguous competition hierarchy alias {_name!r}")
        _CANONICAL_BY_SCOPE[_key] = _entry
    for _identity in _entry.source_identities:
        if type(_identity.ccode) is not str or not _identity.ccode:
            raise RuntimeError("competition source country code must be non-empty")
        _normalized = normalize_league_name(_identity.source_name)
        if not _normalized:
            raise RuntimeError("competition source name normalized empty")
        _key = (_identity.ccode, _normalized)
        _existing = _SOURCE_IDENTITY_TO_ENTRY.get(_key)
        if _existing is not None and _existing != _entry:
            raise RuntimeError(f"ambiguous source competition identity {_key!r}")
        _SOURCE_IDENTITY_TO_ENTRY[_key] = _entry


def resolve_source_competition_review_priority(
    ccode: object,
    source_name: object,
) -> CompetitionReviewPriorityEntry | None:
    if type(ccode) is not str or type(source_name) is not str:
        return None
    normalized = normalize_league_name(source_name)
    if not normalized:
        return None
    return _SOURCE_IDENTITY_TO_ENTRY.get((ccode, normalized))


def resolve_canonical_competition_review_priority(
    canonical_name: object,
    *,
    scope: CompetitionScope | str = CompetitionScope.CLUB,
) -> CompetitionReviewPriorityEntry | None:
    if type(canonical_name) is not str:
        return None
    try:
        scope_value = (
            scope
            if isinstance(scope, CompetitionScope)
            else CompetitionScope(str(scope).upper())
        )
    except ValueError:
        return None
    return _CANONICAL_BY_SCOPE.get(
        (scope_value, normalize_league_name(canonical_name))
    )


def apply_stage_modifier(
    entry: CompetitionReviewPriorityEntry,
    *,
    stage: object = None,
    stage_evidence_reviewed: bool = False,
    both_sides_strong_lineups_expected: bool = False,
    top_flight_rotation_expected: bool = False,
    two_leg_second_leg: bool = False,
) -> StagePriorityAdjustment:
    """Apply only the hierarchy's explicit cup stage/rotation attention rules.

    Stage evidence is ignored unless ``stage_evidence_reviewed`` is exactly true.
    The modifier changes attention order only and never eligibility or BET authority.
    """

    base_tier = entry.tier
    effective_tier = base_tier
    delta = 0
    reason = None
    confidence_focus = False

    if (
        stage_evidence_reviewed
        and entry.scope is CompetitionScope.CLUB
        and entry.kind
        in {CompetitionKind.DOMESTIC_CUP, CompetitionKind.CONTINENTAL_CLUB_CUP}
    ):
        normalized_stage = (
            normalize_league_name(stage) if isinstance(stage, str) else ""
        )
        if normalized_stage in {
            "final",
            "semi final",
            "semifinal",
            "semi finals",
            "semifinals",
        }:
            effective_tier = max(1, base_tier - 1)
            delta = 1
            reason = "FINAL_OR_SEMI_FINAL_UP_ONE_BAND"
        elif normalized_stage in {
            "quarter final",
            "quarterfinal",
            "quarter finals",
            "quarterfinals",
        }:
            if both_sides_strong_lineups_expected is True:
                effective_tier = max(1, base_tier - 1)
                delta = 1
                reason = "QUARTER_FINAL_STRONG_LINEUPS_UP_ONE_BAND"
            else:
                reason = "QUARTER_FINAL_NO_AUTOMATIC_UPGRADE"
        elif (
            normalized_stage
            in {"early round", "first round", "second round", "third round"}
            and top_flight_rotation_expected is True
        ):
            effective_tier = min(9, base_tier + 1)
            delta = -1
            reason = "EARLY_ROUND_ROTATION_DOWN_ONE_BAND"

        if two_leg_second_leg is True:
            confidence_focus = True
            reason = reason or "SECOND_LEG_CONFIDENCE_FOCUS"

    base_band = entry.priority_band
    effective_band = (
        CLUB_TIER_TO_BAND.get(effective_tier, base_band)
        if entry.scope is CompetitionScope.CLUB
        else base_band
    )
    return StagePriorityAdjustment(
        base_tier,
        effective_tier,
        base_band,
        effective_band,
        delta,
        reason,
        confidence_focus,
    )


def derive_non_big_five_domestic_cup_tier(
    parent_league: CompetitionReviewPriorityEntry,
    *,
    later_round: bool = False,
) -> int:
    """Hierarchy rule: parent league -1 band; later rounds may restore parent."""

    if (
        parent_league.scope is not CompetitionScope.CLUB
        or parent_league.kind is not CompetitionKind.DOMESTIC_LEAGUE
    ):
        raise ValueError("parent_league must be a club domestic league")
    if later_round:
        return parent_league.tier
    return min(9, parent_league.tier + 1)


__all__ = [
    "CLUB_TIER_TO_BAND",
    "COMPETITION_REVIEW_PRIORITY_BASIS",
    "COMPETITION_REVIEW_PRIORITY_POLICY_VERSION",
    "DEFAULT_COMPETITION_REVIEW_PRIORITY",
    "INTERNATIONAL_COMPETITION_REVIEW_PRIORITY",
    "UNPRIORITIZED_COMPETITION_RANK",
    "UNPRIORITIZED_COMPETITION_TIER",
    "CompetitionKind",
    "CompetitionReviewPriorityEntry",
    "CompetitionScope",
    "SourceCompetitionIdentity",
    "StagePriorityAdjustment",
    "apply_stage_modifier",
    "derive_non_big_five_domestic_cup_tier",
    "resolve_canonical_competition_review_priority",
    "resolve_source_competition_review_priority",
]
