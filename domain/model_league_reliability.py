"""Evidence-gated model-specific league priority for ATHENA accumulators.

This module is deliberately stricter than the bootstrap league registry.  A
model family may override the bootstrap league order only when ATHENA possesses
reviewed, league-identified held-out evidence with exact committed/replayable
metrics for that family.  Qualitative summaries, prestige, caller-provided
scores, and unsupported competition labels never create a reliability rank.

At the current boundary no model family has enough reviewed league-level
validation evidence to override the bootstrap order.  The resolver therefore
returns an auditable bootstrap fallback while preserving the exact blocker that
prevents evidence-ranked ordering.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from config.league_priority import (
    PRIORITY_POLICY_VERSION,
    UNPRIORITIZED_RANK,
    resolve_league_priority,
)
from domain.markets import MarketId, MarketRegistryError, canonicalize_market_id


MODEL_LEAGUE_RELIABILITY_POLICY_VERSION = "athena-model-league-reliability-v1"


class ModelLeagueFamily(str, Enum):
    SCORE_MATRIX_XG = "SCORE_MATRIX_XG"
    WIN_EITHER_HALF_HOME = "WIN_EITHER_HALF_HOME"
    WIN_EITHER_HALF_AWAY = "WIN_EITHER_HALF_AWAY"
    EARLY_PAYOUT_LEAD_PATH = "EARLY_PAYOUT_LEAD_PATH"


class LeagueReliabilityBasis(str, Enum):
    EVIDENCE_RANKED = "EVIDENCE_RANKED"
    BOOTSTRAP_FALLBACK = "BOOTSTRAP_FALLBACK"
    MARKET_MODEL_FAMILY_UNRESOLVED = "MARKET_MODEL_FAMILY_UNRESOLVED"


@dataclass(frozen=True)
class ModelLeagueEvidenceState:
    family: ModelLeagueFamily
    ranking_authorized: bool
    primary_metric: str
    evidence_references: tuple[str, ...]
    blocker: str | None


@dataclass(frozen=True)
class ModelLeaguePriorityResolution:
    policy_version: str
    bootstrap_policy_version: str
    family: ModelLeagueFamily | None
    canonical_league: str | None
    bootstrap_rank: int
    effective_rank: int
    basis: LeagueReliabilityBasis
    ranking_authorized: bool
    evidence_references: tuple[str, ...]
    reason: str


_SCORE_MATRIX_MARKETS = frozenset(
    {
        MarketId.MATCH_RESULT,
        MarketId.ASIAN_HANDICAP,
        MarketId.TOTAL_GOALS,
        MarketId.DRAW_OR_OVER_2_5,
        MarketId.AWAY_OR_OVER_2_5,
        MarketId.HOME_OR_OVER_2_5,
        MarketId.DOUBLE_CHANCE,
        MarketId.BTTS,
        MarketId.DRAW_NO_BET,
        MarketId.HOME_WIN_TO_NIL,
        MarketId.AWAY_WIN_TO_NIL,
    }
)


MODEL_LEAGUE_EVIDENCE: dict[ModelLeagueFamily, ModelLeagueEvidenceState] = {
    ModelLeagueFamily.SCORE_MATRIX_XG: ModelLeagueEvidenceState(
        family=ModelLeagueFamily.SCORE_MATRIX_XG,
        ranking_authorized=False,
        primary_metric="mean_joint_poisson_nll",
        evidence_references=(
            "docs/fotmob_utc_native_expected_goals_model_validation_result_review.md",
        ),
        blocker=(
            "COMPETITION_IDENTITY_ABSENT_FROM_FROZEN_XG_VALIDATION: the reviewed "
            "xG result explicitly states league/competition robustness is blocked."
        ),
    ),
    ModelLeagueFamily.WIN_EITHER_HALF_HOME: ModelLeagueEvidenceState(
        family=ModelLeagueFamily.WIN_EITHER_HALF_HOME,
        ranking_authorized=False,
        primary_metric="binary_log_loss_then_brier_then_ece",
        evidence_references=(
            "docs/win_either_half_calibration_research.md",
            "artifacts/research-manifests/win-either-half-calibration-v1.json",
        ),
        blocker=(
            "EXACT_LEAGUE_METRIC_BYTES_NOT_COMMITTED: the reviewed documentation "
            "contains qualitative subgroup conclusions and hashes the 356-row "
            "subgroup CSV, but the exact per-league metric rows are not committed "
            "or otherwise replayable from this repository boundary."
        ),
    ),
    ModelLeagueFamily.WIN_EITHER_HALF_AWAY: ModelLeagueEvidenceState(
        family=ModelLeagueFamily.WIN_EITHER_HALF_AWAY,
        ranking_authorized=False,
        primary_metric="binary_log_loss_then_brier_then_ece",
        evidence_references=(
            "docs/win_either_half_calibration_research.md",
            "artifacts/research-manifests/win-either-half-calibration-v1.json",
        ),
        blocker=(
            "EXACT_LEAGUE_METRIC_BYTES_NOT_COMMITTED: Away retains identity "
            "calibration, but no exact committed per-league final-test metric table "
            "exists at this boundary from which a comparative league order can be "
            "reconstructed."
        ),
    ),
    ModelLeagueFamily.EARLY_PAYOUT_LEAD_PATH: ModelLeagueEvidenceState(
        family=ModelLeagueFamily.EARLY_PAYOUT_LEAD_PATH,
        ranking_authorized=False,
        primary_metric="independent_market_probability_log_loss",
        evidence_references=(
            "domain/early_payout_lead_path_probabilities.py",
        ),
        blocker=(
            "NO_INDEPENDENT_LEAGUE_LEVEL_VALIDATION: 1UP/2UP analytical semantics "
            "are reviewed, but no league-stratified held-out validation exists."
        ),
    ),
}


# Future reviewed evidence-ranked orders must be committed here only after the
# associated ModelLeagueEvidenceState has ranking_authorized=True and the exact
# replayable metric evidence has been reviewed.  The empty registry is
# intentional at this boundary.
_EVIDENCE_RANKS: dict[ModelLeagueFamily, dict[str, int]] = {}


def model_league_family_for_market(market_id: Any) -> ModelLeagueFamily | None:
    """Map one canonical market to the model family whose league evidence matters."""

    try:
        market = canonicalize_market_id(market_id)
    except (MarketRegistryError, TypeError, ValueError):
        return None

    if market in _SCORE_MATRIX_MARKETS:
        return ModelLeagueFamily.SCORE_MATRIX_XG
    if market == MarketId.HOME_WIN_EITHER_HALF:
        return ModelLeagueFamily.WIN_EITHER_HALF_HOME
    if market == MarketId.AWAY_WIN_EITHER_HALF:
        return ModelLeagueFamily.WIN_EITHER_HALF_AWAY
    if market in {MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP}:
        return ModelLeagueFamily.EARLY_PAYOUT_LEAD_PATH
    return None


def candidate_market_id(candidate: Mapping[str, Any]) -> Any:
    """Return the exact market identifier attached to the priced selection."""

    selection = candidate.get("accumulator_eligible_selection")
    if isinstance(selection, Mapping) and selection.get("market_id") is not None:
        return selection.get("market_id")
    return candidate.get("market_id")


def resolve_model_league_priority(
    league_name: str,
    *,
    market_id: Any,
) -> ModelLeaguePriorityResolution:
    """Resolve effective league order without inventing model reliability.

    Caller-supplied reliability scores/ranks are ignored.  Only the immutable
    reviewed registry in this module can create an evidence-ranked override.
    """

    league_entry = resolve_league_priority(league_name)
    bootstrap_rank = (
        league_entry.rank if league_entry is not None else UNPRIORITIZED_RANK
    )
    canonical_league = league_entry.canonical_name if league_entry is not None else None
    family = model_league_family_for_market(market_id)

    if family is None:
        return ModelLeaguePriorityResolution(
            policy_version=MODEL_LEAGUE_RELIABILITY_POLICY_VERSION,
            bootstrap_policy_version=PRIORITY_POLICY_VERSION,
            family=None,
            canonical_league=canonical_league,
            bootstrap_rank=bootstrap_rank,
            effective_rank=bootstrap_rank,
            basis=LeagueReliabilityBasis.MARKET_MODEL_FAMILY_UNRESOLVED,
            ranking_authorized=False,
            evidence_references=(),
            reason=(
                "No canonical market/model family was resolved; bootstrap league "
                "order is retained and no model-reliability claim is made."
            ),
        )

    evidence = MODEL_LEAGUE_EVIDENCE[family]
    ranked = _EVIDENCE_RANKS.get(family, {})
    if evidence.ranking_authorized and canonical_league in ranked:
        return ModelLeaguePriorityResolution(
            policy_version=MODEL_LEAGUE_RELIABILITY_POLICY_VERSION,
            bootstrap_policy_version=PRIORITY_POLICY_VERSION,
            family=family,
            canonical_league=canonical_league,
            bootstrap_rank=bootstrap_rank,
            effective_rank=ranked[canonical_league],
            basis=LeagueReliabilityBasis.EVIDENCE_RANKED,
            ranking_authorized=True,
            evidence_references=evidence.evidence_references,
            reason=(
                f"League rank comes from reviewed held-out {evidence.primary_metric} "
                f"evidence for {family.value}."
            ),
        )

    return ModelLeaguePriorityResolution(
        policy_version=MODEL_LEAGUE_RELIABILITY_POLICY_VERSION,
        bootstrap_policy_version=PRIORITY_POLICY_VERSION,
        family=family,
        canonical_league=canonical_league,
        bootstrap_rank=bootstrap_rank,
        effective_rank=bootstrap_rank,
        basis=LeagueReliabilityBasis.BOOTSTRAP_FALLBACK,
        ranking_authorized=False,
        evidence_references=evidence.evidence_references,
        reason=evidence.blocker
        or "No reviewed evidence-ranked league order exists for this model family.",
    )


def resolve_candidate_model_league_priority(
    candidate: Mapping[str, Any],
) -> ModelLeaguePriorityResolution:
    return resolve_model_league_priority(
        str(candidate.get("league") or ""),
        market_id=candidate_market_id(candidate),
    )
