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
# domestic leagues remain first. Primeira Liga, Super Lig and Eredivisie are
# reviewed before the major domestic-cup band. The primary domestic cups of the
# top-five countries then share one review rank, ahead of Belgium, Scotland and
# Greece. Sharing a cup rank is deliberate: once the review band is reached,
# exact fixture/model quality breaks ties rather than an arbitrary prestige
# ordering between FA Cup, Copa del Rey, Coppa Italia, DFB-Pokal and Coupe de
# France. Fixture-level/model evidence still decides what, if anything, survives.
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
        "Primeira Liga",
        CompetitionKind.DOMESTIC_LEAGUE,
        2,
        6,
        (
            SourceCompetitionIdentity("POR", "Liga Portugal"),
            SourceCompetitionIdentity("POR", "Primeira Liga"),
        ),
        "Upper secondary domestic-league review band; above major cup review.",
    ),
    CompetitionReviewPriorityEntry(
        "Süper Lig",
        CompetitionKind.DOMESTIC_LEAGUE,
        2,
        7,
        (
            SourceCompetitionIdentity("TUR", "Super Lig"),
            SourceCompetitionIdentity("TUR", "Süper Lig"),
        ),
        "Upper secondary domestic-league review band; above major cup review.",
    ),
    CompetitionReviewPriorityEntry(
        "Eredivisie",
        CompetitionKind.DOMESTIC_LEAGUE,
        2,
        8,
        (SourceCompetitionIdentity("NED", "Eredivisie"),),
        "Upper secondary domestic-league review band; above major cup review.",
    ),
    CompetitionReviewPriorityEntry(
        "FA Cup",
        CompetitionKind.DOMESTIC_CUP,
        3,
        9,
        (SourceCompetitionIdentity("ENG", "FA Cup"),),
        (
            "Major domestic-cup review band. Fixture-level lineup/rotation, team "
            "strength and model/market evidence still decide whether a tie survives."
        ),
    ),
    CompetitionReviewPriorityEntry(
        "Copa del Rey",
        CompetitionKind.DOMESTIC_CUP,
        3,
        9,
        (SourceCompetitionIdentity("ESP", "Copa del Rey"),),
        (
            "Major domestic-cup review band. Fixture-level lineup/rotation, team "
            "strength and model/market evidence still decide whether a tie survives."
        ),
    ),
    CompetitionReviewPriorityEntry(
        "Coppa Italia",
        CompetitionKind.DOMESTIC_CUP,
        3,
        9,
        (SourceCompetitionIdentity("ITA", "Coppa Italia"),),
        (
            "Major domestic-cup review band. Fixture-level lineup/rotation, team "
            "strength and model/market evidence still decide whether a tie survives."
        ),
    ),
    CompetitionReviewPriorityEntry(
        "DFB-Pokal",
        CompetitionKind.DOMESTIC_CUP,
        3,
        9,
        (
            SourceCompetitionIdentity("GER", "DFB Pokal"),
            SourceCompetitionIdentity("GER", "DFB-Pokal"),
        ),
        (
            "Major domestic-cup review band. Fixture-level lineup/rotation, team "
            "strength and model/market evidence still decide whether a tie survives."
        ),
    ),
    CompetitionReviewPriorityEntry(
        "Coupe de France",
        CompetitionKind.DOMESTIC_CUP,
        3,
        9,
        (SourceCompetitionIdentity("FRA", "Coupe de France"),),
        (
            "Major domestic-cup review band. Fixture-level lineup/rotation, team "
            "strength and model/market evidence still decide whether a tie survives."
        ),
    ),
    CompetitionReviewPriorityEntry(
        "Belgian Pro League",
        CompetitionKind.DOMESTIC_LEAGUE,
        4,
        10,
        (
            SourceCompetitionIdentity("BEL", "Belgian Pro League"),
            SourceCompetitionIdentity("BEL", "First Division A"),
        ),
        "Later domestic-league review band; below the major domestic-cup band.",
    ),
    CompetitionReviewPriorityEntry(
        "Scottish Premiership",
        CompetitionKind.DOMESTIC_LEAGUE,
        4,
        11,
        (
            SourceCompetitionIdentity("SCO", "Premiership"),
            SourceCompetitionIdentity("SCO", "Scottish Premiership"),
        ),
        "Later domestic-league review band; below the major domestic-cup band.",
    ),
    CompetitionReviewPriorityEntry(
        "Greek Super League",
        CompetitionKind.DOMESTIC_LEAGUE,
        4,
        12,
        (
            SourceCompetitionIdentity("GRE", "Super League"),
            SourceCompetitionIdentity("GRE", "Greek Super League"),
        ),
        "Later domestic-league review band; below the major domestic-cup band.",
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
