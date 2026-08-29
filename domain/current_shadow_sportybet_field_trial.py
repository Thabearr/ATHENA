"""Research-only current ATHENA -> SportyBet shadow field-trial policy.

This boundary is deliberately separate from the production Phase 6 -> Price-all
v3 -> Router v3 -> Portfolio v3 chain. It consumes only:
1. a verified *complete current* PR151 durable-history handoff, and
2. a source-replayed PR252 current SportyBet canonical mapping rebind.

It derives the exact PR149 sealed shadow prediction from that complete history,
reconstructs the exact retained current SportyBet event-detail inventory, prices
only exact reviewed Total Goals half-line partitions, and applies the frozen
Router/Portfolio policy constants for research evaluation. PR252 exact semantics
remain authoritative; one PR258 research-only review may additionally reconcile
the current provider's market-18 display-label rename from ``Total Goals`` to
``Over/Under`` when native IDs, specifier, outcome labels and line semantics all
remain exact.

It never mints CalibratedValueCandidate values, production Phase 6 authority,
production selection authority, SportyBet execution authority, stake authority,
or BET authority. NO_BET and portfolio shortfall are valid research outcomes.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import re
import types
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from domain import current_direct_provider_canonical_market_mapping_rebind as current_mapping
from domain import current_fotmob_latest_durable_fresh_history as latest_history
from domain import current_fotmob_utc_native_shadow_prediction as shadow
from domain import fotmob_utc_native_expected_goals_fresh_holdout as fresh
from domain import score_matrix
from domain import sportybet_live_event_quote_evidence as live
from domain._accumulator_optimizer_contracts import (
    EXPECTED_ACCUMULATOR_OPTIMIZER_CONTRACT_SHA256_BY_VERSION,
    MAXIMUM_COMPETITION_SHARE,
    MAXIMUM_FRAGILE_SHARE,
    MAXIMUM_MARKET_FAMILY_SHARE,
    MAXIMUM_TARGET_SIZE,
    MAXIMUM_TEAM_APPEARANCES,
    MINIMUM_COMPETITION_CAP_WHEN_TARGET_GE_2,
    MINIMUM_FRAGILE_CAP,
    MINIMUM_MARKET_FAMILY_CAP_WHEN_TARGET_GE_2,
    MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE,
    MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE,
    validate_accumulator_optimizer_contract,
)
from domain._market_router_contracts import (
    MINIMUM_EVENT_PROBABILITY,
    MINIMUM_NET_EXPECTED_VALUE,
    MINIMUM_ROBUST_EDGE,
    MINIMUM_ROBUST_NET_EXPECTED_VALUE,
)
from domain.markets import MarketFamily, MarketId, OutcomeId


SCHEMA_VERSION = 2
DATASET_NAME = "athena-current-shadow-sportybet-field-trial-v2"
STATUS = "RESEARCH_ONLY_CURRENT_SHADOW_FIELD_TRIAL_SOURCE_BOUND"
PROVIDER = "SportyBet"
MAX_SOURCE_AGE_SECONDS = 900
MINIMUM_LEAD_SECONDS = 120
REVIEWED_TOTAL_GOALS_PROVIDER_MARKET_ID = "18"
REVIEWED_TOTAL_GOALS_SOURCE_LABEL = "Total Goals"
REVIEWED_TOTAL_GOALS_CURRENT_LABEL = "Over/Under"
MARKET_LABEL_RENAME_POLICY_ID = (
    "PR258_REVIEWED_MARKET18_TOTAL_GOALS_TO_OVER_UNDER_"
    "EXACT_NATIVE_ID_SPECIFIER_OUTCOME_LABEL_V1"
)
MARKET_POLICY_ID = (
    "EXACT_PR252_TOTAL_GOALS_OR_REVIEWED_PR258_MARKET18_LABEL_RENAME_HALF_LINES_V3"
)
VALUE_POLICY_ID = (
    "COMPLETE_CURRENT_PR151_PR149_CALIBRATED_XG_POISSON_PLUS_"
    "EXACT_CURRENT_PROVIDER_DECIMAL_ODDS_RESEARCH_V2"
)
ROUTER_POLICY_ID = "FROZEN_ROUTER_V2_THRESHOLDS_SINGLE_SHADOW_MODEL_RESEARCH_V2"
PORTFOLIO_POLICY_ID = (
    "FROZEN_PORTFOLIO_V2_CAPS_MARGINAL_ORDER_AND_PORTFOLIO_TIME_FRESHNESS_RECHECK_V2"
)
SOURCE_BINDING_POLICY_ID = (
    "LATEST_PR151_SHADOW_AND_PR252_MAPPING_MUST_SHARE_EXACT_FOTMOB_CAPTURE_ANCESTRY_V1"
)
SHORTFALL_POLICY_ID = "TARGET_IS_NOT_PADDED_RESEARCH_SHORTFALL_IS_VALID_V2"
NEXT_BOUNDARY = "ANONYMOUS_RESEARCH_SHARE_CODE_CREATE_RELOAD_VERIFICATION_OPTIONAL"

AUTHORITY = types.MappingProxyType(
    {
        "complete_current_fresh_history_proof": True,
        "reviewed_current_fixture_identity": True,
        "reviewed_shadow_expected_goals": True,
        "exact_reviewed_current_market_mapping": True,
        "research_score_matrix": True,
        "research_market_probability": True,
        "research_current_provider_value": True,
        "research_field_trial_routing": True,
        "research_field_trial_portfolio": True,
        "production_model": False,
        "production_probability": False,
        "phase6": False,
        "production_price_all": False,
        "production_market_router": False,
        "production_portfolio": False,
        "production_selection": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)

_TOTAL_SPECIFIER_RE = re.compile(
    r"^total=(-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)$",
    re.ASCII,
)
_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)
_SAFE_PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9_.:+/=-]{1,160}$", re.ASCII)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


class CurrentShadowSportyBetFieldTrialError(ValueError):
    """Raised when the research field trial cannot preserve exact source semantics."""


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise CurrentShadowSportyBetFieldTrialError(
            f"{label} must be timezone-aware"
        )
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentShadowSportyBetFieldTrialError(f"{label} is invalid") from exc


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentShadowSportyBetFieldTrialError(
            "canonical serialization failed"
        ) from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _strict_sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise CurrentShadowSportyBetFieldTrialError(
            f"{label} must be exact lowercase SHA-256"
        )
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CurrentShadowSportyBetFieldTrialError(
            f"{label} must be finite numeric"
        )
    result = float(value)
    if not math.isfinite(result):
        raise CurrentShadowSportyBetFieldTrialError(
            f"{label} must be finite numeric"
        )
    return result


def _probability(value: Any, label: str) -> float:
    result = _finite(value, label)
    if not 0.0 <= result <= 1.0:
        raise CurrentShadowSportyBetFieldTrialError(
            f"{label} must be within [0,1]"
        )
    return result


def _source_id(value: str) -> int:
    if type(value) is not str or not value.startswith("FOTMOB:"):
        raise CurrentShadowSportyBetFieldTrialError(
            "fixture_identifier must be exact FOTMOB:<id>"
        )
    raw = value.removeprefix("FOTMOB:")
    if not raw.isdigit() or int(raw) <= 0 or str(int(raw)) != raw:
        raise CurrentShadowSportyBetFieldTrialError(
            "fixture_identifier has invalid canonical FotMob ID"
        )
    return int(raw)


def _provider_id(value: Any, label: str) -> str:
    if type(value) is not str or _SAFE_PROVIDER_ID_RE.fullmatch(value) is None:
        raise CurrentShadowSportyBetFieldTrialError(
            f"{label} is not an exact safe provider-native ID"
        )
    return value


def _event_id(value: Any) -> str:
    if type(value) is not str or _EVENT_RE.fullmatch(value) is None:
        raise CurrentShadowSportyBetFieldTrialError(
            "event_id must use exact sr:match:<positive integer> form"
        )
    return value


def _exact_text(value: Any, label: str, *, maximum: int = 300) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    ):
        raise CurrentShadowSportyBetFieldTrialError(
            f"{label} must be exact non-empty trimmed text"
        )
    return value


def _half_line(value: float) -> bool:
    doubled = value * 2.0
    return (
        math.isfinite(doubled)
        and abs(doubled - round(doubled)) <= 1e-12
        and int(round(doubled)) % 2 == 1
    )


def _target_cap(target: int, share: float, minimum_when_multi: int) -> int:
    if target == 1:
        return 1
    return min(
        target,
        max(minimum_when_multi, int(math.ceil(target * share))),
    )


def _caps(target: int) -> Mapping[str, int]:
    return types.MappingProxyType(
        {
            "team": MAXIMUM_TEAM_APPEARANCES,
            "competition": _target_cap(
                target,
                MAXIMUM_COMPETITION_SHARE,
                MINIMUM_COMPETITION_CAP_WHEN_TARGET_GE_2,
            ),
            "market_family": _target_cap(
                target,
                MAXIMUM_MARKET_FAMILY_SHARE,
                MINIMUM_MARKET_FAMILY_CAP_WHEN_TARGET_GE_2,
            ),
            "fragile": min(
                target,
                max(
                    MINIMUM_FRAGILE_CAP,
                    int(math.ceil(target * MAXIMUM_FRAGILE_SHARE)),
                ),
            ),
        }
    )


def _validate_policy_dependencies() -> Mapping[str, str]:
    try:
        optimizer = validate_accumulator_optimizer_contract()
        live_contract = live.validate_direct_event_source_contract()
        mapping_contract = current_mapping.validate_current_mapping_rebind_contract()
    except Exception as exc:
        raise CurrentShadowSportyBetFieldTrialError(
            "reviewed research dependencies drifted"
        ) from exc

    expected_optimizer = (
        EXPECTED_ACCUMULATOR_OPTIMIZER_CONTRACT_SHA256_BY_VERSION[1]
    )
    if (
        optimizer["accumulator_optimizer_contract_sha256"]
        != expected_optimizer
    ):
        raise CurrentShadowSportyBetFieldTrialError(
            "frozen Portfolio-v2 policy identity drifted"
        )
    if live_contract["contract_sha256"] != live.EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowSportyBetFieldTrialError(
            "current SportyBet event source identity drifted"
        )
    if mapping_contract != current_mapping.EXPECTED_CONTRACT_SHA256:
        raise CurrentShadowSportyBetFieldTrialError(
            "PR252 current mapping contract identity drifted"
        )
    if (
        MINIMUM_EVENT_PROBABILITY != 0.55
        or MINIMUM_NET_EXPECTED_VALUE != 0.0
        or MINIMUM_ROBUST_NET_EXPECTED_VALUE != 0.0
        or MINIMUM_ROBUST_EDGE != 0.0
    ):
        raise CurrentShadowSportyBetFieldTrialError(
            "frozen Router threshold identity drifted"
        )
    if (
        latest_history.DATASET_NAME
        != "athena-current-fotmob-latest-durable-fresh-history-v1"
        or latest_history.STATUS
        != "VERIFIED_COMPLETE_CURRENT_PR151_DURABLE_HISTORY_PREFIX"
    ):
        raise CurrentShadowSportyBetFieldTrialError(
            "complete-current-history boundary identity drifted"
        )
    return types.MappingProxyType(
        {
            "accumulator_optimizer_v2_contract_sha256": expected_optimizer,
            "live_event_source_contract_sha256": live.EXPECTED_CONTRACT_SHA256,
            "current_mapping_rebind_contract_sha256": (
                current_mapping.EXPECTED_CONTRACT_SHA256
            ),
            "complete_current_history_dataset": latest_history.DATASET_NAME,
        }
    )


@dataclasses.dataclass(frozen=True)
class ResearchFixtureIdentity:
    fixture_identifier: str
    event_id: str
    home_team: str
    away_team: str
    competition: str
    kickoff_utc: datetime

    def __post_init__(self) -> None:
        _source_id(self.fixture_identifier)
        _event_id(self.event_id)
        _exact_text(self.home_team, "home_team")
        _exact_text(self.away_team, "away_team")
        _exact_text(self.competition, "competition")
        if self.home_team == self.away_team:
            raise CurrentShadowSportyBetFieldTrialError(
                "home_team and away_team must differ"
            )
        object.__setattr__(
            self,
            "kickoff_utc",
            _utc(self.kickoff_utc, "kickoff_utc"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identifier": self.fixture_identifier,
            "event_id": self.event_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition": self.competition,
            "kickoff_utc": self.kickoff_utc.isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
        }


def _opportunity_identity_payload(
    *,
    fixture: ResearchFixtureIdentity,
    sealed_prediction_sha256: str,
    latest_history_sha256: str,
    current_mapping_rebind_sha256: str,
    mapped_selection_sha256: str,
    current_inventory_sha256: str,
    provider_market_id: str,
    provider_specifier: str,
    provider_outcome_id: str,
    decimal_odds: float,
    event_probability: float,
    evaluation_time: datetime,
) -> dict[str, Any]:
    return {
        "fixture": fixture.to_dict(),
        "sealed_prediction_sha256": sealed_prediction_sha256,
        "latest_history_sha256": latest_history_sha256,
        "current_mapping_rebind_sha256": current_mapping_rebind_sha256,
        "mapped_selection_sha256": mapped_selection_sha256,
        "current_inventory_sha256": current_inventory_sha256,
        "provider_market_id": provider_market_id,
        "provider_specifier": provider_specifier,
        "provider_outcome_id": provider_outcome_id,
        "decimal_odds": decimal_odds,
        "event_probability": event_probability,
        "evaluation_time": evaluation_time.isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
    }


@dataclasses.dataclass(frozen=True)
class ResearchTotalGoalsOpportunity:
    opportunity_id: str
    fixture: ResearchFixtureIdentity
    sealed_prediction_sha256: str
    latest_history_sha256: str
    current_mapping_rebind_sha256: str
    mapped_selection_sha256: str
    decision_evaluation_time: datetime
    home_expected_goals: float
    away_expected_goals: float
    provider_market_id: str
    provider_market_name: str
    provider_specifier: str
    provider_outcome_id: str
    provider_outcome_name: str
    outcome_id: OutcomeId
    line: float
    decimal_odds: float
    quote_observed_at: datetime
    quote_age_seconds: float
    kickoff_lead_seconds: float
    event_probability: float
    fair_probability: float
    robust_edge: float
    net_expected_value: float
    survival_probability: float
    eligible: bool
    rejection_reasons: tuple[str, ...]
    fragile: bool
    current_inventory_sha256: str
    source_manifest_sha256: str
    source_raw_sha256: str

    def __post_init__(self) -> None:
        _strict_sha(self.opportunity_id, "opportunity_id")
        _strict_sha(self.sealed_prediction_sha256, "sealed_prediction_sha256")
        _strict_sha(self.latest_history_sha256, "latest_history_sha256")
        _strict_sha(
            self.current_mapping_rebind_sha256,
            "current_mapping_rebind_sha256",
        )
        _strict_sha(self.mapped_selection_sha256, "mapped_selection_sha256")
        _strict_sha(self.current_inventory_sha256, "current_inventory_sha256")
        _strict_sha(self.source_manifest_sha256, "source_manifest_sha256")
        _strict_sha(self.source_raw_sha256, "source_raw_sha256")
        if type(self.fixture) is not ResearchFixtureIdentity:
            raise CurrentShadowSportyBetFieldTrialError(
                "opportunity fixture type mismatch"
            )
        evaluation = _utc(
            self.decision_evaluation_time,
            "decision_evaluation_time",
        )
        observed = _utc(self.quote_observed_at, "quote_observed_at")
        object.__setattr__(self, "decision_evaluation_time", evaluation)
        object.__setattr__(self, "quote_observed_at", observed)
        _provider_id(self.provider_market_id, "provider_market_id")
        _provider_id(self.provider_outcome_id, "provider_outcome_id")
        if self.provider_market_name not in {
            REVIEWED_TOTAL_GOALS_SOURCE_LABEL,
            REVIEWED_TOTAL_GOALS_CURRENT_LABEL,
        }:
            raise CurrentShadowSportyBetFieldTrialError(
                "research opportunity escaped reviewed Total Goals provider labels"
            )
        if (
            self.provider_market_name == REVIEWED_TOTAL_GOALS_CURRENT_LABEL
            and self.provider_market_id != REVIEWED_TOTAL_GOALS_PROVIDER_MARKET_ID
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "current Over/Under label is reviewed only for exact provider market 18"
            )
        _exact_text(self.provider_outcome_name, "provider_outcome_name")
        match = _TOTAL_SPECIFIER_RE.fullmatch(self.provider_specifier)
        if match is None:
            raise CurrentShadowSportyBetFieldTrialError(
                "research opportunity has invalid Total Goals specifier"
            )
        parsed_line = float(match.group(1))
        line = _finite(self.line, "line")
        if (
            line < 0
            or not _half_line(line)
            or not math.isclose(
                parsed_line,
                line,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "research opportunity line/specifier semantics differ"
            )
        expected_provider_name: str
        if self.outcome_id is OutcomeId.OVER:
            expected_provider_name = f"Over {line:g}"
        elif self.outcome_id is OutcomeId.UNDER:
            expected_provider_name = f"Under {line:g}"
        else:
            raise CurrentShadowSportyBetFieldTrialError(
                "Total Goals opportunity outcome must be OVER or UNDER"
            )
        if self.provider_outcome_name != expected_provider_name:
            raise CurrentShadowSportyBetFieldTrialError(
                "provider outcome label differs from exact reviewed line semantics"
            )
        odds = _finite(self.decimal_odds, "decimal_odds")
        if odds <= 1.0:
            raise CurrentShadowSportyBetFieldTrialError(
                "decimal_odds must exceed 1"
            )
        home_xg = _finite(self.home_expected_goals, "home_expected_goals")
        away_xg = _finite(self.away_expected_goals, "away_expected_goals")
        if home_xg < 0 or away_xg < 0:
            raise CurrentShadowSportyBetFieldTrialError(
                "expected-goals rates must be non-negative"
            )
        quote_age = _finite(self.quote_age_seconds, "quote_age_seconds")
        lead = _finite(self.kickoff_lead_seconds, "kickoff_lead_seconds")
        if quote_age < 0:
            raise CurrentShadowSportyBetFieldTrialError(
                "quote_age_seconds must be non-negative"
            )
        p = _probability(self.event_probability, "event_probability")
        fair = _probability(self.fair_probability, "fair_probability")
        survival = _probability(
            self.survival_probability,
            "survival_probability",
        )
        edge = _finite(self.robust_edge, "robust_edge")
        net_ev = _finite(self.net_expected_value, "net_expected_value")
        if not math.isclose(
            survival,
            p,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "ordinary Total Goals survival must equal event probability"
            )
        if not math.isclose(
            edge,
            p - fair,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "robust_edge differs from research event-minus-fair probability"
            )
        if not math.isclose(
            net_ev,
            p * odds - 1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "net_expected_value differs from exact research EV"
            )
        reasons = tuple(sorted(set(self.rejection_reasons)))
        if type(self.rejection_reasons) is not tuple or reasons != self.rejection_reasons:
            raise CurrentShadowSportyBetFieldTrialError(
                "rejection_reasons must be sorted unique tuple"
            )
        if type(self.eligible) is not bool or self.eligible is not (not reasons):
            raise CurrentShadowSportyBetFieldTrialError(
                "eligible flag must correspond exactly to rejection reasons"
            )
        expected_fragile = (
            net_ev < MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE
            or p < MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE
        )
        if type(self.fragile) is not bool or self.fragile is not expected_fragile:
            raise CurrentShadowSportyBetFieldTrialError(
                "fragility flag differs from frozen Portfolio-v2 thresholds"
            )
        expected_id = _sha(
            _opportunity_identity_payload(
                fixture=self.fixture,
                sealed_prediction_sha256=self.sealed_prediction_sha256,
                latest_history_sha256=self.latest_history_sha256,
                current_mapping_rebind_sha256=self.current_mapping_rebind_sha256,
                mapped_selection_sha256=self.mapped_selection_sha256,
                current_inventory_sha256=self.current_inventory_sha256,
                provider_market_id=self.provider_market_id,
                provider_specifier=self.provider_specifier,
                provider_outcome_id=self.provider_outcome_id,
                decimal_odds=odds,
                event_probability=p,
                evaluation_time=evaluation,
            )
        )
        if self.opportunity_id != expected_id:
            raise CurrentShadowSportyBetFieldTrialError(
                "opportunity_id differs from exact research source/value identity"
            )
        object.__setattr__(self, "line", line)
        object.__setattr__(self, "decimal_odds", odds)
        object.__setattr__(self, "home_expected_goals", home_xg)
        object.__setattr__(self, "away_expected_goals", away_xg)
        object.__setattr__(self, "quote_age_seconds", quote_age)
        object.__setattr__(self, "kickoff_lead_seconds", lead)
        object.__setattr__(self, "event_probability", p)
        object.__setattr__(self, "fair_probability", fair)
        object.__setattr__(self, "survival_probability", survival)
        object.__setattr__(self, "robust_edge", edge)
        object.__setattr__(self, "net_expected_value", net_ev)

    def semantic_intent(self) -> dict[str, Any]:
        return {
            "eventId": self.fixture.event_id,
            "homeTeamName": self.fixture.home_team,
            "awayTeamName": self.fixture.away_team,
            "marketName": self.provider_market_name,
            "outcomeName": self.provider_outcome_name,
            "specifier": self.provider_specifier,
        }

    def expected_provider_native_identity(self) -> dict[str, str]:
        return {
            "eventId": self.fixture.event_id,
            "marketId": self.provider_market_id,
            "outcomeId": self.provider_outcome_id,
            "specifier": self.provider_specifier,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "fixture": self.fixture.to_dict(),
            "sealed_prediction_sha256": self.sealed_prediction_sha256,
            "latest_history_sha256": self.latest_history_sha256,
            "current_mapping_rebind_sha256": (
                self.current_mapping_rebind_sha256
            ),
            "mapped_selection_sha256": self.mapped_selection_sha256,
            "decision_evaluation_time": self.decision_evaluation_time.isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
            "home_expected_goals": self.home_expected_goals,
            "away_expected_goals": self.away_expected_goals,
            "market_id": MarketId.TOTAL_GOALS.value,
            "market_family": MarketFamily.TOTAL_GOALS.value,
            "provider_market_id": self.provider_market_id,
            "provider_market_name": self.provider_market_name,
            "provider_specifier": self.provider_specifier,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_outcome_name": self.provider_outcome_name,
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "decimal_odds": self.decimal_odds,
            "quote_observed_at": self.quote_observed_at.isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
            "quote_age_seconds": self.quote_age_seconds,
            "kickoff_lead_seconds": self.kickoff_lead_seconds,
            "event_probability": self.event_probability,
            "fair_probability": self.fair_probability,
            "robust_edge": self.robust_edge,
            "net_expected_value": self.net_expected_value,
            "survival_probability": self.survival_probability,
            "eligible": self.eligible,
            "rejection_reasons": list(self.rejection_reasons),
            "fragile": self.fragile,
            "current_inventory_sha256": self.current_inventory_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "semantic_intent": self.semantic_intent(),
            "expected_provider_native_identity": (
                self.expected_provider_native_identity()
            ),
        }


@dataclasses.dataclass(frozen=True)
class ResearchFixtureDecision:
    fixture: ResearchFixtureIdentity
    evaluation_time: datetime
    latest_history_sha256: str
    current_mapping_rebind_sha256: str
    status: str
    selected_opportunity_id: str | None
    opportunities: tuple[ResearchTotalGoalsOpportunity, ...]
    decision_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.fixture) is not ResearchFixtureIdentity:
            raise CurrentShadowSportyBetFieldTrialError(
                "decision fixture type mismatch"
            )
        evaluation = _utc(self.evaluation_time, "evaluation_time")
        _strict_sha(self.latest_history_sha256, "latest_history_sha256")
        _strict_sha(
            self.current_mapping_rebind_sha256,
            "current_mapping_rebind_sha256",
        )
        if self.status not in {"SELECTED", "NO_BET"}:
            raise CurrentShadowSportyBetFieldTrialError(
                "decision status escaped research vocabulary"
            )
        if type(self.opportunities) is not tuple or any(
            type(item) is not ResearchTotalGoalsOpportunity
            for item in self.opportunities
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "opportunities must be exact immutable tuple"
            )
        ids = [item.opportunity_id for item in self.opportunities]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise CurrentShadowSportyBetFieldTrialError(
                "opportunities must be sorted and unique"
            )
        for item in self.opportunities:
            if (
                item.fixture != self.fixture
                or item.decision_evaluation_time != evaluation
                or item.latest_history_sha256 != self.latest_history_sha256
                or item.current_mapping_rebind_sha256
                != self.current_mapping_rebind_sha256
            ):
                raise CurrentShadowSportyBetFieldTrialError(
                    "decision opportunity source identity mismatch"
                )
        reasons = tuple(sorted(set(self.decision_reasons)))
        if (
            type(self.decision_reasons) is not tuple
            or reasons != self.decision_reasons
            or not reasons
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "decision_reasons must be non-empty sorted unique tuple"
            )
        selected = [
            item
            for item in self.opportunities
            if item.opportunity_id == self.selected_opportunity_id
        ]
        if self.status == "SELECTED":
            if len(selected) != 1 or selected[0].eligible is not True:
                raise CurrentShadowSportyBetFieldTrialError(
                    "SELECTED decision must bind exactly one eligible opportunity"
                )
        elif self.selected_opportunity_id is not None:
            raise CurrentShadowSportyBetFieldTrialError(
                "NO_BET cannot carry selected_opportunity_id"
            )
        object.__setattr__(self, "evaluation_time", evaluation)

    @property
    def selected(self) -> ResearchTotalGoalsOpportunity | None:
        if self.selected_opportunity_id is None:
            return None
        return next(
            item
            for item in self.opportunities
            if item.opportunity_id == self.selected_opportunity_id
        )

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture": self.fixture.to_dict(),
            "evaluation_time": self.evaluation_time.isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
            "latest_history_sha256": self.latest_history_sha256,
            "current_mapping_rebind_sha256": (
                self.current_mapping_rebind_sha256
            ),
            "status": self.status,
            "selected_opportunity_id": self.selected_opportunity_id,
            "opportunities": [item.to_dict() for item in self.opportunities],
            "decision_reasons": list(self.decision_reasons),
        }


@dataclasses.dataclass(frozen=True)
class ResearchPortfolioExclusion:
    opportunity_id: str
    fixture_identifier: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _strict_sha(self.opportunity_id, "exclusion opportunity_id")
        _source_id(self.fixture_identifier)
        reasons = tuple(sorted(set(self.reasons)))
        if type(self.reasons) is not tuple or not reasons or reasons != self.reasons:
            raise CurrentShadowSportyBetFieldTrialError(
                "portfolio exclusion reasons must be non-empty sorted unique tuple"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "fixture_identifier": self.fixture_identifier,
            "reasons": list(self.reasons),
        }


@dataclasses.dataclass(frozen=True)
class ResearchShadowPortfolio:
    requested_target_size: int
    evaluation_time: datetime
    source_decision_sha256s: tuple[str, ...]
    selected_legs: tuple[ResearchTotalGoalsOpportunity, ...]
    reserve_legs: tuple[ResearchTotalGoalsOpportunity, ...]
    exclusions: tuple[ResearchPortfolioExclusion, ...]
    shortfall: int
    expected_slip_survival: float | None
    combined_decimal_odds_product: float | None
    caps: Mapping[str, int]
    authority: Mapping[str, bool]
    policy_identities: Mapping[str, str]

    def __post_init__(self) -> None:
        if (
            isinstance(self.requested_target_size, bool)
            or not isinstance(self.requested_target_size, int)
            or not 1 <= self.requested_target_size <= MAXIMUM_TARGET_SIZE
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "portfolio requested target size is invalid"
            )
        evaluation = _utc(self.evaluation_time, "portfolio evaluation_time")
        if type(self.source_decision_sha256s) is not tuple or any(
            type(item) is not str or _SHA_RE.fullmatch(item) is None
            for item in self.source_decision_sha256s
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "source decision identities are invalid"
            )
        if tuple(sorted(set(self.source_decision_sha256s))) != (
            self.source_decision_sha256s
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "source decision identities must be sorted unique tuple"
            )
        for values, label in (
            (self.selected_legs, "selected_legs"),
            (self.reserve_legs, "reserve_legs"),
        ):
            if type(values) is not tuple or any(
                type(item) is not ResearchTotalGoalsOpportunity
                for item in values
            ):
                raise CurrentShadowSportyBetFieldTrialError(
                    f"{label} must be immutable research opportunity tuple"
                )
        if type(self.exclusions) is not tuple or any(
            type(item) is not ResearchPortfolioExclusion
            for item in self.exclusions
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "exclusions must be immutable research exclusion tuple"
            )
        selected_ids = {item.opportunity_id for item in self.selected_legs}
        reserve_ids = {item.opportunity_id for item in self.reserve_legs}
        excluded_ids = {item.opportunity_id for item in self.exclusions}
        if (
            selected_ids & reserve_ids
            or selected_ids & excluded_ids
            or reserve_ids & excluded_ids
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "portfolio selected/reserve/excluded identities overlap"
            )
        expected_shortfall = max(
            0,
            self.requested_target_size - len(self.selected_legs),
        )
        if self.shortfall != expected_shortfall:
            raise CurrentShadowSportyBetFieldTrialError(
                "portfolio shortfall mismatch"
            )
        if dict(self.authority) != dict(AUTHORITY):
            raise CurrentShadowSportyBetFieldTrialError(
                "portfolio authority boundary changed"
            )
        if not isinstance(self.caps, Mapping) or set(self.caps) != {
            "team",
            "competition",
            "market_family",
            "fragile",
        }:
            raise CurrentShadowSportyBetFieldTrialError(
                "portfolio cap vocabulary changed"
            )
        if not isinstance(self.policy_identities, Mapping):
            raise CurrentShadowSportyBetFieldTrialError(
                "portfolio policy identities must be mapping"
            )
        object.__setattr__(self, "evaluation_time", evaluation)
        object.__setattr__(
            self,
            "authority",
            types.MappingProxyType(dict(AUTHORITY)),
        )
        object.__setattr__(
            self,
            "caps",
            types.MappingProxyType(dict(self.caps)),
        )
        object.__setattr__(
            self,
            "policy_identities",
            types.MappingProxyType(dict(self.policy_identities)),
        )

    @property
    def fulfilled(self) -> bool:
        return self.shortfall == 0

    @property
    def field_trial_status(self) -> str:
        if not self.selected_legs:
            return "RESEARCH_NO_QUALIFIED_LEGS"
        if self.fulfilled:
            return "RESEARCH_TARGET_QUALIFIED"
        return "RESEARCH_QUALIFIED_WITH_SHORTFALL"

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.to_dict())

    def semantic_intents(self) -> tuple[dict[str, Any], ...]:
        return tuple(item.semantic_intent() for item in self.selected_legs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "status": STATUS,
            "provider": PROVIDER,
            "field_trial_status": self.field_trial_status,
            "requested_target_size": self.requested_target_size,
            "evaluation_time": self.evaluation_time.isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
            "source_decision_sha256s": list(self.source_decision_sha256s),
            "selected_legs": [item.to_dict() for item in self.selected_legs],
            "reserve_legs": [item.to_dict() for item in self.reserve_legs],
            "exclusions": [item.to_dict() for item in self.exclusions],
            "selected_leg_count": len(self.selected_legs),
            "reserve_leg_count": len(self.reserve_legs),
            "excluded_leg_count": len(self.exclusions),
            "shortfall": self.shortfall,
            "fulfilled": self.fulfilled,
            "expected_slip_survival": self.expected_slip_survival,
            "expected_slip_survival_method": (
                "SINGLE_RESEARCH_SHADOW_MODEL_INDEPENDENCE_BASELINE_"
                "NOT_CORRELATION_ADJUSTED"
            ),
            "combined_decimal_odds_product": (
                self.combined_decimal_odds_product
            ),
            "caps": dict(self.caps),
            "source_binding_policy_id": SOURCE_BINDING_POLICY_ID,
            "market_policy_id": MARKET_POLICY_ID,
            "value_policy_id": VALUE_POLICY_ID,
            "router_policy_id": ROUTER_POLICY_ID,
            "portfolio_policy_id": PORTFOLIO_POLICY_ID,
            "shortfall_policy_id": SHORTFALL_POLICY_ID,
            "policy_identities": dict(self.policy_identities),
            "authority": dict(self.authority),
            "next_boundary": NEXT_BOUNDARY,
            "wager_placed": False,
        }


def _verify_latest_history(
    value: Any,
) -> latest_history.CurrentLatestDurableFreshHistoryHandoff:
    if type(value) is not latest_history.CurrentLatestDurableFreshHistoryHandoff:
        raise CurrentShadowSportyBetFieldTrialError(
            "complete latest PR151 history handoff is required"
        )
    try:
        checked = dataclasses.replace(value)
        latest_history.canonical_current_fotmob_latest_durable_fresh_history_handoff_bytes(
            checked
        )
    except Exception as exc:
        raise CurrentShadowSportyBetFieldTrialError(
            "complete latest PR151 history failed exact replay"
        ) from exc
    if (
        checked.latest_applicable_success_selection_proven is not True
        or checked.current_fresh_history_prefix_complete is not True
    ):
        raise CurrentShadowSportyBetFieldTrialError(
            "current fresh-history completeness is not proven"
        )
    if any(checked.authority.values()):
        raise CurrentShadowSportyBetFieldTrialError(
            "latest-history boundary unexpectedly acquired downstream authority"
        )
    return checked


def _verify_current_mapping(
    value: Any,
) -> current_mapping.CurrentDirectProviderCanonicalMarketMappingRebind:
    try:
        return current_mapping.verify_current_direct_provider_canonical_mapping_rebind(
            value
        )
    except Exception as exc:
        raise CurrentShadowSportyBetFieldTrialError(
            "PR252 current mapping failed exact retained-source replay"
        ) from exc


def _exact_current_inventory(
    mapping: current_mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
) -> live.SportyBetLiveEventQuoteInventory:
    detail_rows = tuple(mapping._current_bundle._detail_directories)
    matches = [
        Path(path)
        for event_id, path in detail_rows
        if event_id == mapping.event_id
    ]
    if len(matches) != 1:
        raise CurrentShadowSportyBetFieldTrialError(
            "PR252 mapping retained detail source is absent or ambiguous"
        )
    try:
        inventory = live.build_live_event_quote_inventory(
            matches[0],
            repository_root=mapping._current_bundle._repository_root,
        )
    except Exception as exc:
        raise CurrentShadowSportyBetFieldTrialError(
            "exact retained SportyBet event-detail inventory replay failed"
        ) from exc
    if (
        inventory.canonical_sha256 != mapping.current_inventory_sha256
        or inventory.source_manifest_sha256 != mapping.current_manifest_sha256
        or inventory.source_raw_sha256 != mapping.current_raw_sha256
        or inventory.event_id != mapping.event_id
        or inventory.home_team_name != mapping.home_team_name
        or inventory.away_team_name != mapping.away_team_name
        or inventory.kickoff_utc != mapping.kickoff_utc
    ):
        raise CurrentShadowSportyBetFieldTrialError(
            "retained current SportyBet inventory differs from PR252 mapping ancestry"
        )
    return inventory


def _fixture_and_shadow_row(
    history: latest_history.CurrentLatestDurableFreshHistoryHandoff,
    mapping: current_mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
) -> tuple[ResearchFixtureIdentity, shadow.CurrentUtcNativeShadowPredictionRow]:
    bundle = mapping._current_bundle
    rows = [
        row
        for row in bundle.rows
        if row.event_id == mapping.event_id
        and row.fixture_reconciliation_authorized is True
        and row.matched_fotmob_fixture_id == mapping.fixture_id
    ]
    if len(rows) != 1 or rows[0].competition_name is None:
        raise CurrentShadowSportyBetFieldTrialError(
            "PR252 mapping lost exact PR251 competition/fixture exposure identity"
        )
    fixture_identifier = f"FOTMOB:{mapping.fixture_id}"
    _source_id(fixture_identifier)
    shadow_rows = [
        row
        for row in history.shadow_handoff.rows
        if row.fixture_identifier == fixture_identifier
    ]
    if len(shadow_rows) != 1:
        raise CurrentShadowSportyBetFieldTrialError(
            "complete current shadow replay lacks exact mapped fixture"
        )
    shadow_row = shadow_rows[0]
    if (
        shadow_row.disposition != shadow.SEALED_COMPLETE_CASE
        or shadow_row.sealed_prediction is None
        or shadow_row.sealed_prediction_sha256 is None
        or shadow_row.kickoff_utc != mapping.kickoff_utc
    ):
        raise CurrentShadowSportyBetFieldTrialError(
            "mapped fixture does not have one sealed complete current shadow case"
        )
    fixture = ResearchFixtureIdentity(
        fixture_identifier=fixture_identifier,
        event_id=mapping.event_id,
        home_team=mapping.home_team_name,
        away_team=mapping.away_team_name,
        competition=rows[0].competition_name,
        kickoff_utc=mapping.kickoff_utc,
    )
    return fixture, shadow_row


def _prove_shared_fotmob_capture(
    history: latest_history.CurrentLatestDurableFreshHistoryHandoff,
    mapping: current_mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
) -> None:
    shadow_handoff = history.shadow_handoff
    source_manifest_sha = shadow_handoff.source_manifest_sha256
    source_raw_sha = shadow_handoff.source_raw_sha256
    identities = tuple(mapping._current_bundle.fotmob_capture_identities)
    matches = [
        item
        for item in identities
        if item.get("manifest_sha256") == source_manifest_sha
        and item.get("raw_sha256") == source_raw_sha
    ]
    if len(matches) != 1:
        raise CurrentShadowSportyBetFieldTrialError(
            "latest PR151 shadow and PR252 mapping do not share one exact FotMob capture ancestry"
        )


@dataclasses.dataclass(frozen=True)
class _ResearchCurrentTotalGoalsMapping:
    provider_market_id: str
    provider_market_name: str
    provider_specifier: str
    provider_outcome_id: str
    provider_outcome_name: str
    canonical_market_id: MarketId
    canonical_outcome_id: OutcomeId
    canonical_line: float
    source_mapping_row_sha256: str
    current_inventory_sha256: str
    mapping_basis: str

    def __post_init__(self) -> None:
        _provider_id(self.provider_market_id, "research mapped provider_market_id")
        _provider_id(self.provider_outcome_id, "research mapped provider_outcome_id")
        _exact_text(self.provider_market_name, "research mapped provider_market_name")
        _exact_text(self.provider_outcome_name, "research mapped provider_outcome_name")
        _strict_sha(self.source_mapping_row_sha256, "source_mapping_row_sha256")
        _strict_sha(self.current_inventory_sha256, "current_inventory_sha256")
        if self.canonical_market_id is not MarketId.TOTAL_GOALS:
            raise CurrentShadowSportyBetFieldTrialError(
                "research current mapping escaped Total Goals"
            )
        if self.canonical_outcome_id not in {OutcomeId.OVER, OutcomeId.UNDER}:
            raise CurrentShadowSportyBetFieldTrialError(
                "research current Total Goals mapping has invalid outcome"
            )
        line = _finite(self.canonical_line, "research mapped canonical total line")
        if line < 0 or not _half_line(line):
            raise CurrentShadowSportyBetFieldTrialError(
                "research current Total Goals mapping requires exact half line"
            )
        match = _TOTAL_SPECIFIER_RE.fullmatch(self.provider_specifier)
        if match is None or not math.isclose(
            float(match.group(1)), line, rel_tol=0.0, abs_tol=1e-12
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "research current Total Goals mapping line/specifier differs"
            )
        expected_outcome = (
            f"Over {line:g}"
            if self.canonical_outcome_id is OutcomeId.OVER
            else f"Under {line:g}"
        )
        if self.provider_outcome_name != expected_outcome:
            raise CurrentShadowSportyBetFieldTrialError(
                "research current Total Goals mapping outcome label differs"
            )
        if self.mapping_basis == "PR252_EXACT_REVIEWED_SEMANTICS":
            if self.provider_market_name != REVIEWED_TOTAL_GOALS_SOURCE_LABEL:
                raise CurrentShadowSportyBetFieldTrialError(
                    "exact PR252 Total Goals row changed provider label"
                )
        elif self.mapping_basis == MARKET_LABEL_RENAME_POLICY_ID:
            if (
                self.provider_market_id != REVIEWED_TOTAL_GOALS_PROVIDER_MARKET_ID
                or self.provider_market_name != REVIEWED_TOTAL_GOALS_CURRENT_LABEL
            ):
                raise CurrentShadowSportyBetFieldTrialError(
                    "reviewed current market-label rename escaped exact market-18 rule"
                )
        else:
            raise CurrentShadowSportyBetFieldTrialError(
                "research current mapping basis is unreviewed"
            )
        object.__setattr__(self, "canonical_line", line)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_market_id": self.provider_market_id,
            "provider_market_name": self.provider_market_name,
            "provider_specifier": self.provider_specifier,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_outcome_name": self.provider_outcome_name,
            "canonical_market_id": self.canonical_market_id.value,
            "canonical_outcome_id": self.canonical_outcome_id.value,
            "canonical_line": self.canonical_line,
            "source_mapping_row_sha256": self.source_mapping_row_sha256,
            "current_inventory_sha256": self.current_inventory_sha256,
            "mapping_basis": self.mapping_basis,
        }


def _reviewed_total_goals_label_rename_rows(
    mapping: current_mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
    inventory: live.SportyBetLiveEventQuoteInventory,
) -> tuple[_ResearchCurrentTotalGoalsMapping, ...]:
    if inventory.canonical_sha256 != mapping.current_inventory_sha256:
        raise CurrentShadowSportyBetFieldTrialError(
            "label-rename review is not bound to the PR252 current inventory"
        )
    native_index = {
        (item.market_id, item.specifier, item.outcome_id): item
        for item in inventory.selections
    }
    if len(native_index) != len(inventory.selections):
        raise CurrentShadowSportyBetFieldTrialError(
            "current inventory contains duplicate provider-native selection identity"
        )
    rows: list[_ResearchCurrentTotalGoalsMapping] = []
    for audit in mapping.mapping_audits:
        if (
            audit.disposition
            is not current_mapping.RebindAuditDisposition.CURRENT_PROVIDER_LABEL_DRIFT_REJECTED
            or audit.provider_market_id != REVIEWED_TOTAL_GOALS_PROVIDER_MARKET_ID
            or audit.reviewed_provider_market_name != REVIEWED_TOTAL_GOALS_SOURCE_LABEL
            or audit.current_provider_market_name != REVIEWED_TOTAL_GOALS_CURRENT_LABEL
            or audit.current_provider_outcome_name != audit.reviewed_provider_outcome_name
            or audit.provider_specifier is None
            or audit.canonical_market_id is not MarketId.TOTAL_GOALS
            or audit.canonical_outcome_id not in {OutcomeId.OVER, OutcomeId.UNDER}
            or audit.canonical_line is None
        ):
            continue
        line = _finite(audit.canonical_line, "reviewed renamed canonical total line")
        if line < 0 or not _half_line(line):
            continue
        selected = native_index.get(
            (audit.provider_market_id, audit.provider_specifier, audit.provider_outcome_id)
        )
        if (
            selected is None
            or selected.market_name != REVIEWED_TOTAL_GOALS_CURRENT_LABEL
            or selected.outcome_name != audit.reviewed_provider_outcome_name
            or selected.bookable is not True
        ):
            continue
        rows.append(
            _ResearchCurrentTotalGoalsMapping(
                provider_market_id=audit.provider_market_id,
                provider_market_name=selected.market_name,
                provider_specifier=audit.provider_specifier,
                provider_outcome_id=audit.provider_outcome_id,
                provider_outcome_name=selected.outcome_name,
                canonical_market_id=audit.canonical_market_id,
                canonical_outcome_id=audit.canonical_outcome_id,
                canonical_line=line,
                source_mapping_row_sha256=audit.source_mapping_row_sha256,
                current_inventory_sha256=inventory.canonical_sha256,
                mapping_basis=MARKET_LABEL_RENAME_POLICY_ID,
            )
        )
    return tuple(rows)


def _mapped_total_partitions(
    mapping: current_mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
    inventory: live.SportyBetLiveEventQuoteInventory,
) -> tuple[
    tuple[_ResearchCurrentTotalGoalsMapping, _ResearchCurrentTotalGoalsMapping],
    ...,
]:
    grouped: dict[
        tuple[str, str, float],
        dict[OutcomeId, _ResearchCurrentTotalGoalsMapping],
    ] = {}
    rows: list[_ResearchCurrentTotalGoalsMapping] = []
    for row in mapping.mapped_selections:
        if row.canonical_market_id is not MarketId.TOTAL_GOALS:
            continue
        if (
            row.canonical_line is None
            or row.provider_specifier is None
            or row.current_bookable_observed is not True
            or row.bookmaker_equivalence_authorized is not True
            or row.provider_market_name != REVIEWED_TOTAL_GOALS_SOURCE_LABEL
        ):
            continue
        line = _finite(row.canonical_line, "mapped canonical total line")
        if line < 0 or not _half_line(line):
            continue
        match = _TOTAL_SPECIFIER_RE.fullmatch(row.provider_specifier)
        if match is None or not math.isclose(
            float(match.group(1)), line, rel_tol=0.0, abs_tol=1e-12
        ):
            continue
        if row.canonical_outcome_id not in {OutcomeId.OVER, OutcomeId.UNDER}:
            continue
        rows.append(
            _ResearchCurrentTotalGoalsMapping(
                provider_market_id=row.provider_market_id,
                provider_market_name=row.provider_market_name,
                provider_specifier=row.provider_specifier,
                provider_outcome_id=row.provider_outcome_id,
                provider_outcome_name=row.provider_outcome_name,
                canonical_market_id=row.canonical_market_id,
                canonical_outcome_id=row.canonical_outcome_id,
                canonical_line=line,
                source_mapping_row_sha256=row.source_mapping_row_sha256,
                current_inventory_sha256=row.current_inventory_sha256,
                mapping_basis="PR252_EXACT_REVIEWED_SEMANTICS",
            )
        )
    rows.extend(_reviewed_total_goals_label_rename_rows(mapping, inventory))
    for row in rows:
        key = (row.provider_market_id, row.provider_specifier, row.canonical_line)
        bucket = grouped.setdefault(key, {})
        if row.canonical_outcome_id in bucket:
            raise CurrentShadowSportyBetFieldTrialError(
                "reviewed current mapping contains duplicate canonical total partition side"
            )
        bucket[row.canonical_outcome_id] = row
    pairs = []
    for key in sorted(grouped):
        sides = grouped[key]
        if set(sides) == {OutcomeId.OVER, OutcomeId.UNDER}:
            pairs.append((sides[OutcomeId.OVER], sides[OutcomeId.UNDER]))
    return tuple(pairs)


def build_source_bound_total_goals_research_decision(
    *,
    complete_current_history: latest_history.CurrentLatestDurableFreshHistoryHandoff,
    current_mapping_rebind: current_mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
    evaluation_time: datetime,
) -> ResearchFixtureDecision:
    """Build one source-bound research decision from complete current evidence.

    The function intentionally prices only exact PR252-mapped Total Goals
    partitions. Unreviewed provider lines are ignored even when present and even
    when they would look more attractive.
    """

    _validate_policy_dependencies()
    history = _verify_latest_history(complete_current_history)
    mapping = _verify_current_mapping(current_mapping_rebind)
    _prove_shared_fotmob_capture(history, mapping)
    fixture, shadow_row = _fixture_and_shadow_row(history, mapping)
    inventory = _exact_current_inventory(mapping)
    prediction = dataclasses.replace(shadow_row.sealed_prediction)
    sealed_sha = fresh.sha256_sealed_fresh_prediction(prediction)
    if sealed_sha != shadow_row.sealed_prediction_sha256:
        raise CurrentShadowSportyBetFieldTrialError(
            "sealed shadow prediction identity changed during source replay"
        )

    now = _utc(evaluation_time, "evaluation_time")
    observed = _utc(inventory.observed_at, "inventory observed_at")
    if now < mapping.evaluation_time:
        raise CurrentShadowSportyBetFieldTrialError(
            "research evaluation_time predates PR252 mapping issuance"
        )
    age = (now - observed).total_seconds()
    lead = (fixture.kickoff_utc - now).total_seconds()
    if not math.isfinite(age) or age < 0:
        raise CurrentShadowSportyBetFieldTrialError(
            "current provider observation is future-dated"
        )

    latest_sha = (
        latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff(
            history
        )
    )
    mapping_sha = _sha(mapping.to_dict())

    freshness_reasons: list[str] = []
    if age > MAX_SOURCE_AGE_SECONDS:
        freshness_reasons.append("CURRENT_PROVIDER_QUOTE_STALE")
    if not math.isfinite(lead) or lead <= MINIMUM_LEAD_SECONDS:
        freshness_reasons.append("FIXTURE_TOO_CLOSE_TO_KICKOFF")
    if inventory.prematch_bookable_observed is not True:
        freshness_reasons.append("CURRENT_EVENT_NOT_PREMATCH_BOOKABLE")
    if freshness_reasons:
        return ResearchFixtureDecision(
            fixture=fixture,
            evaluation_time=now,
            latest_history_sha256=latest_sha,
            current_mapping_rebind_sha256=mapping_sha,
            status="NO_BET",
            selected_opportunity_id=None,
            opportunities=(),
            decision_reasons=tuple(sorted(set(freshness_reasons))),
        )

    rates = dict(prediction.rates)
    if set(rates) != {
        "native_home",
        "native_away",
        "elo_only_home",
        "elo_only_away",
        "calibrated_home",
        "calibrated_away",
    }:
        raise CurrentShadowSportyBetFieldTrialError(
            "PR149 rate vocabulary drifted"
        )
    home_xg = _finite(rates["calibrated_home"], "calibrated_home")
    away_xg = _finite(rates["calibrated_away"], "calibrated_away")
    if home_xg < 0 or away_xg < 0:
        raise CurrentShadowSportyBetFieldTrialError(
            "calibrated rates must be non-negative"
        )
    matrix = score_matrix.build_score_matrix(home_xg, away_xg)

    native_index = {
        (item.market_id, item.specifier, item.outcome_id): item
        for item in inventory.selections
    }
    if len(native_index) != len(inventory.selections):
        raise CurrentShadowSportyBetFieldTrialError(
            "current inventory contains duplicate provider-native selection identity"
        )

    opportunities: list[ResearchTotalGoalsOpportunity] = []
    for over_map, under_map in _mapped_total_partitions(mapping, inventory):
        if (
            over_map.provider_market_id != under_map.provider_market_id
            or over_map.provider_specifier != under_map.provider_specifier
            or over_map.canonical_line != under_map.canonical_line
        ):
            raise CurrentShadowSportyBetFieldTrialError(
                "mapped Total Goals partition identity drifted"
            )
        line = _finite(over_map.canonical_line, "mapped total line")
        current_sides: dict[
            OutcomeId,
            live.SportyBetLiveEventSelection,
        ] = {}
        for mapped in (over_map, under_map):
            selected = native_index.get(
                (
                    mapped.provider_market_id,
                    mapped.provider_specifier,
                    mapped.provider_outcome_id,
                )
            )
            if selected is None:
                raise CurrentShadowSportyBetFieldTrialError(
                    "reviewed mapped selection is absent from retained current inventory"
                )
            if (
                selected.market_name != mapped.provider_market_name
                or selected.outcome_name != mapped.provider_outcome_name
                or selected.bookable is not True
            ):
                raise CurrentShadowSportyBetFieldTrialError(
                    "current provider selection differs from reviewed mapped semantics"
                )
            current_sides[mapped.canonical_outcome_id] = selected

        over = current_sides[OutcomeId.OVER]
        under = current_sides[OutcomeId.UNDER]
        over_odds = _finite(over.odds_decimal, "over decimal odds")
        under_odds = _finite(under.odds_decimal, "under decimal odds")
        if over_odds <= 1.0 or under_odds <= 1.0:
            raise CurrentShadowSportyBetFieldTrialError(
                "mapped current Total Goals odds must exceed 1"
            )
        implied_over = 1.0 / over_odds
        implied_under = 1.0 / under_odds
        implied_sum = implied_over + implied_under
        if not math.isfinite(implied_sum) or implied_sum <= 0:
            raise CurrentShadowSportyBetFieldTrialError(
                "exact mapped Total Goals implied partition is invalid"
            )
        fair = {
            OutcomeId.OVER: implied_over / implied_sum,
            OutcomeId.UNDER: implied_under / implied_sum,
        }
        event = {
            OutcomeId.OVER: matrix.over(line),
            OutcomeId.UNDER: matrix.under(line),
        }
        mapping_by_outcome = {
            OutcomeId.OVER: over_map,
            OutcomeId.UNDER: under_map,
        }
        selection_by_outcome = {
            OutcomeId.OVER: over,
            OutcomeId.UNDER: under,
        }

        for outcome_id in (OutcomeId.OVER, OutcomeId.UNDER):
            mapped = mapping_by_outcome[outcome_id]
            selected = selection_by_outcome[outcome_id]
            p = _probability(event[outcome_id], "event probability")
            fair_p = _probability(fair[outcome_id], "fair probability")
            odds = _finite(selected.odds_decimal, "decimal odds")
            net_ev = p * odds - 1.0
            edge = p - fair_p
            reasons: list[str] = []
            if p < MINIMUM_EVENT_PROBABILITY:
                reasons.append(
                    "EVENT_PROBABILITY_BELOW_FROZEN_ROUTER_THRESHOLD"
                )
            if (
                net_ev <= MINIMUM_NET_EXPECTED_VALUE
                or net_ev <= MINIMUM_ROBUST_NET_EXPECTED_VALUE
            ):
                reasons.append("NET_EXPECTED_VALUE_NOT_STRICTLY_POSITIVE")
            if edge <= MINIMUM_ROBUST_EDGE:
                reasons.append("ROBUST_EDGE_NOT_STRICTLY_POSITIVE")
            reasons_tuple = tuple(sorted(set(reasons)))
            fragile = (
                net_ev < MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE
                or p < MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE
            )
            mapped_sha = _sha(mapped.to_dict())
            identity_payload = _opportunity_identity_payload(
                fixture=fixture,
                sealed_prediction_sha256=sealed_sha,
                latest_history_sha256=latest_sha,
                current_mapping_rebind_sha256=mapping_sha,
                mapped_selection_sha256=mapped_sha,
                current_inventory_sha256=inventory.canonical_sha256,
                provider_market_id=selected.market_id,
                provider_specifier=selected.specifier or "",
                provider_outcome_id=selected.outcome_id,
                decimal_odds=odds,
                event_probability=p,
                evaluation_time=now,
            )
            opportunities.append(
                ResearchTotalGoalsOpportunity(
                    opportunity_id=_sha(identity_payload),
                    fixture=fixture,
                    sealed_prediction_sha256=sealed_sha,
                    latest_history_sha256=latest_sha,
                    current_mapping_rebind_sha256=mapping_sha,
                    mapped_selection_sha256=mapped_sha,
                    decision_evaluation_time=now,
                    home_expected_goals=home_xg,
                    away_expected_goals=away_xg,
                    provider_market_id=selected.market_id,
                    provider_market_name=selected.market_name,
                    provider_specifier=selected.specifier or "",
                    provider_outcome_id=selected.outcome_id,
                    provider_outcome_name=selected.outcome_name,
                    outcome_id=outcome_id,
                    line=line,
                    decimal_odds=odds,
                    quote_observed_at=observed,
                    quote_age_seconds=age,
                    kickoff_lead_seconds=lead,
                    event_probability=p,
                    fair_probability=fair_p,
                    robust_edge=edge,
                    net_expected_value=net_ev,
                    survival_probability=p,
                    eligible=not reasons_tuple,
                    rejection_reasons=reasons_tuple,
                    fragile=fragile,
                    current_inventory_sha256=inventory.canonical_sha256,
                    source_manifest_sha256=inventory.source_manifest_sha256,
                    source_raw_sha256=inventory.source_raw_sha256,
                )
            )

    ordered = tuple(
        sorted(opportunities, key=lambda item: item.opportunity_id)
    )
    eligible = [item for item in ordered if item.eligible]
    if not eligible:
        reason = (
            "NO_EXACT_REVIEWED_TOTAL_GOALS_PARTITION"
            if not ordered
            else "NO_ELIGIBLE_RESEARCH_TOTAL_GOALS_VALUE"
        )
        return ResearchFixtureDecision(
            fixture=fixture,
            evaluation_time=now,
            latest_history_sha256=latest_sha,
            current_mapping_rebind_sha256=mapping_sha,
            status="NO_BET",
            selected_opportunity_id=None,
            opportunities=ordered,
            decision_reasons=(reason,),
        )

    chosen = min(
        eligible,
        key=lambda item: (
            -item.net_expected_value,
            -item.robust_edge,
            -item.event_probability,
            item.quote_age_seconds,
            item.opportunity_id,
        ),
    )
    return ResearchFixtureDecision(
        fixture=fixture,
        evaluation_time=now,
        latest_history_sha256=latest_sha,
        current_mapping_rebind_sha256=mapping_sha,
        status="SELECTED",
        selected_opportunity_id=chosen.opportunity_id,
        opportunities=ordered,
        decision_reasons=(
            "RESEARCH_SHADOW_TOTAL_GOALS_ROBUST_VALUE_SELECTED",
        ),
    )


def _counts(
    selected: Sequence[ResearchTotalGoalsOpportunity],
) -> tuple[dict[str, int], dict[str, int], dict[str, int], int]:
    teams: dict[str, int] = {}
    competitions: dict[str, int] = {}
    families: dict[str, int] = {}
    fragile = 0
    for item in selected:
        for name in (item.fixture.home_team, item.fixture.away_team):
            teams[name] = teams.get(name, 0) + 1
        competitions[item.fixture.competition] = (
            competitions.get(item.fixture.competition, 0) + 1
        )
        family = MarketFamily.TOTAL_GOALS.value
        families[family] = families.get(family, 0) + 1
        fragile += int(item.fragile)
    return teams, competitions, families, fragile


def _constraint_reasons(
    candidate: ResearchTotalGoalsOpportunity,
    selected: Sequence[ResearchTotalGoalsOpportunity],
    caps: Mapping[str, int],
) -> tuple[str, ...]:
    teams, competitions, families, fragile = _counts(selected)
    reasons: list[str] = []
    for name in (candidate.fixture.home_team, candidate.fixture.away_team):
        if teams.get(name, 0) >= caps["team"]:
            reasons.append(f"TEAM_EXPOSURE_CAP:{name}")
    if competitions.get(candidate.fixture.competition, 0) >= caps["competition"]:
        reasons.append(
            f"COMPETITION_CONCENTRATION_CAP:{candidate.fixture.competition}"
        )
    family = MarketFamily.TOTAL_GOALS.value
    if families.get(family, 0) >= caps["market_family"]:
        reasons.append(f"MARKET_FAMILY_CONCENTRATION_CAP:{family}")
    if candidate.fragile and fragile >= caps["fragile"]:
        reasons.append("FRAGILITY_CAP")
    return tuple(sorted(set(reasons)))


def _marginal_key(
    candidate: ResearchTotalGoalsOpportunity,
    selected: Sequence[ResearchTotalGoalsOpportunity],
    caps: Mapping[str, int],
) -> tuple[Any, ...]:
    _teams, competitions, families, fragile = _counts(selected)
    family = MarketFamily.TOTAL_GOALS.value
    exposure_penalty = (
        competitions.get(candidate.fixture.competition, 0)
        / caps["competition"]
        + families.get(family, 0) / caps["market_family"]
        + ((fragile / caps["fragile"]) if candidate.fragile else 0.0)
    )
    return (
        exposure_penalty,
        -candidate.survival_probability,
        -candidate.net_expected_value,
        -candidate.robust_edge,
        candidate.quote_age_seconds,
        candidate.opportunity_id,
    )


def optimize_research_shadow_portfolio(
    decisions: Sequence[ResearchFixtureDecision],
    *,
    target_size: int,
    evaluation_time: datetime,
) -> ResearchShadowPortfolio:
    """Optimize source-bound research decisions with portfolio-time rechecks."""

    identities = _validate_policy_dependencies()
    now = _utc(evaluation_time, "evaluation_time")
    if (
        isinstance(target_size, bool)
        or not isinstance(target_size, int)
        or not 1 <= target_size <= MAXIMUM_TARGET_SIZE
    ):
        raise CurrentShadowSportyBetFieldTrialError(
            f"target_size must be an integer from 1 through {MAXIMUM_TARGET_SIZE}"
        )
    if (
        isinstance(decisions, (str, bytes))
        or not isinstance(decisions, Sequence)
    ):
        raise CurrentShadowSportyBetFieldTrialError(
            "decisions must be a sequence"
        )
    rows = tuple(decisions)
    if any(type(item) is not ResearchFixtureDecision for item in rows):
        raise CurrentShadowSportyBetFieldTrialError(
            "decisions contain invalid item"
        )
    checked = tuple(dataclasses.replace(item) for item in rows)
    fixture_ids = [item.fixture.fixture_identifier for item in checked]
    event_ids = [item.fixture.event_id for item in checked]
    if (
        len(fixture_ids) != len(set(fixture_ids))
        or len(event_ids) != len(set(event_ids))
    ):
        raise CurrentShadowSportyBetFieldTrialError(
            "duplicate fixture/event decisions are forbidden"
        )

    admitted: list[ResearchTotalGoalsOpportunity] = []
    exclusions: list[ResearchPortfolioExclusion] = []
    for decision in sorted(
        checked,
        key=lambda item: item.fixture.fixture_identifier,
    ):
        if decision.evaluation_time > now:
            raise CurrentShadowSportyBetFieldTrialError(
                "portfolio evaluation_time predates a research decision"
            )
        selected = decision.selected
        if selected is None:
            continue
        age = (now - selected.quote_observed_at).total_seconds()
        lead = (selected.fixture.kickoff_utc - now).total_seconds()
        reasons: list[str] = []
        if not math.isfinite(age) or age < 0:
            raise CurrentShadowSportyBetFieldTrialError(
                "portfolio quote age is invalid or future-dated"
            )
        if age > MAX_SOURCE_AGE_SECONDS:
            reasons.append("CURRENT_PROVIDER_QUOTE_STALE_AT_PORTFOLIO_TIME")
        if not math.isfinite(lead) or lead <= MINIMUM_LEAD_SECONDS:
            reasons.append(
                "FIXTURE_TOO_CLOSE_TO_KICKOFF_AT_PORTFOLIO_TIME"
            )
        if reasons:
            exclusions.append(
                ResearchPortfolioExclusion(
                    opportunity_id=selected.opportunity_id,
                    fixture_identifier=selected.fixture.fixture_identifier,
                    reasons=tuple(sorted(set(reasons))),
                )
            )
            continue
        admitted.append(selected)

    caps = _caps(target_size)
    remaining = sorted(admitted, key=lambda item: item.opportunity_id)
    selected: list[ResearchTotalGoalsOpportunity] = []
    while remaining and len(selected) < target_size:
        admissible = [
            item
            for item in remaining
            if not _constraint_reasons(item, selected, caps)
        ]
        if not admissible:
            break
        chosen = min(
            admissible,
            key=lambda item: _marginal_key(item, selected, caps),
        )
        selected.append(chosen)
        remaining = [
            item
            for item in remaining
            if item.opportunity_id != chosen.opportunity_id
        ]

    selected = sorted(selected, key=lambda item: item.opportunity_id)
    selected_ids = {item.opportunity_id for item in selected}
    reserves = tuple(
        sorted(
            (
                item
                for item in admitted
                if item.opportunity_id not in selected_ids
            ),
            key=lambda item: (
                -item.survival_probability,
                -item.net_expected_value,
                -item.robust_edge,
                item.quote_age_seconds,
                item.opportunity_id,
            ),
        )
    )
    survival = (
        None
        if not selected
        else math.prod(item.survival_probability for item in selected)
    )
    if survival is not None and not math.isfinite(survival):
        raise CurrentShadowSportyBetFieldTrialError(
            "research survival product is non-finite"
        )
    odds_product: float | None = None
    if selected:
        odds_value = Decimal("1")
        for item in selected:
            odds_value *= Decimal(str(item.decimal_odds))
        parsed = float(odds_value)
        odds_product = parsed if math.isfinite(parsed) else None

    decision_hashes = tuple(
        sorted(item.canonical_sha256 for item in checked)
    )
    return ResearchShadowPortfolio(
        requested_target_size=target_size,
        evaluation_time=now,
        source_decision_sha256s=decision_hashes,
        selected_legs=tuple(selected),
        reserve_legs=reserves,
        exclusions=tuple(
            sorted(exclusions, key=lambda item: item.opportunity_id)
        ),
        shortfall=max(0, target_size - len(selected)),
        expected_slip_survival=survival,
        combined_decimal_odds_product=odds_product,
        caps=caps,
        authority=AUTHORITY,
        policy_identities=identities,
    )


__all__ = [
    "AUTHORITY",
    "DATASET_NAME",
    "MARKET_POLICY_ID",
    "MAX_SOURCE_AGE_SECONDS",
    "MINIMUM_LEAD_SECONDS",
    "NEXT_BOUNDARY",
    "PORTFOLIO_POLICY_ID",
    "PROVIDER",
    "ROUTER_POLICY_ID",
    "SCHEMA_VERSION",
    "SHORTFALL_POLICY_ID",
    "SOURCE_BINDING_POLICY_ID",
    "STATUS",
    "VALUE_POLICY_ID",
    "CurrentShadowSportyBetFieldTrialError",
    "ResearchFixtureDecision",
    "ResearchFixtureIdentity",
    "ResearchPortfolioExclusion",
    "ResearchShadowPortfolio",
    "ResearchTotalGoalsOpportunity",
    "build_source_bound_total_goals_research_decision",
    "optimize_research_shadow_portfolio",
]
