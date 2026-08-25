"""Source-bound historical richness audit and canonical market labels.

This module is an offline evidence contract.  It separates post-match labels
from ATHENA's pre-match feature corpora and grants no prediction or betting
authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import sqlite3
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from domain.historical_asof_features import (
    EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256_BY_VERSION,
    ReadOnlyHistoricalWarehouse,
    WAREHOUSE_SCHEMA_VERSION,
)
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId


DATASET = "athena_historical_training_coverage"
SCHEMA_VERSION = 1
MARKET_LABEL_REGISTRY_VERSION = 1
LABEL_GENERATION_CONTRACT_VERSION = 1

REGULATION_FT_POLICY_ID = "CANONICAL_REGULATION_FT_BOTH_SIDES_V1"
HALF_TIME_POLICY_ID = "CANONICAL_REGULATION_HT_PAIR_V1"
CONFLICT_POLICY_ID = "LABEL_LOCAL_UNRESOLVED_REQUIRED_FIELDS_BLOCK_V1"
EXTRA_PERIOD_POLICY_ID = (
    "REGULATION_LABELS_EXCLUDE_ET_SHOOTOUT_AND_BLOCK_UNQUALIFIED_AGGREGATES_V1"
)
PREFERRED_EVENT_POLICY_ID = "WAREHOUSE_EVENTS_PREFERRED_ONLY_V1"
GOAL_PATH_POLICY_ID = "COMPLETE_PREFERRED_REGULATION_GOAL_CHRONOLOGY_V1"
SAME_TIMESTAMP_POLICY_ID = "BLOCK_MIXED_TEAM_ORDER_SENSITIVE_GOAL_TIES_V1"
LINE_SETTLEMENT_POLICY_ID = "EXPLICIT_QUARTER_LINE_SCORE_KERNEL_V1"
WIN_EITHER_HALF_POLICY_ID = "EXACT_FT_HT_HALF_DIFFERENCE_V1"
EARLY_PAYOUT_POLICY_ID = "SPORTYBET_NG_1UP_2UP_OVERLAPPING_SELECTIONS_V1"
EARLY_PAYOUT_SETTLEMENT_RECEIPT_SHA256 = (
    "921db06634ba4d210f100591c0c9acda5ae44db49452936e2229095530c01f76"
)
OPTIONAL_JOIN_POLICY_ID = "EXACT_MATCH_KEY_AND_WAREHOUSE_SHA_V1"

AUTHORITY_FLAGS = MappingProxyType({
    key: False for key in (
        "network_acquisition", "provider_acquisition", "model_training",
        "model_promotion", "probability_inference", "probability_adjustment",
        "calibration", "bookmaker_pricing", "market_activation", "router",
        "selection", "accumulator", "production_approval", "bet",
    )
})


class HistoricalTrainingCoverageError(ValueError):
    pass


class ResolutionStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    BLOCKED = "BLOCKED"


class LabelKind(str, Enum):
    DIRECT_SELECTION_LABEL = "DIRECT_SELECTION_LABEL"
    SETTLEMENT_STATE_LABEL = "SETTLEMENT_STATE_LABEL"
    LINE_INDEPENDENT_SUFFICIENT_STATISTIC = "LINE_INDEPENDENT_SUFFICIENT_STATISTIC"
    HALF_LABEL = "HALF_LABEL"
    PATH_LABEL = "PATH_LABEL"


class SettlementState(str, Enum):
    WIN = "WIN"
    HALF_WIN = "HALF_WIN"
    PUSH = "PUSH"
    HALF_LOSS = "HALF_LOSS"
    LOSS = "LOSS"


class EvidenceCapabilityId(str, Enum):
    REGULATION_FT = "REGULATION_FT"
    HALF_TIME_SCORE = "HALF_TIME_SCORE"
    PREFERRED_EVENT_EVIDENCE = "PREFERRED_EVENT_EVIDENCE"
    COMPLETE_REGULATION_GOAL_PATH = "COMPLETE_REGULATION_GOAL_PATH"
    XG_PAIR = "XG_PAIR"
    SHOTS_PAIR = "SHOTS_PAIR"
    SHOTS_ON_TARGET_PAIR = "SHOTS_ON_TARGET_PAIR"
    POSSESSION_PAIR = "POSSESSION_PAIR"
    CARD_TOTALS = "CARD_TOTALS"
    HOME_LINEUP_EVIDENCE = "HOME_LINEUP_EVIDENCE"
    AWAY_LINEUP_EVIDENCE = "AWAY_LINEUP_EVIDENCE"
    HOME_COACH_EVIDENCE = "HOME_COACH_EVIDENCE"
    AWAY_COACH_EVIDENCE = "AWAY_COACH_EVIDENCE"
    REFEREE_EVIDENCE = "REFEREE_EVIDENCE"
    ADVANCED_STATS_SOURCE_COVERAGE = "ADVANCED_STATS_SOURCE_COVERAGE"
    SOURCE_PROVENANCE = "SOURCE_PROVENANCE"
    CONFLICT_STATE = "CONFLICT_STATE"
    HISTORICAL_ASOF_TARGET_JOIN = "HISTORICAL_ASOF_TARGET_JOIN"
    TACTICAL_IDENTITY_TARGET_JOIN = "TACTICAL_IDENTITY_TARGET_JOIN"


@dataclass(frozen=True)
class MarketLabelDefinition:
    label_id: str
    market_id: MarketId | None
    family: MarketFamily | None
    kind: LabelKind
    output_type: str
    required_evidence: tuple[str, ...]
    derivation: str

    def semantic_dict(self) -> dict[str, Any]:
        return {
            "label_id": self.label_id,
            "market_id": None if self.market_id is None else self.market_id.value,
            "family": None if self.family is None else self.family.value,
            "kind": self.kind.value,
            "output_type": self.output_type,
            "required_evidence": list(self.required_evidence),
            "derivation": self.derivation,
        }


def _definition(label_id: str, market: MarketId | None, kind: LabelKind,
                output: str, required: tuple[str, ...], derivation: str) -> MarketLabelDefinition:
    return MarketLabelDefinition(
        label_id, market, None if market is None else MARKET_REGISTRY[market].family,
        kind, output, required, derivation,
    )


_FT = ("home_score_ft", "away_score_ft")
_HT = _FT + ("home_score_ht", "away_score_ht")
MARKET_LABEL_REGISTRY: tuple[MarketLabelDefinition, ...] = (
    _definition("HOME_GOALS", None, LabelKind.LINE_INDEPENDENT_SUFFICIENT_STATISTIC, "integer", _FT, "regulation home score"),
    _definition("AWAY_GOALS", None, LabelKind.LINE_INDEPENDENT_SUFFICIENT_STATISTIC, "integer", _FT, "regulation away score"),
    _definition("TOTAL_GOALS", MarketId.TOTAL_GOALS, LabelKind.LINE_INDEPENDENT_SUFFICIENT_STATISTIC, "integer", _FT, "home_goals + away_goals; no offered line implied"),
    _definition("GOAL_MARGIN", MarketId.ASIAN_HANDICAP, LabelKind.LINE_INDEPENDENT_SUFFICIENT_STATISTIC, "integer", _FT, "home_goals - away_goals; no offered line implied"),
    _definition("MATCH_RESULT", MarketId.MATCH_RESULT, LabelKind.DIRECT_SELECTION_LABEL, "HOME|DRAW|AWAY", _FT, "regulation score comparison"),
    _definition("BTTS", MarketId.BTTS, LabelKind.DIRECT_SELECTION_LABEL, "YES|NO", _FT, "both regulation scores > 0"),
    *tuple(_definition(label, MarketId.DOUBLE_CHANCE, LabelKind.DIRECT_SELECTION_LABEL, "boolean", _FT, rule) for label, rule in (
        ("DOUBLE_CHANCE_HOME_OR_DRAW", "home_goals >= away_goals"),
        ("DOUBLE_CHANCE_DRAW_OR_AWAY", "away_goals >= home_goals"),
        ("DOUBLE_CHANCE_HOME_OR_AWAY", "home_goals != away_goals"),
    )),
    _definition("HOME_WIN_TO_NIL", MarketId.HOME_WIN_TO_NIL, LabelKind.DIRECT_SELECTION_LABEL, "YES|NO", _FT, "home win and away score zero"),
    _definition("AWAY_WIN_TO_NIL", MarketId.AWAY_WIN_TO_NIL, LabelKind.DIRECT_SELECTION_LABEL, "YES|NO", _FT, "away win and home score zero"),
    *tuple(_definition(label, market, LabelKind.DIRECT_SELECTION_LABEL, "YES|NO", _FT, rule) for label, market, rule in (
        ("DRAW_OR_OVER_2_5", MarketId.DRAW_OR_OVER_2_5, "draw OR total_goals > 2.5"),
        ("HOME_OR_OVER_2_5", MarketId.HOME_OR_OVER_2_5, "home win OR total_goals > 2.5"),
        ("AWAY_OR_OVER_2_5", MarketId.AWAY_OR_OVER_2_5, "away win OR total_goals > 2.5"),
    )),
    _definition("HOME_DRAW_NO_BET", MarketId.DRAW_NO_BET, LabelKind.SETTLEMENT_STATE_LABEL, "WIN|PUSH|LOSS", _FT, "home win/draw/away win"),
    _definition("AWAY_DRAW_NO_BET", MarketId.DRAW_NO_BET, LabelKind.SETTLEMENT_STATE_LABEL, "WIN|PUSH|LOSS", _FT, "away win/draw/home win"),
    *tuple(_definition(label, market, LabelKind.HALF_LABEL, output, _HT, rule) for label, market, output, rule in (
        ("FIRST_HALF_HOME_GOALS", None, "integer", "home_score_ht"),
        ("FIRST_HALF_AWAY_GOALS", None, "integer", "away_score_ht"),
        ("SECOND_HALF_HOME_GOALS", None, "integer", "home_score_ft-home_score_ht"),
        ("SECOND_HALF_AWAY_GOALS", None, "integer", "away_score_ft-away_score_ht"),
        ("FIRST_HALF_RESULT", None, "HOME|DRAW|AWAY", "first-half score comparison"),
        ("SECOND_HALF_RESULT", None, "HOME|DRAW|AWAY", "second-half score comparison"),
        ("HOME_WIN_FIRST_HALF", MarketId.HOME_WIN_EITHER_HALF, "boolean", "home_score_ht > away_score_ht"),
        ("AWAY_WIN_FIRST_HALF", MarketId.AWAY_WIN_EITHER_HALF, "boolean", "away_score_ht > home_score_ht"),
        ("HOME_WIN_SECOND_HALF", MarketId.HOME_WIN_EITHER_HALF, "boolean", "second-half home goals > away goals"),
        ("AWAY_WIN_SECOND_HALF", MarketId.AWAY_WIN_EITHER_HALF, "boolean", "second-half away goals > home goals"),
        ("HOME_WIN_EITHER_HALF", MarketId.HOME_WIN_EITHER_HALF, "YES|NO", "home wins first OR second half"),
        ("AWAY_WIN_EITHER_HALF", MarketId.AWAY_WIN_EITHER_HALF, "YES|NO", "away wins first OR second half"),
        ("BOTH_TEAMS_WON_A_HALF", None, "boolean", "home and away each win a distinct half"),
    )),
    *tuple(_definition(f"MATCH_RESULT_{threshold}UP_{side}", MarketId[f"MATCH_RESULT_{threshold}UP"], LabelKind.PATH_LABEL, "boolean", _FT if side == "DRAW" else _FT + ("complete_goal_path",), rule)
           for threshold in (1, 2) for side, rule in (
               ("HOME", f"home reaches +{threshold}" + (" OR wins FT" if threshold == 2 else "")),
               ("DRAW", "ordinary regulation draw"),
               ("AWAY", f"away reaches +{threshold}" + (" OR wins FT" if threshold == 2 else "")),
           )),
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def calculate_market_label_registry_sha256(
    registry: Sequence[MarketLabelDefinition] = MARKET_LABEL_REGISTRY,
    version: int = MARKET_LABEL_REGISTRY_VERSION,
) -> str:
    return hashlib.sha256(_canonical_bytes({"version": version,
        "definitions": [item.semantic_dict() for item in registry]})).hexdigest()


EXPECTED_MARKET_LABEL_REGISTRY_SHA256_BY_VERSION = {
    1: "3eff35745371543bf6ff20c6c7e8550835382c04eba6583b8dbded932753e87b",
}


def canonical_market_semantics_payload(registry: Mapping[MarketId, Any] = MARKET_REGISTRY) -> dict[str, Any]:
    return {"markets": [{
        "market_id": market_id.value,
        "family": definition.family.value,
        "settlement_semantics": definition.settlement_semantics,
        "supported_outcomes": [item.value for item in definition.supported_outcomes],
        "line_required": definition.line_required,
    } for market_id, definition in sorted(registry.items(), key=lambda pair: pair[0].value)]}


def calculate_canonical_market_semantics_sha256(registry: Mapping[MarketId, Any] = MARKET_REGISTRY) -> str:
    return hashlib.sha256(_canonical_bytes(canonical_market_semantics_payload(registry))).hexdigest()


EXPECTED_CANONICAL_MARKET_SEMANTICS_SHA256 = (
    "b6a1de9415e27d9ed0e7394012435a60ca733187d41c951fd53d4a035ae84f11"
)


def generation_contract_payload(*, registry_sha256: str, market_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "market_label_registry_version": MARKET_LABEL_REGISTRY_VERSION,
        "market_label_registry_sha256": registry_sha256,
        "canonical_market_semantics_sha256": market_sha256,
        "warehouse_schema_version": WAREHOUSE_SCHEMA_VERSION,
        "warehouse_schema_sql_sha256": (
            EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256_BY_VERSION[WAREHOUSE_SCHEMA_VERSION]
        ),
        "regulation_ft_policy_id": REGULATION_FT_POLICY_ID,
        "half_time_policy_id": HALF_TIME_POLICY_ID,
        "conflict_policy_id": CONFLICT_POLICY_ID,
        "extra_period_policy_id": EXTRA_PERIOD_POLICY_ID,
        "preferred_event_policy_id": PREFERRED_EVENT_POLICY_ID,
        "complete_goal_path_policy_id": GOAL_PATH_POLICY_ID,
        "same_timestamp_policy_id": SAME_TIMESTAMP_POLICY_ID,
        "line_settlement_policy_id": LINE_SETTLEMENT_POLICY_ID,
        "win_either_half_policy_id": WIN_EITHER_HALF_POLICY_ID,
        "early_payout_policy_id": EARLY_PAYOUT_POLICY_ID,
        "early_payout_settlement_receipt_sha256": (
            EARLY_PAYOUT_SETTLEMENT_RECEIPT_SHA256
        ),
        "optional_join_policy_id": OPTIONAL_JOIN_POLICY_ID,
    }


def calculate_label_generation_contract_sha256(*, registry_sha256: str,
                                                market_sha256: str,
                                                version: int = LABEL_GENERATION_CONTRACT_VERSION) -> str:
    return hashlib.sha256(_canonical_bytes({"version": version, "semantics":
        generation_contract_payload(registry_sha256=registry_sha256,
                                    market_sha256=market_sha256)})).hexdigest()


EXPECTED_LABEL_GENERATION_CONTRACT_SHA256_BY_VERSION = {
    1: "b60bbaaff1819d9eea09fae514d19c82af99878e7f9f799bb7efedbcc3149ee5"
}


def validate_contracts(
    *,
    registry_definitions: Sequence[MarketLabelDefinition] = MARKET_LABEL_REGISTRY,
    registry_version: int = MARKET_LABEL_REGISTRY_VERSION,
    expected_registry_by_version: Mapping[int, str] = EXPECTED_MARKET_LABEL_REGISTRY_SHA256_BY_VERSION,
    market_registry: Mapping[MarketId, Any] = MARKET_REGISTRY,
    expected_market_sha256: str = EXPECTED_CANONICAL_MARKET_SEMANTICS_SHA256,
    generation_version: int = LABEL_GENERATION_CONTRACT_VERSION,
    expected_generation_by_version: Mapping[int, str] = EXPECTED_LABEL_GENERATION_CONTRACT_SHA256_BY_VERSION,
) -> tuple[str, str, str]:
    registry = calculate_market_label_registry_sha256(registry_definitions, registry_version)
    expected_registry = expected_registry_by_version.get(registry_version)
    if expected_registry is None or registry != expected_registry:
        raise HistoricalTrainingCoverageError("unreviewed market-label registry semantics")
    market = calculate_canonical_market_semantics_sha256(market_registry)
    if market != expected_market_sha256:
        raise HistoricalTrainingCoverageError("canonical market semantics drift")
    generation = calculate_label_generation_contract_sha256(
        registry_sha256=registry, market_sha256=market, version=generation_version)
    expected_generation = expected_generation_by_version.get(generation_version)
    if expected_generation is None or generation != expected_generation:
        raise HistoricalTrainingCoverageError("unreviewed label generation semantics")
    return registry, market, generation


def _quarter_line(value: Any) -> tuple[Fraction, tuple[Fraction, ...]]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise HistoricalTrainingCoverageError("line must be finite numeric")
    fraction = Fraction(str(value))
    units = fraction * 4
    if units.denominator != 1:
        raise HistoricalTrainingCoverageError("line must be an exact quarter goal")
    integer = int(units)
    if integer % 2 == 0:
        return fraction, (fraction,)
    return fraction, (Fraction(integer - 1, 4), Fraction(integer + 1, 4))


def _combine_components(values: Sequence[int]) -> SettlementState:
    total = sum(values)
    if len(values) == 1:
        return {1: SettlementState.WIN, 0: SettlementState.PUSH, -1: SettlementState.LOSS}[total]
    return {2: SettlementState.WIN, 1: SettlementState.HALF_WIN, 0: SettlementState.PUSH,
            -1: SettlementState.HALF_LOSS, -2: SettlementState.LOSS}[total]


def settle_total_goals(total_goals: int, outcome: str, line: float) -> SettlementState:
    if isinstance(total_goals, bool) or not isinstance(total_goals, int) or total_goals < 0:
        raise HistoricalTrainingCoverageError("total_goals must be a non-negative integer")
    side = outcome.strip().upper() if isinstance(outcome, str) else ""
    if side not in {"OVER", "UNDER"}:
        raise HistoricalTrainingCoverageError("totals outcome must be OVER or UNDER")
    _, components = _quarter_line(line)
    values = []
    for component in components:
        comparison = Fraction(total_goals) - component
        sign = 1 if comparison > 0 else -1 if comparison < 0 else 0
        values.append(sign if side == "OVER" else -sign)
    return _combine_components(values)


def settle_asian_handicap(goal_margin: int, side: str, line: float) -> SettlementState:
    if isinstance(goal_margin, bool) or not isinstance(goal_margin, int):
        raise HistoricalTrainingCoverageError("goal_margin must be an integer")
    selected = side.strip().upper() if isinstance(side, str) else ""
    if selected not in {"HOME", "AWAY"}:
        raise HistoricalTrainingCoverageError("handicap side must be HOME or AWAY")
    _, components = _quarter_line(line)
    base = goal_margin if selected == "HOME" else -goal_margin
    values = []
    for component in components:
        comparison = Fraction(base) + component
        values.append(1 if comparison > 0 else -1 if comparison < 0 else 0)
    return _combine_components(values)


@dataclass(frozen=True)
class Resolution:
    status: ResolutionStatus
    value: Any = None
    blocker: str | None = None
    evidence_identities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status is ResolutionStatus.AVAILABLE:
            if self.value is None or self.blocker is not None:
                raise HistoricalTrainingCoverageError("AVAILABLE requires value and no blocker")
        elif self.value is not None:
            raise HistoricalTrainingCoverageError("non-AVAILABLE resolution cannot carry value")
        if self.status is ResolutionStatus.BLOCKED and not self.blocker:
            raise HistoricalTrainingCoverageError("BLOCKED requires a blocker")
        _canonical_bytes(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        value = self.value.value if isinstance(self.value, Enum) else self.value
        return {"status": self.status.value, "value": value, "blocker": self.blocker,
                "evidence_identities": list(self.evidence_identities)}


def _result(home: int, away: int) -> str:
    return "HOME" if home > away else "AWAY" if away > home else "DRAW"


def _score_values(home: int, away: int) -> dict[str, Any]:
    result = _result(home, away)
    total = home + away
    return {
        "HOME_GOALS": home, "AWAY_GOALS": away, "TOTAL_GOALS": total,
        "GOAL_MARGIN": home - away, "MATCH_RESULT": result,
        "BTTS": "YES" if home > 0 and away > 0 else "NO",
        "DOUBLE_CHANCE_HOME_OR_DRAW": result in {"HOME", "DRAW"},
        "DOUBLE_CHANCE_DRAW_OR_AWAY": result in {"DRAW", "AWAY"},
        "DOUBLE_CHANCE_HOME_OR_AWAY": result != "DRAW",
        "HOME_WIN_TO_NIL": "YES" if home > away and away == 0 else "NO",
        "AWAY_WIN_TO_NIL": "YES" if away > home and home == 0 else "NO",
        "DRAW_OR_OVER_2_5": "YES" if result == "DRAW" or total > 2.5 else "NO",
        "HOME_OR_OVER_2_5": "YES" if result == "HOME" or total > 2.5 else "NO",
        "AWAY_OR_OVER_2_5": "YES" if result == "AWAY" or total > 2.5 else "NO",
        "HOME_DRAW_NO_BET": (SettlementState.WIN if result == "HOME" else SettlementState.PUSH if result == "DRAW" else SettlementState.LOSS),
        "AWAY_DRAW_NO_BET": (SettlementState.WIN if result == "AWAY" else SettlementState.PUSH if result == "DRAW" else SettlementState.LOSS),
        "MATCH_RESULT_1UP_DRAW": result == "DRAW", "MATCH_RESULT_2UP_DRAW": result == "DRAW",
    }


def _half_values(home_ft: int, away_ft: int, home_ht: int, away_ht: int) -> dict[str, Any]:
    home_sh, away_sh = home_ft - home_ht, away_ft - away_ht
    home_first, away_first = home_ht > away_ht, away_ht > home_ht
    home_second, away_second = home_sh > away_sh, away_sh > home_sh
    return {
        "FIRST_HALF_HOME_GOALS": home_ht, "FIRST_HALF_AWAY_GOALS": away_ht,
        "SECOND_HALF_HOME_GOALS": home_sh, "SECOND_HALF_AWAY_GOALS": away_sh,
        "FIRST_HALF_RESULT": _result(home_ht, away_ht),
        "SECOND_HALF_RESULT": _result(home_sh, away_sh),
        "HOME_WIN_FIRST_HALF": home_first, "AWAY_WIN_FIRST_HALF": away_first,
        "HOME_WIN_SECOND_HALF": home_second, "AWAY_WIN_SECOND_HALF": away_second,
        "HOME_WIN_EITHER_HALF": "YES" if home_first or home_second else "NO",
        "AWAY_WIN_EITHER_HALF": "YES" if away_first or away_second else "NO",
        "BOTH_TEAMS_WON_A_HALF": (home_first and away_second) or (away_first and home_second),
    }


def _int_score(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _row_get(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except KeyError:
        return default


def _conflicts(row: Mapping[str, Any]) -> frozenset[str]:
    raw = _row_get(row, "conflict_fields")
    return frozenset() if not raw else frozenset(str(raw).split(chr(30)))


def _row_identity(row: Mapping[str, Any], warehouse_sha: str) -> str:
    return "WAREHOUSE_MATCH:" + warehouse_sha + ":" + str(row["match_key"])


def _score_resolution_state(row: Mapping[str, Any]) -> tuple[ResolutionStatus, str | None, tuple[int, int] | None]:
    conflicts = _conflicts(row)
    if conflicts & set(_FT):
        return ResolutionStatus.BLOCKED, "UNRESOLVED_REQUIRED_FT_CONFLICT", None
    home, away = _int_score(_row_get(row, "home_score_ft")), _int_score(_row_get(row, "away_score_ft"))
    if home is None or away is None:
        return ResolutionStatus.MISSING, None, None
    return ResolutionStatus.AVAILABLE, None, (home, away)


def _half_resolution_state(row: Mapping[str, Any], ft: tuple[int, int] | None) -> tuple[ResolutionStatus, str | None, tuple[int, int] | None]:
    if _conflicts(row) & set(_HT):
        return ResolutionStatus.BLOCKED, "UNRESOLVED_REQUIRED_HALF_CONFLICT", None
    home, away = _int_score(_row_get(row, "home_score_ht")), _int_score(_row_get(row, "away_score_ht"))
    if ft is None or home is None or away is None:
        return ResolutionStatus.MISSING, None, None
    if home > ft[0] or away > ft[1]:
        return ResolutionStatus.BLOCKED, "NEGATIVE_SECOND_HALF_SCORE", None
    return ResolutionStatus.AVAILABLE, None, (home, away)


def _event_side(event: Mapping[str, Any], row: Mapping[str, Any]) -> str | None:
    team = event.get("team")
    if team == _row_get(row, "home_team"):
        side = "HOME"
    elif team == _row_get(row, "away_team"):
        side = "AWAY"
    else:
        return None
    if bool(event.get("is_own_goal")):
        side = "AWAY" if side == "HOME" else "HOME"
    return side


def _regulation_period(source: str, period: Any) -> int | None:
    if source == "statsbomb_open":
        return {"1": 1, "2": 2}.get(str(period))
    if source == "fjelstul_worldcup" and isinstance(period, str):
        normalized = period.strip().lower().replace("_", " ")
        if "first" in normalized and "half" in normalized:
            return 1
        if "second" in normalized and "half" in normalized:
            return 2
    return None


def _event_timestamp(event: Mapping[str, Any], period: int) -> tuple[int, int, int, int] | None:
    minute = event.get("minute")
    if not isinstance(minute, int) or isinstance(minute, bool) or minute < 0:
        return None
    values = []
    for name in ("stoppage_minute", "second"):
        value = event.get(name)
        if value is None:
            value = 0
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return None
        values.append(value)
    return period, minute, values[0], values[1]


def evaluate_goal_path(row: Mapping[str, Any], preferred_events: Sequence[Mapping[str, Any]],
                       has_approved_event_source: bool) -> tuple[Resolution, dict[str, bool] | None]:
    warehouse_sha = str(getattr(row, "source_warehouse_sha256", _row_get(row, "source_warehouse_sha256")))
    identity = _row_identity(row, warehouse_sha)
    ft_state, ft_blocker, ft = _score_resolution_state(row)
    if ft_state is ResolutionStatus.BLOCKED:
        return Resolution(ft_state, blocker=ft_blocker, evidence_identities=(identity,)), None
    if ft is None:
        return Resolution(ResolutionStatus.MISSING), None
    path_conflicts = sorted(field for field in _conflicts(row)
                            if "event" in field.lower() or "goal" in field.lower())
    if path_conflicts:
        return Resolution(ResolutionStatus.BLOCKED,
                          blocker="UNRESOLVED_REQUIRED_GOAL_PATH_CONFLICT",
                          evidence_identities=(identity,)), None
    goal_events = [event for event in preferred_events if str(event.get("event_type", "")).lower() == "goal"]
    if not goal_events and not has_approved_event_source:
        return Resolution(ResolutionStatus.MISSING), None
    chronology: list[tuple[tuple[int, int, int, int], str, str]] = []
    for event in goal_events:
        source = str(event.get("source_key"))
        period = _regulation_period(source, event.get("period"))
        if period is None:
            # Reviewed ET/shootout periods are excluded; unsupported semantics block.
            if source == "statsbomb_open" and str(event.get("period")) in {"3", "4", "5"}:
                continue
            return Resolution(ResolutionStatus.BLOCKED, blocker="UNSUPPORTED_GOAL_PERIOD_SEMANTICS",
                              evidence_identities=(identity,)), None
        side = _event_side(event, row)
        timestamp = _event_timestamp(event, period)
        if side is None or timestamp is None:
            return Resolution(ResolutionStatus.BLOCKED, blocker="INCOMPLETE_GOAL_ATTRIBUTION_OR_CHRONOLOGY",
                              evidence_identities=(identity,)), None
        chronology.append((timestamp, side, str(event.get("event_key"))))
    if sum(side == "HOME" for _, side, _ in chronology) != ft[0] or sum(side == "AWAY" for _, side, _ in chronology) != ft[1]:
        return Resolution(ResolutionStatus.BLOCKED, blocker="GOAL_PATH_DOES_NOT_RECONCILE_TO_REGULATION_FT",
                          evidence_identities=(identity,)), None
    chronology.sort(key=lambda item: item[0])
    # State is margin plus four irreversible lead-trigger flags.  For tied
    # mixed-team goals, consider every distinct admissible side order.  No event
    # key or source ID is allowed to break the tie.
    states = {(0, False, False, False, False)}
    for _, group_iter in itertools.groupby(chronology, key=lambda item: item[0]):
        group = list(group_iter)
        sides = tuple(item[1] for item in group)
        if len(sides) > 8:
            return Resolution(ResolutionStatus.BLOCKED,
                              blocker="UNBOUNDED_SAME_TIMESTAMP_GOAL_AMBIGUITY",
                              evidence_identities=(identity,)), None
        orders = {sides} if len(set(sides)) == 1 else set(itertools.permutations(sides))
        next_states = set()
        for state in states:
            for order in orders:
                margin, home1, away1, home2, away2 = state
                for side in order:
                    margin += 1 if side == "HOME" else -1
                    home1 |= margin >= 1; away1 |= margin <= -1
                    home2 |= margin >= 2; away2 |= margin <= -2
                next_states.add((margin, home1, away1, home2, away2))
        states = next_states
    trigger_states = {(state[1], state[2], state[3], state[4]) for state in states}
    if len(trigger_states) != 1:
        return Resolution(ResolutionStatus.BLOCKED, blocker="ORDER_SENSITIVE_SAME_TIMESTAMP_GOALS",
                          evidence_identities=(identity,)), None
    home1, away1, home2, away2 = next(iter(trigger_states))
    flags = {"1UP_HOME": home1, "1UP_AWAY": away1,
             "2UP_HOME": home2, "2UP_AWAY": away2}
    flags["2UP_HOME"] |= ft[0] > ft[1]
    flags["2UP_AWAY"] |= ft[1] > ft[0]
    event_ids = tuple("PREFERRED_EVENT:" + str(event.get("event_key")) for event in goal_events)
    return Resolution(ResolutionStatus.AVAILABLE, value="COMPLETE", evidence_identities=(identity,) + event_ids), flags


@dataclass(frozen=True, init=False)
class HistoricalTrainingCoverageRow:
    match_key: str
    match_date: str
    scope: str
    competition_key: str | None
    season: str | None
    data_quality: str
    source_warehouse_sha256: str
    market_label_registry_version: int
    market_label_registry_sha256: str
    canonical_market_semantics_sha256: str
    generation_contract_version: int
    generation_contract_sha256: str
    capabilities: tuple[tuple[str, Resolution], ...]
    labels: tuple[tuple[str, Resolution], ...]
    authority_flags: tuple[tuple[str, bool], ...]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise HistoricalTrainingCoverageError("canonical coverage rows are source-builder issued only")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": DATASET, "schema_version": SCHEMA_VERSION,
            "match_key": self.match_key, "match_date": self.match_date,
            "scope": self.scope, "competition_key": self.competition_key,
            "season": self.season, "data_quality": self.data_quality,
            "source_warehouse_sha256": self.source_warehouse_sha256,
            "market_label_registry_version": self.market_label_registry_version,
            "market_label_registry_sha256": self.market_label_registry_sha256,
            "canonical_market_semantics_sha256": self.canonical_market_semantics_sha256,
            "generation_contract_version": self.generation_contract_version,
            "generation_contract_sha256": self.generation_contract_sha256,
            "capabilities": {key: value.to_dict() for key, value in self.capabilities},
            "labels": {key: value.to_dict() for key, value in self.labels},
            "authority_flags": dict(self.authority_flags),
        }

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def _presence(count: int, identity: str) -> Resolution:
    return Resolution(ResolutionStatus.AVAILABLE, value=count,
                      evidence_identities=(identity,)) if count else Resolution(ResolutionStatus.MISSING)


def _pair_capability(row: Mapping[str, Any], fields: tuple[str, ...], identity: str,
                     *, nonnegative: bool = False, integer: bool = False,
                     period_unsafe: bool = False) -> Resolution:
    if _conflicts(row) & set(fields):
        return Resolution(ResolutionStatus.BLOCKED, blocker="UNRESOLVED_REQUIRED_FIELD_CONFLICT",
                          evidence_identities=(identity,))
    values = [_row_get(row, field) for field in fields]
    if period_unsafe and any(value is not None for value in values):
        return Resolution(ResolutionStatus.BLOCKED,
                          blocker="UNQUALIFIED_AGGREGATE_ON_EXTRA_PERIOD_MATCH",
                          evidence_identities=(identity,))
    if any(value is None for value in values):
        return Resolution(ResolutionStatus.MISSING)
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return Resolution(ResolutionStatus.BLOCKED, blocker="INVALID_NUMERIC_SOURCE_VALUE",
                              evidence_identities=(identity,))
        if nonnegative and float(value) < 0:
            return Resolution(ResolutionStatus.BLOCKED, blocker="INVALID_NUMERIC_SOURCE_VALUE",
                              evidence_identities=(identity,))
        if integer and (not isinstance(value, int) or isinstance(value, bool)):
            return Resolution(ResolutionStatus.BLOCKED, blocker="INVALID_COUNT_SOURCE_VALUE",
                              evidence_identities=(identity,))
    return Resolution(ResolutionStatus.AVAILABLE, value=list(values), evidence_identities=(identity,))


def _assemble_coverage_row(
    source: ReadOnlyHistoricalWarehouse,
    row: Mapping[str, Any],
    *,
    preferred_events: Sequence[Mapping[str, Any]],
    counts: Mapping[str, int],
    asof_join_sha256: str | None = None,
    tactical_join_sha256: str | None = None,
) -> HistoricalTrainingCoverageRow:
    """Assemble only after this module has replayed exact source evidence."""
    source._require_bound_row(row)  # closure-owned issuance proof from Phase 2
    if getattr(row, "source_warehouse_sha256", None) != source.sha256:
        raise HistoricalTrainingCoverageError("warehouse row ancestry mismatch")
    registry_sha, market_sha, generation_sha = validate_contracts()
    identity = _row_identity(row, source.sha256)
    unresolved = [item[0] for item in source.connection.execute(
        "SELECT DISTINCT field_name FROM warehouse_conflicts "
        "WHERE match_key=? AND resolved=0 ORDER BY field_name", (row["match_key"],))]
    row_values = dict(row.row_items)
    row_values["conflict_fields"] = chr(30).join(unresolved) if unresolved else None
    row_values["source_warehouse_sha256"] = source.sha256
    row = MappingProxyType(row_values)
    ft_status, ft_blocker, ft = _score_resolution_state(row)
    ht_status, ht_blocker, ht = _half_resolution_state(row, ft)
    approved_event_source = bool(counts.get("approved_event_sources"))
    path_resolution, path_flags = evaluate_goal_path(row, preferred_events, approved_event_source)
    extra_period_evidence = any(_row_get(row, field) is not None for field in (
        "home_score_et", "away_score_et", "home_score_pen", "away_score_pen")) or bool(
            _row_get(row, "has_reviewed_extra_time_event")) or bool(
            _row_get(row, "has_penalty_shootout_evidence"))

    capabilities: dict[str, Resolution] = {
        EvidenceCapabilityId.REGULATION_FT.value: Resolution(ft_status, value=list(ft) if ft else None,
            blocker=ft_blocker, evidence_identities=(identity,) if ft_status is not ResolutionStatus.MISSING else ()),
        EvidenceCapabilityId.HALF_TIME_SCORE.value: Resolution(ht_status, value=list(ht) if ht else None,
            blocker=ht_blocker, evidence_identities=(identity,) if ht_status is not ResolutionStatus.MISSING else ()),
        EvidenceCapabilityId.PREFERRED_EVENT_EVIDENCE.value: _presence(len(preferred_events), identity),
        EvidenceCapabilityId.COMPLETE_REGULATION_GOAL_PATH.value: path_resolution,
        EvidenceCapabilityId.XG_PAIR.value: _pair_capability(row, ("home_xg", "away_xg"), identity, nonnegative=True, period_unsafe=extra_period_evidence),
        EvidenceCapabilityId.SHOTS_PAIR.value: _pair_capability(row, ("home_shots", "away_shots"), identity, nonnegative=True, integer=True, period_unsafe=extra_period_evidence),
        EvidenceCapabilityId.SHOTS_ON_TARGET_PAIR.value: _pair_capability(row, ("home_shots_on_target", "away_shots_on_target"), identity, nonnegative=True, integer=True, period_unsafe=extra_period_evidence),
        EvidenceCapabilityId.POSSESSION_PAIR.value: _pair_capability(row, ("home_possession", "away_possession"), identity, period_unsafe=extra_period_evidence),
        EvidenceCapabilityId.CARD_TOTALS.value: _pair_capability(row, ("home_yellows", "away_yellows", "home_reds", "away_reds"), identity, nonnegative=True, integer=True, period_unsafe=extra_period_evidence),
        EvidenceCapabilityId.HOME_LINEUP_EVIDENCE.value: _presence(counts.get("home_lineups", 0), identity),
        EvidenceCapabilityId.AWAY_LINEUP_EVIDENCE.value: _presence(counts.get("away_lineups", 0), identity),
        EvidenceCapabilityId.HOME_COACH_EVIDENCE.value: _presence(counts.get("home_coaches", 0), identity),
        EvidenceCapabilityId.AWAY_COACH_EVIDENCE.value: _presence(counts.get("away_coaches", 0), identity),
        EvidenceCapabilityId.REFEREE_EVIDENCE.value: _presence(counts.get("referees", 0), identity),
        EvidenceCapabilityId.ADVANCED_STATS_SOURCE_COVERAGE.value: _presence(counts.get("advanced_sources", 0), identity),
        EvidenceCapabilityId.SOURCE_PROVENANCE.value: _presence(counts.get("provenance", 0), identity),
        EvidenceCapabilityId.CONFLICT_STATE.value: Resolution(ResolutionStatus.AVAILABLE,
            value={"unresolved_count": len(_conflicts(row))}, evidence_identities=(identity,)),
        EvidenceCapabilityId.HISTORICAL_ASOF_TARGET_JOIN.value: (Resolution(ResolutionStatus.AVAILABLE, value=asof_join_sha256,
            evidence_identities=("ASOF_CORPUS:" + asof_join_sha256,)) if asof_join_sha256 else Resolution(ResolutionStatus.MISSING)),
        EvidenceCapabilityId.TACTICAL_IDENTITY_TARGET_JOIN.value: (Resolution(ResolutionStatus.AVAILABLE, value=tactical_join_sha256,
            evidence_identities=("TACTICAL_CORPUS:" + tactical_join_sha256,)) if tactical_join_sha256 else Resolution(ResolutionStatus.MISSING)),
    }
    labels = {definition.label_id: Resolution(ResolutionStatus.MISSING) for definition in MARKET_LABEL_REGISTRY}
    if ft_status is ResolutionStatus.BLOCKED:
        for definition in MARKET_LABEL_REGISTRY:
            labels[definition.label_id] = Resolution(ResolutionStatus.BLOCKED, blocker=ft_blocker,
                                                     evidence_identities=(identity,))
    elif ft is not None:
        for key, value in _score_values(*ft).items():
            labels[key] = Resolution(ResolutionStatus.AVAILABLE, value=value,
                                     evidence_identities=(identity,))
        if ht_status is ResolutionStatus.AVAILABLE and ht is not None:
            for key, value in _half_values(*ft, *ht).items():
                labels[key] = Resolution(ResolutionStatus.AVAILABLE, value=value,
                                         evidence_identities=(identity,))
        elif ht_status is ResolutionStatus.BLOCKED:
            for definition in MARKET_LABEL_REGISTRY:
                if definition.kind is LabelKind.HALF_LABEL:
                    labels[definition.label_id] = Resolution(ResolutionStatus.BLOCKED, blocker=ht_blocker,
                                                             evidence_identities=(identity,))
        for threshold in (1, 2):
            for side in ("HOME", "AWAY"):
                key = f"MATCH_RESULT_{threshold}UP_{side}"
                if path_flags is not None:
                    labels[key] = Resolution(ResolutionStatus.AVAILABLE,
                        value=path_flags[f"{threshold}UP_{side}"],
                        evidence_identities=path_resolution.evidence_identities)
                elif path_resolution.status is ResolutionStatus.BLOCKED:
                    labels[key] = Resolution(ResolutionStatus.BLOCKED,
                        blocker=path_resolution.blocker,
                        evidence_identities=path_resolution.evidence_identities)

    # Construction occurs only at the end of this source-replaying public
    # builder.  There is no token-bearing or caller-parameterized issuance
    # helper that can stamp arbitrary values with the warehouse ancestry.
    result = object.__new__(HistoricalTrainingCoverageRow)
    values = {
        "match_key": str(row["match_key"]), "match_date": str(row["match_date"]),
        "scope": str(row["scope"]), "competition_key": row["competition_key"],
        "season": row["season"], "data_quality": str(row["data_quality"]),
        "source_warehouse_sha256": source.sha256,
        "market_label_registry_version": MARKET_LABEL_REGISTRY_VERSION,
        "market_label_registry_sha256": registry_sha,
        "canonical_market_semantics_sha256": market_sha,
        "generation_contract_version": LABEL_GENERATION_CONTRACT_VERSION,
        "generation_contract_sha256": generation_sha,
        "capabilities": tuple(sorted(capabilities.items())),
        "labels": tuple(sorted(labels.items())),
        "authority_flags": tuple(AUTHORITY_FLAGS.items()),
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    return result


def preferred_events_for_match(source: ReadOnlyHistoricalWarehouse, match_key: str) -> tuple[Mapping[str, Any], ...]:
    return tuple(MappingProxyType(dict(row)) for row in source.connection.execute(
        "SELECT * FROM warehouse_events_preferred WHERE match_key=? ORDER BY event_type,source_key,minute,stoppage_minute,second",
        (match_key,)))


def evidence_counts_for_match(source: ReadOnlyHistoricalWarehouse, row: Mapping[str, Any]) -> Mapping[str, int]:
    key, home, away = row["match_key"], row["home_team"], row["away_team"]
    query = """
    SELECT
      (SELECT count(*) FROM warehouse_lineups WHERE match_key=? AND team=?) home_lineups,
      (SELECT count(*) FROM warehouse_lineups WHERE match_key=? AND team=?) away_lineups,
      (SELECT count(*) FROM warehouse_coaches WHERE match_key=? AND team=?) home_coaches,
      (SELECT count(*) FROM warehouse_coaches WHERE match_key=? AND team=?) away_coaches,
      (SELECT count(*) FROM warehouse_officials WHERE match_key=? AND role='referee') referees,
      (SELECT count(*) FROM warehouse_match_sources WHERE match_key=? AND has_advanced_stats=1) advanced_sources,
      (SELECT count(*) FROM warehouse_field_provenance WHERE match_key=?) provenance,
      (SELECT count(*) FROM warehouse_match_sources WHERE match_key=? AND has_events=1 AND source_key IN ('statsbomb_open','fjelstul_worldcup')) approved_event_sources
    """
    values = (key, home, key, away, key, home, key, away, key, key, key, key)
    result = source.connection.execute(query, values).fetchone()
    return MappingProxyType(dict(result))


def build_coverage_row_from_bound_source(
    source: ReadOnlyHistoricalWarehouse,
    row: Mapping[str, Any],
    *,
    asof_corpus: "ReadOnlyOptionalJoinCorpus | None" = None,
    tactical_corpus: "ReadOnlyOptionalJoinCorpus | None" = None,
) -> HistoricalTrainingCoverageRow:
    """Replay one source-issued target; callers cannot inject evidence payloads."""
    source._require_bound_row(row)
    return _assemble_coverage_row(
        source,
        row,
        preferred_events=preferred_events_for_match(source, str(row["match_key"])),
        counts=evidence_counts_for_match(source, row),
        asof_join_sha256=(None if asof_corpus is None
                          else asof_corpus.join_identity(str(row["match_key"]))),
        tactical_join_sha256=(None if tactical_corpus is None
                              else tactical_corpus.join_identity(str(row["match_key"]))),
    )


def build_historical_training_coverage_row(warehouse_path: Path, match_key: str) -> HistoricalTrainingCoverageRow:
    with ReadOnlyHistoricalWarehouse(Path(warehouse_path)) as source:
        row = source.target_match(match_key)
        result = build_coverage_row_from_bound_source(source, row)
        source.assert_unchanged()
        return result


class ReadOnlyOptionalJoinCorpus:
    """Exact-byte, query-only validator for a Phase 2 or Phase 3 corpus."""

    _KINDS = {
        "ASOF": ("athena_historical_asof_features", "historical_asof_snapshots"),
        "TACTICAL": ("athena_tactical_identity", "tactical_identity_snapshots"),
    }

    def __init__(self, path: Path, kind: str, expected_warehouse_sha256: str) -> None:
        from domain.historical_asof_features import file_sha256
        self.kind = kind.upper()
        if self.kind not in self._KINDS:
            raise HistoricalTrainingCoverageError("unsupported optional corpus kind")
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise HistoricalTrainingCoverageError("optional corpus does not exist")
        self._assert_no_companions()
        self._before = self.path.stat()
        self.sha256 = file_sha256(self.path)
        self._assert_no_companions()
        self.connection = sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA query_only=ON")
        try:
            expected_dataset, self.table = self._KINDS[self.kind]
            objects = {row[0] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"corpus_meta", self.table}.issubset(objects):
                raise HistoricalTrainingCoverageError("optional corpus schema mismatch")
            raw = dict(self.connection.execute("SELECT key,value FROM corpus_meta"))
            self.meta = MappingProxyType({key: json.loads(value) for key, value in raw.items()})
            if self.meta.get("dataset") != expected_dataset:
                raise HistoricalTrainingCoverageError("optional corpus dataset mismatch")
            if self.meta.get("source_warehouse_sha256") != expected_warehouse_sha256:
                raise HistoricalTrainingCoverageError("optional corpus warehouse ancestry mismatch")
            self._assert_no_companions()
        except Exception:
            self.close()
            raise

    def _assert_no_companions(self) -> None:
        for suffix in ("-wal", "-journal"):
            companion = Path(str(self.path) + suffix)
            if companion.exists() and companion.stat().st_size:
                raise HistoricalTrainingCoverageError("unsafe active optional-corpus companion")

    def join_identity(self, match_key: str) -> str | None:
        row = self.connection.execute(
            f"SELECT canonical_sha256,payload_json FROM {self.table} WHERE match_key=?",
            (match_key,),).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise HistoricalTrainingCoverageError("invalid optional corpus payload") from exc
        canonical = _canonical_bytes(payload)
        if canonical != row["payload_json"].encode("utf-8"):
            raise HistoricalTrainingCoverageError("optional corpus payload is not canonical")
        actual = hashlib.sha256(canonical).hexdigest()
        if actual != row["canonical_sha256"]:
            raise HistoricalTrainingCoverageError("optional corpus row identity mismatch")
        if payload.get("source_warehouse_sha256") != self.meta["source_warehouse_sha256"]:
            raise HistoricalTrainingCoverageError("optional corpus row ancestry mismatch")
        return actual

    def assert_unchanged(self) -> None:
        from domain.historical_asof_features import file_sha256
        self._assert_no_companions()
        after = self.path.stat()
        if (after.st_size, after.st_mtime_ns) != (self._before.st_size, self._before.st_mtime_ns):
            raise HistoricalTrainingCoverageError("optional corpus changed during audit")
        if file_sha256(self.path) != self.sha256:
            raise HistoricalTrainingCoverageError("optional corpus bytes changed during audit")
        self._assert_no_companions()

    def close(self) -> None:
        connection = getattr(self, "connection", None)
        if connection is not None:
            connection.close()
            self.connection = None

    def __enter__(self) -> "ReadOnlyOptionalJoinCorpus":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


__all__ = [
    "AUTHORITY_FLAGS", "DATASET", "EvidenceCapabilityId", "HistoricalTrainingCoverageError",
    "HistoricalTrainingCoverageRow", "LABEL_GENERATION_CONTRACT_VERSION", "LabelKind",
    "MARKET_LABEL_REGISTRY", "MARKET_LABEL_REGISTRY_VERSION", "Resolution", "ResolutionStatus",
    "ReadOnlyOptionalJoinCorpus",
    "SCHEMA_VERSION", "SettlementState", "build_historical_training_coverage_row",
    "build_coverage_row_from_bound_source", "calculate_canonical_market_semantics_sha256",
    "calculate_label_generation_contract_sha256", "calculate_market_label_registry_sha256",
    "settle_asian_handicap", "settle_total_goals", "validate_contracts",
]
