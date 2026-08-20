"""Versioned default league hierarchy for ATHENA accumulator planning.

League priority is an ordering policy, not model or betting authority.  A league
being high in this registry never makes a fixture eligible by itself.  Actual
accumulator inclusion still requires the fixture/market/evidence/pricing gates
owned by the reviewed decision pipeline.

The old implementation used substring matching, which could incorrectly treat
competitions such as the Austrian Bundesliga as the German Bundesliga.  This
module uses normalized *whole-name aliases* only.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


PRIORITY_POLICY_VERSION = "athena-league-priority-v2"
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
    """Normalize a league label for exact alias matching.

    Normalization is intentionally conservative: case, accents and punctuation
    are normalized, but substring/fuzzy matching is never performed.
    """

    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", " ", without_marks.casefold()).strip()


# The first eleven competitions mirror ATHENA's reviewed domestic historical
# source coverage (E0, SP1, I1, D1, F1, N1, P1, B1, SC0, T1, G1).  The UEFA
# club competitions are an explicit later expansion band: they may be ordered
# here, but they still need a market/model to say they are actually supported.
DEFAULT_LEAGUE_PRIORITY: tuple[LeaguePriorityEntry, ...] = (
    LeaguePriorityEntry(
        "Premier League",
        1,
        1,
        ("Premier League", "English Premier League", "England Premier League"),
        "Core reviewed domestic-history coverage.",
    ),
    LeaguePriorityEntry(
        "La Liga",
        1,
        2,
        ("La Liga", "Primera Division", "Spain La Liga"),
        "Core reviewed domestic-history coverage.",
    ),
    LeaguePriorityEntry(
        "Serie A",
        1,
        3,
        ("Serie A", "Italy Serie A", "Italian Serie A"),
        "Core reviewed domestic-history coverage.",
    ),
    LeaguePriorityEntry(
        "Bundesliga",
        1,
        4,
        ("Bundesliga", "German Bundesliga", "Germany Bundesliga"),
        "Core reviewed domestic-history coverage.",
    ),
    LeaguePriorityEntry(
        "Ligue 1",
        1,
        5,
        ("Ligue 1", "France Ligue 1", "French Ligue 1"),
        "Core reviewed domestic-history coverage.",
    ),
    LeaguePriorityEntry(
        "Eredivisie",
        2,
        6,
        ("Eredivisie", "Netherlands Eredivisie", "Dutch Eredivisie"),
        "Reviewed domestic-history expansion coverage.",
    ),
    LeaguePriorityEntry(
        "Primeira Liga",
        2,
        7,
        ("Primeira Liga", "Liga Portugal", "Portugal Primeira Liga"),
        "Reviewed domestic-history expansion coverage.",
    ),
    LeaguePriorityEntry(
        "Belgian Pro League",
        2,
        8,
        (
            "Belgian Pro League",
            "First Division A",
            "Jupiler Pro League",
            "Belgium First Division A",
        ),
        "Reviewed domestic-history expansion coverage.",
    ),
    LeaguePriorityEntry(
        "Scottish Premiership",
        2,
        9,
        ("Scottish Premiership", "Scotland Premiership"),
        "Reviewed domestic-history expansion coverage.",
    ),
    LeaguePriorityEntry(
        "Süper Lig",
        2,
        10,
        ("Süper Lig", "Super Lig", "Turkey Super Lig", "Turkish Super Lig"),
        "Reviewed domestic-history expansion coverage.",
    ),
    LeaguePriorityEntry(
        "Greek Super League",
        2,
        11,
        (
            "Greek Super League",
            "Super League Greece",
            "Super League (Greece)",
            "Greece Super League 1",
            "Super League 1",
        ),
        "Reviewed domestic-history expansion coverage.",
    ),
    LeaguePriorityEntry(
        "UEFA Champions League",
        3,
        12,
        ("UEFA Champions League", "Champions League"),
        "Continental expansion; inclusion still requires explicit model support.",
    ),
    LeaguePriorityEntry(
        "UEFA Europa League",
        3,
        13,
        ("UEFA Europa League", "Europa League"),
        "Continental expansion; inclusion still requires explicit model support.",
    ),
    LeaguePriorityEntry(
        "UEFA Conference League",
        3,
        14,
        (
            "UEFA Conference League",
            "UEFA Europa Conference League",
            "Conference League",
        ),
        "Continental expansion; inclusion still requires explicit model support.",
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


# Compatibility exports used by the legacy AccaFilter.  They now represent
# exact registry membership rather than the old fuzzy/substring semantics.
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
    """Resolve an exact normalized alias to its priority entry."""

    return _ALIAS_TO_ENTRY.get(normalize_league_name(league_name))


def get_league_tier(league_name: str) -> int:
    """Return the configured priority tier; unknown leagues fail to tier 99."""

    entry = resolve_league_priority(league_name)
    return entry.tier if entry is not None else UNPRIORITIZED_TIER


def get_league_priority_rank(league_name: str) -> int:
    """Return strict default league rank; unknown leagues sort last."""

    entry = resolve_league_priority(league_name)
    return entry.rank if entry is not None else UNPRIORITIZED_RANK
