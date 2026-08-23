"""Deterministic ATHENA accumulator consideration ordering.

This module consumes only already-eligible candidates. Competition hierarchy,
stage modifiers and fixture quality determine review order; none of them create
model, pricing, selection, execution or BET authority.

Club and international football use separate hierarchy spaces. A single plan
must not mechanically mix them.
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
    CompetitionScope,
    apply_stage_modifier,
    resolve_canonical_competition_review_priority,
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


ACCUMULATOR_PRIORITY_POLICY_VERSION = "athena-acca-priority-v4"


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


def _scope(match: Mapping[str, Any]) -> CompetitionScope:
    value = match.get("competition_scope")
    if value is None:
        return CompetitionScope.CLUB
    if isinstance(value, CompetitionScope):
        return value
    if isinstance(value, str):
        try:
            return CompetitionScope(value.strip().upper())
        except ValueError:
            pass
    raise ValueError("competition_scope must be CLUB or INTERNATIONAL")


def _source_competition_identity_present(match: Mapping[str, Any]) -> bool:
    return "source_competition_ccode" in match or "source_competition_name" in match


def _competition_review_entry(match: Mapping[str, Any]):
    scope = _scope(match)
    if _source_competition_identity_present(match):
        return resolve_source_competition_review_priority(
            match.get("source_competition_ccode"),
            match.get("source_competition_name"),
        )

    if match.get("canonical_competition_identity_reviewed") is True:
        return resolve_canonical_competition_review_priority(
            match.get("canonical_competition_name"),
            scope=scope,
        )

    if scope is CompetitionScope.INTERNATIONAL:
        # The scope itself is explicit. Exact alias resolution is permitted, but
        # still no fuzzy/substring matching is used.
        return resolve_canonical_competition_review_priority(
            match.get("league"),
            scope=scope,
        )
    return None


def _stage_adjustment(match: Mapping[str, Any], entry):
    if entry is None:
        return None
    return apply_stage_modifier(
        entry,
        stage=match.get("competition_stage"),
        stage_evidence_reviewed=match.get("stage_evidence_reviewed") is True,
        both_sides_strong_lineups_expected=(
            match.get("both_sides_strong_lineups_expected") is True
        ),
        top_flight_rotation_expected=match.get("top_flight_rotation_expected") is True,
        two_leg_second_leg=match.get("two_leg_second_leg") is True,
    )


def _priority_components(match: Mapping[str, Any]) -> tuple[int, int]:
    scope = _scope(match)
    entry = _competition_review_entry(match)
    if entry is not None:
        adjustment = _stage_adjustment(match, entry)
        return adjustment.effective_tier, entry.rank
    if scope is CompetitionScope.INTERNATIONAL:
        return UNPRIORITIZED_COMPETITION_TIER, UNPRIORITIZED_COMPETITION_RANK
    if _source_competition_identity_present(match):
        return UNPRIORITIZED_COMPETITION_TIER, UNPRIORITIZED_COMPETITION_RANK
    league_resolution = resolve_candidate_model_league_priority(match)
    league_entry = resolve_league_priority(str(match.get("league") or ""))
    return (
        league_entry.tier if league_entry is not None else UNPRIORITIZED_TIER,
        league_resolution.effective_rank,
    )


def fixture_priority_sort_key(
    match: Mapping[str, Any],
    *,
    input_index: int = 0,
) -> tuple[Any, ...]:
    """Transparent hierarchy-band -> hierarchy-rank -> fixture-quality key."""

    probability = _probability(match)
    risk = _risk(match)
    freshness = _freshness(match)
    edge_pp = _edge_pp(match)
    effective_tier, rank = _priority_components(match)

    return (
        effective_tier,
        rank,
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


def _annotate(match: Mapping[str, Any], *, input_index: int) -> dict[str, Any]:
    league = str(match.get("league") or "")
    scope = _scope(match)
    league_entry = resolve_league_priority(league)
    league_resolution = resolve_candidate_model_league_priority(match)
    source_identity_present = _source_competition_identity_present(match)
    competition_entry = _competition_review_entry(match)
    stage_adjustment = _stage_adjustment(match, competition_entry)

    if competition_entry is not None:
        review_rank = competition_entry.rank
        review_tier = stage_adjustment.effective_tier
        review_name = competition_entry.canonical_name
        review_kind = competition_entry.kind.value
        review_band = stage_adjustment.effective_band
        review_base_band = competition_entry.priority_band
        review_base_score = competition_entry.base_score
        if source_identity_present:
            review_basis = "SOURCE_QUALIFIED_COMPETITION_REVIEW_PRIORITY"
        elif match.get("canonical_competition_identity_reviewed") is True:
            review_basis = "REVIEWED_CANONICAL_COMPETITION_IDENTITY"
        else:
            review_basis = "EXACT_INTERNATIONAL_SCOPE_ALIAS"
    elif scope is CompetitionScope.INTERNATIONAL:
        review_rank = UNPRIORITIZED_COMPETITION_RANK
        review_tier = UNPRIORITIZED_COMPETITION_TIER
        review_name = None
        review_kind = None
        review_band = None
        review_base_band = None
        review_base_score = None
        review_basis = "UNRESOLVED_INTERNATIONAL_COMPETITION_IDENTITY"
    elif source_identity_present:
        review_rank = UNPRIORITIZED_COMPETITION_RANK
        review_tier = UNPRIORITIZED_COMPETITION_TIER
        review_name = None
        review_kind = None
        review_band = None
        review_base_band = None
        review_base_score = None
        review_basis = "UNRESOLVED_SOURCE_COMPETITION_IDENTITY"
    else:
        review_rank = league_resolution.effective_rank
        review_tier = league_entry.tier if league_entry else UNPRIORITIZED_TIER
        review_name = league_resolution.canonical_league
        review_kind = "LEGACY_LEAGUE_FALLBACK" if league_entry else None
        review_band = None
        review_base_band = None
        review_base_score = None
        review_basis = "MODEL_LEAGUE_OR_HIERARCHY_FALLBACK"

    annotated = dict(match)
    annotated["priority_policy_version"] = ACCUMULATOR_PRIORITY_POLICY_VERSION
    annotated["competition_review_priority_policy_version"] = COMPETITION_REVIEW_PRIORITY_POLICY_VERSION
    annotated["competition_review_scope"] = scope.value
    annotated["competition_review_priority_rank"] = review_rank
    annotated["competition_review_priority_tier"] = review_tier
    annotated["competition_review_priority_name"] = review_name
    annotated["competition_review_priority_kind"] = review_kind
    annotated["competition_review_priority_band"] = review_band
    annotated["competition_review_base_band"] = review_base_band
    annotated["competition_review_base_score"] = review_base_score
    annotated["competition_review_priority_basis"] = review_basis
    annotated["competition_stage_modifier_delta"] = (
        stage_adjustment.band_delta if stage_adjustment is not None else 0
    )
    annotated["competition_stage_modifier_reason"] = (
        stage_adjustment.reason if stage_adjustment is not None else None
    )
    annotated["competition_second_leg_confidence_focus"] = (
        stage_adjustment.confidence_focus if stage_adjustment is not None else False
    )
    annotated["league_priority_policy_version"] = PRIORITY_POLICY_VERSION
    annotated["model_league_reliability_policy_version"] = MODEL_LEAGUE_RELIABILITY_POLICY_VERSION
    annotated["league_priority_tier"] = league_entry.tier if league_entry is not None else UNPRIORITIZED_TIER
    annotated["league_priority_rank"] = league_entry.rank if league_entry is not None else UNPRIORITIZED_RANK
    annotated["league_priority_name"] = league_entry.canonical_name if league_entry is not None else None
    annotated["model_league_family"] = league_resolution.family.value if league_resolution.family is not None else None
    annotated["model_league_priority_rank"] = league_resolution.effective_rank
    annotated["model_league_priority_basis"] = league_resolution.basis.value
    annotated["model_league_ranking_authorized"] = league_resolution.ranking_authorized
    annotated["model_league_reliability_reason"] = league_resolution.reason
    annotated["model_league_reliability_evidence"] = list(league_resolution.evidence_references)
    annotated["fixture_priority_probability"] = _probability(match)
    annotated["fixture_priority_risk_score"] = None if math.isinf(_risk(match)) else _risk(match)
    annotated["fixture_priority_freshness"] = _freshness(match)
    annotated["fixture_priority_edge_pp"] = _edge_pp(match)
    annotated["fixture_priority_input_index"] = input_index
    return annotated


def prioritize_accumulator_candidates(
    candidates: Iterable[Mapping[str, Any]],
    *,
    allow_unprioritized: bool = False,
) -> tuple[tuple[dict[str, Any], ...], tuple[PriorityExclusion, ...]]:
    """Order candidates while preserving separate club/international hierarchies."""

    decorated: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    exclusions: list[PriorityExclusion] = []
    admitted_scopes: set[CompetitionScope] = set()

    for input_index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            exclusions.append(PriorityExclusion(f"__input_index__:{input_index:09d}", "", "candidate is not a mapping"))
            continue

        league = str(candidate.get("league") or "")
        fixture_id = _fixture_identity(candidate, input_index)
        scope = _scope(candidate)
        source_identity_present = _source_competition_identity_present(candidate)
        competition_entry = _competition_review_entry(candidate)

        if source_identity_present:
            if competition_entry is None and not allow_unprioritized:
                exclusions.append(PriorityExclusion(fixture_id, league, "source competition identity is not in the reviewed ATHENA hierarchy; explicit expansion opt-in is required"))
                continue
        elif scope is CompetitionScope.INTERNATIONAL:
            if competition_entry is None and not allow_unprioritized:
                exclusions.append(PriorityExclusion(fixture_id, league, "international competition identity is not in the reviewed ATHENA international hierarchy"))
                continue
        else:
            league_entry = resolve_league_priority(league)
            if competition_entry is None and league_entry is None and not allow_unprioritized:
                exclusions.append(PriorityExclusion(fixture_id, league, "competition is not in the default ATHENA hierarchy; explicit expansion opt-in is required"))
                continue

        admitted_scopes.add(scope)
        decorated.append((fixture_priority_sort_key(candidate, input_index=input_index), _annotate(candidate, input_index=input_index)))

    if len(admitted_scopes) > 1:
        raise ValueError("club and international competition hierarchies must be planned separately")

    decorated.sort(key=lambda item: item[0])
    return tuple(item[1] for item in decorated), tuple(exclusions)


def build_accumulator_priority_plan(
    candidates: Iterable[Mapping[str, Any]],
    *,
    target_size: int,
    allow_unprioritized: bool = False,
) -> AccumulatorPriorityPlan:
    if isinstance(target_size, bool) or not isinstance(target_size, int):
        raise TypeError("target_size must be an integer")
    if target_size < 1 or target_size > 50:
        raise ValueError("target_size must be between 1 and 50")

    ordered, exclusions = prioritize_accumulator_candidates(candidates, allow_unprioritized=allow_unprioritized)
    selected = ordered[:target_size]
    reserve = ordered[target_size:]
    return AccumulatorPriorityPlan(
        policy_version=ACCUMULATOR_PRIORITY_POLICY_VERSION,
        competition_review_policy_version=COMPETITION_REVIEW_PRIORITY_POLICY_VERSION,
        league_policy_version=PRIORITY_POLICY_VERSION,
        model_league_policy_version=MODEL_LEAGUE_RELIABILITY_POLICY_VERSION,
        requested_fold_size=target_size,
        ordered_candidates=ordered,
        selected_candidates=selected,
        reserve_candidates=reserve,
        exclusions=exclusions,
        shortfall=max(0, target_size - len(selected)),
    )
