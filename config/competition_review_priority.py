"""Source-qualified competition review priority for ATHENA accumulator work.

This registry answers where ATHENA should look first when reviewing a fixture
universe. It is deliberately separate from model reliability and from betting
authority. A high review rank never means a model is proven more accurate in
that competition, and it never makes a fixture or market eligible by itself.

Source identity matters. Generic labels such as ``Premier League`` or ``Serie A``
exist in multiple countries, so a caller with FotMob source metadata must match
an exact country-code + normalized whole competition-name pair. There is no
substring, fuzzy, prestige, or country-free fallback in the source-qualified
resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from config.league_priority import normalize_league_name


COMPETITION_REVIEW_PRIORITY_POLICY_VERSION = "athena-competition-review-priority-v1"
COMPETITION_REVIEW_PRIORITY_BASIS = "BOOTSTRAP_REVIEW_ORDER_NOT_MODEL_RELIABILITY"
UNPRIORITIZED_COMPETITION_TIER = 99
UNPRIORITIZED_COMPETITION_RANK = 999


class CompetitionKind(str, Enum):
    DOMESTIC_LEAGUE = "DOMESTIC_LEAGUE"
    DOMESTIC_CUP = "DOMESTIC_CUP"


@dataclass(frozen=True)
class SourceCompetitionIdentity:
    ccode: str
    source_name: str


@dataclass(frozen=True)
class CompetitionReviewPriorityEntry:
    canonical_name: str
    kind: CompetitionKind
    tier: int
    rank: int
    source_identities: tuple[SourceCompetitionIdentity, ...]
    rationale: str


# This is a review-search order, not a prediction-quality table. The top-five
# domestic leagues remain first. DFB-Pokal is deliberately elevated above the
# secondary domestic-league band because the Saturday execution goal benefits
# from inspecting strong cup ties before automatically exhausting Belgium,
# Scotland, Turkey or Greece. Fixture-level/model evidence still decides what,
# if anything, can later survive as a selection.
DEFAULT_COMPETITION_REVIEW_PRIORITY: tuple[CompetitionReviewPriorityEntry, ...] = (
    CompetitionReviewPriorityEntry(
        "Premier League",
        CompetitionKind.DOMESTIC_LEAGUE,
        1,
        1,
        (SourceCompetitionIdentity("ENG", "Premier League"),),
        "Top-five domestic league review band; not a model-reliability claim.",
    ),
    CompetitionReviewPriorityEntry(
        "La Liga",
        CompetitionKind.DOMESTIC_LEAGUE,
        1,
        2,
        (
            SourceCompetitionIdentity("ESP", "LaLiga"),
            SourceCompetitionIdentity("ESP", "La Liga"),
        ),
        "Top-five domestic league review band; not a model-reliability claim.",
    ),
    CompetitionReviewPriorityEntry(
        "Serie A",
        CompetitionKind.DOMESTIC_LEAGUE,
        1,
        3,
        (SourceCompetitionIdentity("ITA", "Serie A"),),
        "Top-five domestic league review band; not a model-reliability claim.",
    ),
    CompetitionReviewPriorityEntry(
        "Bundesliga",
        CompetitionKind.DOMESTIC_LEAGUE,
        1,
        4,
        (SourceCompetitionIdentity("GER", "Bundesliga"),),
        "Top-five domestic league review band; not a model-reliability claim.",
    ),
    CompetitionReviewPriorityEntry(
        "Ligue 1",
        CompetitionKind.DOMESTIC_LEAGUE,
        1,
        5,
        (SourceCompetitionIdentity("FRA", "Ligue 1"),),
        "Top-five domestic league review band; not a model-reliability claim.",
    ),
    CompetitionReviewPriorityEntry(
        "DFB-Pokal",
        CompetitionKind.DOMESTIC_CUP,
        2,
        6,
        (
            SourceCompetitionIdentity("GER", "DFB Pokal"),
            SourceCompetitionIdentity("GER", "DFB-Pokal"),
        ),
        (
            "Strong domestic cup review band. Inspect before the secondary "
            "domestic-league band, while preserving separate lineup/rotation, "
            "team-level and model/market gates for each tie."
        ),
    ),
    CompetitionReviewPriorityEntry(
        "Eredivisie",
        CompetitionKind.DOMESTIC_LEAGUE,
        2,
        7,
        (SourceCompetitionIdentity("NED", "Eredivisie"),),
        "Secondary domestic-league review band; not a model-reliability claim.",
    ),
    CompetitionReviewPriorityEntry(
        "Primeira Liga",
        CompetitionKind.DOMESTIC_LEAGUE,
        2,
        8,
        (
            SourceCompetitionIdentity("POR", "Liga Portugal"),
            SourceCompetitionIdentity("POR", "Primeira Liga"),
        ),
        "Secondary domestic-league review band; not a model-reliability claim.",
    ),
    CompetitionReviewPriorityEntry(
        "Belgian Pro League",
        CompetitionKind.DOMESTIC_LEAGUE,
        3,
        9,
        (
            SourceCompetitionIdentity("BEL", "Belgian Pro League"),
            SourceCompetitionIdentity("BEL", "First Division A"),
        ),
        "Later domestic-league review band; not a model-reliability claim.",
    ),
    CompetitionReviewPriorityEntry(
        "Scottish Premiership",
        CompetitionKind.DOMESTIC_LEAGUE,
        3,
        10,
        (
            SourceCompetitionIdentity("SCO", "Premiership"),
            SourceCompetitionIdentity("SCO", "Scottish Premiership"),
        ),
        "Later domestic-league review band; not a model-reliability claim.",
    ),
    CompetitionReviewPriorityEntry(
        "Süper Lig",
        CompetitionKind.DOMESTIC_LEAGUE,
        3,
        11,
        (
            SourceCompetitionIdentity("TUR", "Super Lig"),
            SourceCompetitionIdentity("TUR", "Süper Lig"),
        ),
        "Later domestic-league review band; not a model-reliability claim.",
    ),
    CompetitionReviewPriorityEntry(
        "Greek Super League",
        CompetitionKind.DOMESTIC_LEAGUE,
        3,
        12,
        (
            SourceCompetitionIdentity("GRE", "Super League"),
            SourceCompetitionIdentity("GRE", "Greek Super League"),
        ),
        "Later domestic-league review band; not a model-reliability claim.",
    ),
)


_SOURCE_IDENTITY_TO_ENTRY: dict[
    tuple[str, str], CompetitionReviewPriorityEntry
] = {}
_CANONICAL_TO_ENTRY: dict[str, CompetitionReviewPriorityEntry] = {}
for _entry in DEFAULT_COMPETITION_REVIEW_PRIORITY:
    if _entry.canonical_name in _CANONICAL_TO_ENTRY:
        raise RuntimeError("duplicate canonical competition review-priority name")
    _CANONICAL_TO_ENTRY[_entry.canonical_name] = _entry
    for _identity in _entry.source_identities:
        if type(_identity.ccode) is not str or not _identity.ccode:
            raise RuntimeError("competition source country code must be non-empty")
        _normalized = normalize_league_name(_identity.source_name)
        if not _normalized:
            raise RuntimeError("competition source name normalized empty")
        _key = (_identity.ccode, _normalized)
        _existing = _SOURCE_IDENTITY_TO_ENTRY.get(_key)
        if _existing is not None and _existing != _entry:
            raise RuntimeError(
                f"ambiguous source competition identity {_key!r}: "
                f"{_existing.canonical_name!r} vs {_entry.canonical_name!r}"
            )
        _SOURCE_IDENTITY_TO_ENTRY[_key] = _entry


def resolve_source_competition_review_priority(
    ccode: object,
    source_name: object,
) -> CompetitionReviewPriorityEntry | None:
    """Resolve one exact source-qualified competition identity."""

    if type(ccode) is not str or type(source_name) is not str:
        return None
    normalized = normalize_league_name(source_name)
    if not normalized:
        return None
    return _SOURCE_IDENTITY_TO_ENTRY.get((ccode, normalized))


def resolve_canonical_competition_review_priority(
    canonical_name: object,
) -> CompetitionReviewPriorityEntry | None:
    """Resolve only an already-canonical internal competition name."""

    if type(canonical_name) is not str:
        return None
    return _CANONICAL_TO_ENTRY.get(canonical_name)


__all__ = [
    "COMPETITION_REVIEW_PRIORITY_BASIS",
    "COMPETITION_REVIEW_PRIORITY_POLICY_VERSION",
    "DEFAULT_COMPETITION_REVIEW_PRIORITY",
    "UNPRIORITIZED_COMPETITION_RANK",
    "UNPRIORITIZED_COMPETITION_TIER",
    "CompetitionKind",
    "CompetitionReviewPriorityEntry",
    "SourceCompetitionIdentity",
    "resolve_canonical_competition_review_priority",
    "resolve_source_competition_review_priority",
]
