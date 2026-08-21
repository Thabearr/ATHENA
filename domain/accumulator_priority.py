"""Deterministic priority planning for large ATHENA accumulators.

This module answers only *which already-eligible fixtures are considered first*.
It does not make a fixture eligible, grant model/selection/pricing authority, or
force a requested fold size.

When exact source competition identity is preserved, review ordering is taken
from the source-qualified competition-review registry. This allows reviewed cup
competitions such as DFB-Pokal to sit ahead of lower review-priority leagues
without pretending that cup status is model-reliability evidence. If source
identity is absent, the pre-existing evidence-gated model-league boundary remains
the compatibility fallback.

Within one competition, fixture ordering is lexicographic rather than a hidden
weighted score: higher estimated leg probability, lower risk, fresher evidence,
higher validated bookmaker edge, earlier kickoff, then stable fixture identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any, Iterable, Mapping

from config.competition_review_priority import (
    COMPETITION_REVIEW_PRIORITY_POLICY_VERSION,
    UNPRIORITIZED_COMPETITION_RANK,
    UNPRIORITIZED_COMPETITION_TIER,
    resolve_source_competition_review_priority,
)
from config.league_priority import (
    PRIORITY_POLICY_VERSION,
    UNPRIORITIZED_RANK,
    UNPRIORITIZED_TIER,
    resolve_league_priority,
)
from domain.model_league_reliability import (
    MODEL_LEAGUE_RELIABILITY_POLICY_VERSION,
    resolve_candidate_model_league_priority,
)


ACCUMULATOR_PRIORITY_POLICY_VERSION = "athena-acca-priority-v3"


@dataclass(frozen=True)
class PriorityExclusion:
    fixture_id: str
    league: str
    reason: str


@dataclass(frozen=True)
class AccumulatorPriorityPlan:
    policy_version: str
    competition_review_policy_version: str
    league_policy_version: str
    model_league_policy_version: str
    requested_fold_size: int
    ordered_candidates: tuple[dict[str, Any], ...]
    selected_candidates: tuple[dict[str, Any], ...]
    reserve_candidates: tuple[dict[str, Any], ...]
    exclusions: tuple[PriorityExclusion, ...]
    shortfall: int

    @property
    def fulfilled(self) -> bool:
        return self.shortfall == 0


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _probability(match: Mapping[str, Any]) -> float | None:
    selection = match.get("accumulator_eligible_selection")
    value = None
    if isinstance(selection, Mapping):
        value = _finite_number(selection.get("prob"))
        if value is None:
            value = _finite_number(selection.get("estimated_probability"))
    if value is None:
        value = _finite_number(match.get("estimated_probability"))
    if value is None or value < 0.0 or value > 1.0:
        return None
    return value


def _edge_pp(match: Mapping[str, Any]) -> float | None:
    selection = match.get("accumulator_eligible_selection")
    value = None
    if isinstance(selection, Mapping):
        value = _finite_number(selection.get("edge_pp"))
        if selection.get("edge_is_bookmaker_value") is not True:
            value = None
    if value is None and match.get("edge_is_bookmaker_value") is True:
        value = _finite_number(match.get("edge_pp"))
    return value


def _risk(match: Mapping[str, Any]) -> float:
    value = _finite_number(match.get("risk_score"))
    return value if value is not None else float("inf")


def _freshness(match: Mapping[str, Any]) -> float | None:
    value = _finite_number(match.get("freshness"))
    if value is None or value < 0.0 or value > 1.0:
        return None
    return value


def _kickoff(match: Mapping[str, Any]) -> datetime:
    value = match.get("match_date")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = datetime.max.replace(tzinfo=timezone.utc)
    else:
        parsed = datetime.max.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fixture_identity(match: Mapping[str, Any], input_index: int) -> str:
    for key in ("fixture_id", "fixture"):
        value = match.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return f"__input_index__:{input_index:09d}"


def _source_competition_identity_present(match: Mapping[str, Any]) -> bool:
    return (
        "source_competition_ccode" in match
        or "source_competition_name" in match
    )


def _competition_review_entry(match: Mapping[str, Any]):
    if not _source_competition_identity_present(match):
        return None
    return resolve_source_competition_review_priority(
        match.get("source_competition_ccode"),
        match.get("source_competition_name"),
    )


def _effective_review_rank(match: Mapping[str, Any]) -> int:
    if _source_competition_identity_present(match):
        entry = _competition_review_entry(match)
        return entry.rank if entry is not None else UNPRIORITIZED_COMPETITION_RANK
    return resolve_candidate_model_league_priority(match).effective_rank


def fixture_priority_sort_key(
    match: Mapping[str, Any],
    *,
    input_index: int = 0,
) -> tuple[Any, ...]:
    """Return transparent competition-review + fixture-quality priority key."""

    probability = _probability(match)
    risk = _risk(match)
    freshness = _freshness(match)
    edge_pp = _edge_pp(match)

    return (
        _effective_review_rank(match),
        1 if probability is None else 0,
        -(probability if probability is not None else 0.0),
        risk,
        1 if freshness is None else 0,
        -(freshness if freshness is not None else 0.0),
        1 if edge_pp is None else 0,
        -(edge_pp if edge_pp is not None else 0.0),
        _kickoff(match),
        _fixture_identity(match, input_index),
        input_index,
    )


def _annotate(
    match: Mapping[str, Any],
    *,
    input_index: int,
) -> dict[str, Any]:
    league = str(match.get("league") or "")
    league_entry = resolve_league_priority(league)
    league_resolution = resolve_candidate_model_league_priority(match)
    source_identity_present = _source_competition_identity_present(match)
    competition_entry = _competition_review_entry(match)

    if source_identity_present:
        review_rank = (
            competition_entry.rank
            if competition_entry is not None
            else UNPRIORITIZED_COMPETITION_RANK
        )
        review_tier = (
            competition_entry.tier
            if competition_entry is not None
            else UNPRIORITIZED_COMPETITION_TIER
        )
        review_name = competition_entry.canonical_name if competition_entry else None
        review_kind = competition_entry.kind.value if competition_entry else None
        review_basis = (
            "SOURCE_QUALIFIED_COMPETITION_REVIEW_PRIORITY"
            if competition_entry is not None
            else "UNRESOLVED_SOURCE_COMPETITION_IDENTITY"
        )
    else:
        review_rank = league_resolution.effective_rank
        review_tier = league_entry.tier if league_entry else UNPRIORITIZED_TIER
        review_name = league_resolution.canonical_league
        review_kind = "LEGACY_LEAGUE_FALLBACK" if league_entry else None
        review_basis = "MODEL_LEAGUE_OR_BOOTSTRAP_FALLBACK"

    annotated = dict(match)
    annotated["priority_policy_version"] = ACCUMULATOR_PRIORITY_POLICY_VERSION
    annotated["competition_review_priority_policy_version"] = (
        COMPETITION_REVIEW_PRIORITY_POLICY_VERSION
    )
    annotated["competition_review_priority_rank"] = review_rank
    annotated["competition_review_priority_tier"] = review_tier
    annotated["competition_review_priority_name"] = review_name
    annotated["competition_review_priority_kind"] = review_kind
    annotated["competition_review_priority_basis"] = review_basis
    annotated["league_priority_policy_version"] = PRIORITY_POLICY_VERSION
    annotated["model_league_reliability_policy_version"] = (
        MODEL_LEAGUE_RELIABILITY_POLICY_VERSION
    )
    annotated["league_priority_tier"] = (
        league_entry.tier if league_entry is not None else UNPRIORITIZED_TIER
    )
    annotated["league_priority_rank"] = (
        league_entry.rank if league_entry is not None else UNPRIORITIZED_RANK
    )
    annotated["league_priority_name"] = (
        league_entry.canonical_name if league_entry is not None else None
    )
    annotated["model_league_family"] = (
        league_resolution.family.value if league_resolution.family is not None else None
    )
    annotated["model_league_priority_rank"] = league_resolution.effective_rank
    annotated["model_league_priority_basis"] = league_resolution.basis.value
    annotated["model_league_ranking_authorized"] = league_resolution.ranking_authorized
    annotated["model_league_reliability_reason"] = league_resolution.reason
    annotated["model_league_reliability_evidence"] = list(
        league_resolution.evidence_references
    )
    annotated["fixture_priority_probability"] = _probability(match)
    annotated["fixture_priority_risk_score"] = (
        None if math.isinf(_risk(match)) else _risk(match)
    )
    annotated["fixture_priority_freshness"] = _freshness(match)
    annotated["fixture_priority_edge_pp"] = _edge_pp(match)
    annotated["fixture_priority_input_index"] = input_index
    return annotated


def prioritize_accumulator_candidates(
    candidates: Iterable[Mapping[str, Any]],
    *,
    allow_unprioritized: bool = False,
) -> tuple[tuple[dict[str, Any], ...], tuple[PriorityExclusion, ...]]:
    """Order candidates by review priority then fixture quality.

    Exact source competition identity, when present, is authoritative for review
    ordering and prevents a same-name foreign competition from falling back to a
    bare league label. Without source identity, the previous model-league
    compatibility path remains in force.
    """

    decorated: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    exclusions: list[PriorityExclusion] = []

    for input_index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            exclusions.append(
                PriorityExclusion(
                    fixture_id=f"__input_index__:{input_index:09d}",
                    league="",
                    reason="candidate is not a mapping",
                )
            )
            continue

        league = str(candidate.get("league") or "")
        fixture_id = _fixture_identity(candidate, input_index)
        source_identity_present = _source_competition_identity_present(candidate)
        competition_entry = _competition_review_entry(candidate)

        if source_identity_present:
            if competition_entry is None and not allow_unprioritized:
                exclusions.append(
                    PriorityExclusion(
                        fixture_id=fixture_id,
                        league=league,
                        reason=(
                            "source competition identity is not in the reviewed ATHENA "
                            "competition-review registry; explicit expansion opt-in is required"
                        ),
                    )
                )
                continue
        else:
            league_entry = resolve_league_priority(league)
            if league_entry is None and not allow_unprioritized:
                exclusions.append(
                    PriorityExclusion(
                        fixture_id=fixture_id,
                        league=league,
                        reason=(
                            "league is not in the default ATHENA priority registry; "
                            "explicit expansion opt-in is required"
                        ),
                    )
                )
                continue

        decorated.append(
            (
                fixture_priority_sort_key(candidate, input_index=input_index),
                _annotate(candidate, input_index=input_index),
            )
        )

    decorated.sort(key=lambda item: item[0])
    return tuple(item[1] for item in decorated), tuple(exclusions)


def build_accumulator_priority_plan(
    candidates: Iterable[Mapping[str, Any]],
    *,
    target_size: int,
    allow_unprioritized: bool = False,
) -> AccumulatorPriorityPlan:
    """Build a deterministic priority plan without manufacturing fold size."""

    if isinstance(target_size, bool) or not isinstance(target_size, int):
        raise TypeError("target_size must be an integer")
    if target_size < 1 or target_size > 50:
        raise ValueError("target_size must be between 1 and 50")

    ordered, exclusions = prioritize_accumulator_candidates(
        candidates,
        allow_unprioritized=allow_unprioritized,
    )
    selected = ordered[:target_size]
    reserve = ordered[target_size:]
    return AccumulatorPriorityPlan(
        policy_version=ACCUMULATOR_PRIORITY_POLICY_VERSION,
        competition_review_policy_version=(
            COMPETITION_REVIEW_PRIORITY_POLICY_VERSION
        ),
        league_policy_version=PRIORITY_POLICY_VERSION,
        model_league_policy_version=MODEL_LEAGUE_RELIABILITY_POLICY_VERSION,
        requested_fold_size=target_size,
        ordered_candidates=ordered,
        selected_candidates=selected,
        reserve_candidates=reserve,
        exclusions=exclusions,
        shortfall=max(0, target_size - len(selected)),
    )
