"""Core policy/constants for research-only Shadow Price-all + Router (PR D)."""
from __future__ import annotations

from enum import Enum
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Optional

from domain.markets import MarketId, OutcomeId

SCHEMA_VERSION = 2
DATASET_NAME = "athena-current-shadow-all-market-price-all-router-v2"
DEVIG_POLICY_ID = "PROPORTIONAL_ONLY_MUTUALLY_EXCLUSIVE_EXHAUSTIVE_PARTITIONS_V1"
SETTLEMENT_RETURN_POLICY_ID = "UNIT_STAKE_FULL_PUSH_SPLIT_SETTLEMENT_RETURNS_V1"
VALUE_FIRST_ROUTER_POLICY_ID = "SHADOW_CONSERVATIVE_FROZEN_THRESHOLDS_V1"
ROUTER_POLICY_ID = "SHADOW_SOURCE_ALIGNED_SETTLEMENT_AWARE_ROUTER_V3"
QUOTE_POLICY_ID = "PRB_EXACT_SEMANTICS_OVER_REPLAYED_CURRENT_PROVIDER_EVENT_V2"
SOURCE_CONTEXT_POLICY_ID = "PRC_CURRENT_SCAN_PLUS_PR253_FIXTURE_BRIDGE_PLUS_PRB_REPLAY_V1"
MAX_QUOTE_AGE_SECONDS = 900
MINIMUM_LEAD_SECONDS = 120
MINIMUM_EVENT_PROBABILITY = 0.55
MINIMUM_PREDICTION_CONFIDENCE = 0.55
MINIMUM_DECIMAL_ODDS = 1.09
MINIMUM_NET_EXPECTED_VALUE = 0.0
MINIMUM_ROBUST_NET_EXPECTED_VALUE = 0.0
MINIMUM_ROBUST_EDGE = 0.0
# Project source contract: stable recommendations begin at Over 1.5; Over 0.5
# may be priced/audited when the provider exposes it, but it is never selection
# authority merely because its raw probability is extreme.
MINIMUM_SELECTABLE_OVER_TOTAL_GOALS_LINE = 1.5

SCALAR_PREDICTION_CONFIDENCE_METHOD = "MODEL_EVENT_PROBABILITY"
DNB_PREDICTION_CONFIDENCE_METHOD = "SETTLEMENT_SURVIVAL_WIN_PLUS_PUSH"
AH_PREDICTION_CONFIDENCE_METHOD = (
    "SETTLEMENT_SURVIVAL_WIN_PLUS_HALF_WIN_PLUS_PUSH"
)
DNB_SETTLEMENT_STATES = ("WIN", "PUSH", "LOSS")
AH_SETTLEMENT_STATES = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)

AUTHORITY_FLAGS = MappingProxyType({
    "research_current_quote_consumption": True,
    "research_shadow_price_all": True,
    "research_shadow_market_routing": True,
    "research_counterfactual_recording": True,
    "production_model": False,
    "production_probability": False,
    "phase6": False,
    "production_price_all": False,
    "production_market_router": False,
    "production_portfolio": False,
    "production_selection": False,
    "accumulator": False,
    "slip_construction": False,
    "share_code_generation": False,
    "sportybet_execution": False,
    "login": False,
    "cookies": False,
    "wallet": False,
    "staking": False,
    "bet": False,
    "wager_placed": False,
})

ORDINARY_PARTITIONS: Mapping[MarketId, tuple[OutcomeId, ...]] = MappingProxyType({
    MarketId.MATCH_RESULT: (OutcomeId.HOME, OutcomeId.DRAW, OutcomeId.AWAY),
    MarketId.BTTS: (OutcomeId.YES, OutcomeId.NO),
    MarketId.TOTAL_GOALS: (OutcomeId.OVER, OutcomeId.UNDER),
    MarketId.DRAW_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
    MarketId.HOME_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
    MarketId.AWAY_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
    MarketId.HOME_WIN_TO_NIL: (OutcomeId.YES, OutcomeId.NO),
    MarketId.AWAY_WIN_TO_NIL: (OutcomeId.YES, OutcomeId.NO),
    MarketId.HOME_WIN_EITHER_HALF: (OutcomeId.YES, OutcomeId.NO),
    MarketId.AWAY_WIN_EITHER_HALF: (OutcomeId.YES, OutcomeId.NO),
})
OVERLAPPING_MARKETS = frozenset({
    MarketId.DOUBLE_CHANCE,
    MarketId.MATCH_RESULT_1UP,
    MarketId.MATCH_RESULT_2UP,
})
PUSH_SPLIT_MARKETS = frozenset({MarketId.DRAW_NO_BET, MarketId.ASIAN_HANDICAP})


class ShadowPriceError(ValueError):
    """Raised when PR-D source/value/routing inputs fail closed."""


class ShadowPriceDisposition(str, Enum):
    PRICED = "PRICED"
    UNPRICED_NO_EXACT_QUOTE = "UNPRICED_NO_EXACT_QUOTE"
    UNPRICED_AMBIGUOUS_QUOTE = "UNPRICED_AMBIGUOUS_QUOTE"
    UNPRICED_STALE_QUOTE = "UNPRICED_STALE_QUOTE"
    UNPRICED_FUTURE_QUOTE = "UNPRICED_FUTURE_QUOTE"
    UNPRICED_TOO_CLOSE_TO_KICKOFF = "UNPRICED_TOO_CLOSE_TO_KICKOFF"
    UNPRICED_PROVIDER_BLOCKED = "UNPRICED_PROVIDER_BLOCKED"
    UNPRICED_UPSTREAM_BLOCKED = "UNPRICED_UPSTREAM_BLOCKED"
    UNPRICED_SETTLEMENT_INCOMPLETE = "UNPRICED_SETTLEMENT_INCOMPLETE"
    AUDIT_ONLY_UPSTREAM_BLOCKED = "AUDIT_ONLY_UPSTREAM_BLOCKED"


class ShadowDevigStatus(str, Enum):
    PROPORTIONAL_COMPLETE_PARTITION = "PROPORTIONAL_COMPLETE_PARTITION"
    NOT_IDENTIFIABLE_OVERLAPPING_EVENTS = "NOT_IDENTIFIABLE_OVERLAPPING_EVENTS"
    NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT = "NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT"
    INCOMPLETE_PARTITION = "INCOMPLETE_PARTITION"
    CROSS_SNAPSHOT = "CROSS_SNAPSHOT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ShadowRouterDecisionStatus(str, Enum):
    SELECTED = "SELECTED"
    NO_BET = "NO_BET"


class ShadowOpportunityEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    REJECTED = "REJECTED"


class ShadowModelAgreementStatus(str, Enum):
    SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE = "SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE"


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ShadowPriceError("canonical serialization failed") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_sha(value: Optional[str], label: str) -> Optional[str]:
    if value is None:
        return None
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise ShadowPriceError(f"{label} must be exact lowercase SHA-256")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ShadowPriceError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ShadowPriceError(f"{label} must be finite numeric")
    return result


def _probability(value: Any, label: str) -> float:
    result = _finite(value, label)
    if not 0.0 <= result <= 1.0:
        raise ShadowPriceError(f"{label} must be in [0, 1]")
    return result


def _odds(value: Any, label: str = "decimal_odds") -> float:
    result = _finite(value, label)
    if result <= 1.0:
        raise ShadowPriceError(f"{label} must be > 1")
    return result


def settlement_unit_return(state: str, decimal_odds: float) -> float:
    odds = _odds(decimal_odds)
    if state == "WIN":
        return odds - 1.0
    if state == "HALF_WIN":
        return (odds - 1.0) / 2.0
    if state == "PUSH":
        return 0.0
    if state == "HALF_LOSS":
        return -0.5
    if state == "LOSS":
        return -1.0
    raise ShadowPriceError(f"unknown settlement state {state!r}")