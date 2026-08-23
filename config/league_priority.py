"""Versioned ATHENA club-competition fallback hierarchy for accumulator planning.

This registry is consideration order only. It does not make a fixture eligible,
prove model reliability, create value, or grant selection/BET authority.

The order mirrors *Athena Football Competition Hierarchy v1.0*. It is the
compatibility fallback for callers that do not preserve a source-qualified
competition identity. Exact whole-name aliases are used; substring/fuzzy
matching is forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


PRIORITY_POLICY_VERSION = "athena-league-priority-v3"
PRIORITY_BASIS = "ATHENA_FOOTBALL_COMPETITION_HIERARCHY_V1_CONSIDERATION_ORDER"
UNPRIORITIZED_TIER = 99
UNPRIORITIZED_RANK = 999


@dataclass(frozen=True)
class LeaguePriorityEntry:
    canonical_name: str
    tier: int
    rank: int
    aliases: tuple[str, ...]
    rationale: str


def normalize_league_name(value: str) -> str:
    """Normalize a label for exact alias matching, never fuzzy matching."""

    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", " ", without_marks.casefold()).strip()


# Numeric tiers mirror the PDF bands for compatibility:
# 1=S, 2=A, 3=B, 4=C1, 5=C2, 6=D, 7=E, 8=F, 9=G.
# Domestic cups live in the source-qualified competition registry rather than
# this legacy league-name fallback. Tier G contains only explicitly approved
# long-tail leagues; an arbitrary unknown league never enters Tier G by name.
DEFAULT_LEAGUE_PRIORITY: tuple[LeaguePriorityEntry, ...] = (
    LeaguePriorityEntry(
        "UEFA Champions League",
        1,
        1,
        ("UEFA Champions League", "Champions League"),
        "Tier S: first club competition reviewed under hierarchy v1.0.",
    ),
    LeaguePriorityEntry(
        "UEFA Europa League",
        1,
        2,
        ("UEFA Europa League", "Europa League"),
        "Tier S: reviewed after Champions League and before domestic football.",
    ),
    LeaguePriorityEntry(
        "UEFA Conference League",
        1,
        3,
        (
            "UEFA Conference League",
            "UEFA Europa Conference League",
            "Conference League",
        ),
        "Tier S: reviewed after Europa League and before domestic football.",
    ),
    LeaguePriorityEntry(
        "Premier League",
        2,
        10,
        ("Premier League", "English Premier League", "England Premier League"),
        "Tier A: first Big Five domestic league.",
    ),
    LeaguePriorityEntry(
        "La Liga",
        2,
        11,
        ("La Liga", "LaLiga", "Primera Division", "Spain La Liga"),
        "Tier A: second Big Five domestic league.",
    ),
    LeaguePriorityEntry(
        "Serie A",
        2,
        12,
        ("Serie A", "Italy Serie A", "Italian Serie A"),
        "Tier A: third Big Five domestic league.",
    ),
    LeaguePriorityEntry(
        "Bundesliga",
        2,
        13,
        ("Bundesliga", "German Bundesliga", "Germany Bundesliga"),
        "Tier A: fourth Big Five domestic league.",
    ),
    LeaguePriorityEntry(
        "Ligue 1",
        2,
        14,
        ("Ligue 1", "France Ligue 1", "French Ligue 1"),
        "Tier A: fifth Big Five domestic league.",
    ),
    LeaguePriorityEntry(
        "Eredivisie",
        4,
        30,
        ("Eredivisie", "Netherlands Eredivisie", "Dutch Eredivisie"),
        "Tier C1: first secondary European top flight.",
    ),
    LeaguePriorityEntry(
        "Primeira Liga",
        4,
        31,
        ("Primeira Liga", "Liga Portugal", "Portugal Primeira Liga"),
        "Tier C1: second secondary European top flight.",
    ),
    LeaguePriorityEntry(
        "Süper Lig",
        4,
        32,
        ("Süper Lig", "Super Lig", "Turkey Super Lig", "Turkish Super Lig"),
        "Tier C1: third secondary European top flight.",
    ),
    LeaguePriorityEntry(
        "Belgian Pro League",
        4,
        33,
        (
            "Belgian Pro League",
            "First Division A",
            "Jupiler Pro League",
            "Belgium First Division A",
        ),
        "Tier C1: fourth secondary European top flight.",
    ),
    LeaguePriorityEntry(
        "Eliteserien",
        5,
        40,
        ("Eliteserien", "Norway Eliteserien", "Tippeligaen"),
        "Tier C2: first preferred European top flight.",
    ),
    LeaguePriorityEntry(
        "Danish Superliga",
        5,
        41,
        ("Danish Superliga", "Superligaen", "Danish Super League"),
        "Tier C2: second preferred European top flight.",
    ),
    LeaguePriorityEntry(
        "Allsvenskan",
        5,
        42,
        ("Allsvenskan", "Swedish Allsvenskan", "Sweden Allsvenskan"),
        "Tier C2: third preferred European top flight.",
    ),
    LeaguePriorityEntry(
        "Swiss Super League",
        5,
        43,
        ("Swiss Super League", "Swiss Superleague", "Switzerland Super League"),
        "Tier C2: fourth preferred European top flight.",
    ),
    LeaguePriorityEntry(
        "Greek Super League",
        5,
        44,
        (
            "Greek Super League",
            "Super League Greece",
            "Super League (Greece)",
            "Greece Super League 1",
            "Super League 1",
        ),
        "Tier C2: fifth preferred European top flight.",
    ),
    LeaguePriorityEntry(
        "EFL Championship",
        6,
        50,
        (
            "EFL Championship",
            "Championship",
            "English Championship",
            "England Championship",
        ),
        "Tier D: first non-top-flight league in the default hierarchy.",
    ),
    LeaguePriorityEntry(
        "Major League Soccer",
        7,
        60,
        ("Major League Soccer", "MLS", "USA MLS", "United States MLS"),
        "Tier E: reviewed after the Championship.",
    ),
    LeaguePriorityEntry(
        "Saudi Pro League",
        8,
        70,
        ("Saudi Pro League", "Saudi League", "Roshn Saudi League"),
        "Tier F: reviewed after MLS.",
    ),
    LeaguePriorityEntry(
        "Scottish Premiership",
        9,
        80,
        (
            "Scottish Premiership",
            "Scotland Premiership",
            "Scottish Premier League",
        ),
        "Tier G: explicitly approved historical long-tail European top flight.",
    ),
)


_ALIAS_TO_ENTRY: dict[str, LeaguePriorityEntry] = {}
for _entry in DEFAULT_LEAGUE_PRIORITY:
    for _alias in (_entry.canonical_name, *_entry.aliases):
        _normalized = normalize_league_name(_alias)
        if not _normalized:
            raise RuntimeError("league priority aliases must not normalize to empty")
        _existing = _ALIAS_TO_ENTRY.get(_normalized)
        if _existing is not None and _existing != _entry:
            raise RuntimeError(
                f"duplicate league-priority alias {_alias!r}: "
                f"{_existing.canonical_name!r} vs {_entry.canonical_name!r}"
            )
        _ALIAS_TO_ENTRY[_normalized] = _entry


TIER_1_LEAGUES = [
    entry.canonical_name for entry in DEFAULT_LEAGUE_PRIORITY if entry.tier == 1
]
TIER_2_LEAGUES = [
    entry.canonical_name for entry in DEFAULT_LEAGUE_PRIORITY if entry.tier == 2
]
TIER_3_LEAGUES = [
    entry.canonical_name for entry in DEFAULT_LEAGUE_PRIORITY if entry.tier == 3
]


def resolve_league_priority(league_name: str) -> LeaguePriorityEntry | None:
    return _ALIAS_TO_ENTRY.get(normalize_league_name(league_name))


def get_league_tier(league_name: str) -> int:
    entry = resolve_league_priority(league_name)
    return entry.tier if entry is not None else UNPRIORITIZED_TIER


def get_league_priority_rank(league_name: str) -> int:
    entry = resolve_league_priority(league_name)
    return entry.rank if entry is not None else UNPRIORITIZED_RANK
