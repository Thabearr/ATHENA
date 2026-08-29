"""Shadow Price-all core constants and enums (PR D)."""
from __future__ import annotations

from enum import Enum
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

from domain.markets import MarketId, OutcomeId

SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-shadow-all-market-price-all-router-v1"
DEVIG_POLICY_ID = "PROPORTIONAL_ONLY_MUTUALLY_EXCLUSIVE_EXHAUSTIVE_PARTITIONS_V1"
SETTLEMENT_RETURN_POLICY_ID = "UNIT_STAKE_FULL_PUSH_SPLIT_SETTLEMENT_RETURNS_V1"
ROUTER_POLICY_ID = "SHADOW_CONSERVATIVE_FROZEN_THRESHOLDS_V1"
QUOTE_POLICY_ID = "EXACT_SOURCE_BOUND_SPORTYBET_SELECTION_IDENTITY_V1"
SOURCE_BOUND_ISSUANCE_TOKEN = "ATHENA_SHADOW_QUOTE_SOURCE_BOUND_V1"
MAX_QUOTE_AGE_SECONDS = 900
MINIMUM_EVENT_PROBABILITY = 0.55
MINIMUM_NET_EXPECTED_VALUE = 0.0
MINIMUM_ROBUST_NET_EXPECTED_VALUE = 0.0
MINIMUM_ROBUST_EDGE = 0.0

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
OVERLAPPING_MARKETS = frozenset({MarketId.DOUBLE_CHANCE, MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP})
PUSH_SPLIT_MARKETS = frozenset({MarketId.DRAW_NO_BET, MarketId.ASIAN_HANDICAP})


class ShadowPriceError(ValueError):
    """Raised when Shadow Price-all / Router input fails closed."""


class ShadowPriceDisposition(str, Enum):
    PRICED = "PRICED"
    UNPRICED_NO_EXACT_QUOTE = "UNPRICED_NO_EXACT_QUOTE"
    UNPRICED_AMBIGUOUS_QUOTE = "UNPRICED_AMBIGUOUS_QUOTE"
    UNPRICED_STALE_QUOTE = "UNPRICED_STALE_QUOTE"
    UNPRICED_FUTURE_QUOTE = "UNPRICED_FUTURE_QUOTE"
    UNPRICED_PROVIDER_BLOCKED = "UNPRICED_PROVIDER_BLOCKED"
    UNPRICED_UPSTREAM_BLOCKED = "UNPRICED_UPSTREAM_BLOCKED"
    UNPRICED_INVALID_ODDS = "UNPRICED_INVALID_ODDS"
    UNPRICED_SETTLEMENT_INCOMPLETE = "UNPRICED_SETTLEMENT_INCOMPLETE"
    UNPRICED_SOURCE_MISMATCH = "UNPRICED_SOURCE_MISMATCH"
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
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_sha(value: Optional[str], label: str) -> Optional[str]:
    if value is None:
        return None
    if type(value) is not str or not _SHA_RE.fullmatch(value):
        raise ShadowPriceError(f"{label} must be exact 64-char lowercase hex SHA-256")
    return value


def _finite(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ShadowPriceError(f"{label} must be finite numeric")
    return float(value)


def _probability(value: float, label: str) -> float:
    p = _finite(value, label)
    if p < 0.0 or p > 1.0:
        raise ShadowPriceError(f"{label} must be in [0, 1]")
    return p


def _odds(value: float, label: str = "decimal_odds") -> float:
    o = _finite(value, label)
    if o <= 1.0:
        raise ShadowPriceError(f"{label} must be > 1")
    return o


def settlement_unit_return(state: str, decimal_odds: float) -> float:
    if state == "WIN":
        return decimal_odds - 1.0
    if state == "HALF_WIN":
        return (decimal_odds - 1.0) / 2.0
    if state == "PUSH":
        return 0.0
    if state == "HALF_LOSS":
        return -0.5
    if state == "LOSS":
        return -1.0
    raise ShadowPriceError(f"unknown settlement state {state}")
