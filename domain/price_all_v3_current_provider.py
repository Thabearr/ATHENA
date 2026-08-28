"""Price-all v3 for exact PR253 current SportyBet mapped quotes.

This additive boundary reconstructs the complete PR253 source before computing
settlement-aware value.  It never routes, selects, builds a slip, executes a
provider request, stakes, or places a wager.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal
import enum
import hashlib
import json
import math
import types
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from domain import current_direct_provider_live_quote_mapping_consumption as current
from domain import price_all_v2_direct_provider as v2
from domain._price_all_contracts import (
    CalibratedValueCandidate,
    DEVIG_POLICY_ID,
    DevigStatus,
    SETTLEMENT_RETURN_POLICY_ID,
)
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId
from domain.sportybet_reviewed_canonical_market_mapping import (
    SettlementEquivalenceAuthority,
)


SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-price-all-v3-current-provider-value-evaluation-v1"
STATUS_AS_OF = "PRICE_ALL_V3_CURRENT_PROVIDER_AS_OF_VALUE_VERIFIED"
STATUS_LIVE = "PRICE_ALL_V3_CURRENT_PROVIDER_LIVE_VALUE_VERIFIED"
AS_OF_REPLAY = current.AS_OF_REPLAY
LIVE_CURRENT = current.LIVE_CURRENT
PR253_CONTRACT_SHA256 = current.EXPECTED_CONTRACT_SHA256
PRICE_ALL_V2_CONTRACT_SHA256 = v2.EXPECTED_CONTRACT_SHA256
DEFAULT_MAX_QUOTE_AGE_SECONDS = current.MAX_SOURCE_AGE_SECONDS
DEFAULT_MINIMUM_LEAD_SECONDS = current.MINIMUM_LEAD_SECONDS
SOURCE_REPLAY_POLICY_ID = "EXACT_PR253_RECONSTRUCTION_BEFORE_VALUE_V1"
FRESHNESS_POLICY_ID = (
    "EVALUATION_TIME_RECHECK_STRICTEST_UPSTREAM_AGE_AND_KICKOFF_LEAD_V1"
)
PARTITION_POLICY_ID = (
    "EXACT_PROVIDER_MARKET_SPECIFIER_AND_FULL_CURRENT_ANCESTRY_PARTITION_V1"
)
NO_ROUTER_POLICY_ID = "PRICE_ALL_V3_NO_RANK_ROUTE_SELECT_SLIP_EXECUTION_OR_BET_V1"
NEXT_BOUNDARY = "MARKET_ROUTER_V3_CURRENT_PROVIDER_VALUE_CONSUMPTION_REQUIRED"
EXPECTED_CONTRACT_SHA256 = "30481bc9ebf442f0e664bcd14d2c6cd18026a42a35083d143db6366837b3d425"

_AUTHORITY = types.MappingProxyType(
    {
        "current_provider_quote_consumption": True,
        "settlement_aware_value_computation": True,
        "football_probability_generation": False,
        "model_promotion": False,
        "market_router": False,
        "portfolio_optimization": False,
        "final_selection": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
    }
)

_EARLY_OR_WEH = frozenset(
    {
        MarketId.HOME_WIN_EITHER_HALF,
        MarketId.AWAY_WIN_EITHER_HALF,
        MarketId.MATCH_RESULT_1UP,
        MarketId.MATCH_RESULT_2UP,
    }
)

_ORDINARY_PARTITIONS: Mapping[MarketId, tuple[OutcomeId, ...]] = (
    types.MappingProxyType(
        {
            MarketId.MATCH_RESULT: (OutcomeId.HOME, OutcomeId.DRAW, OutcomeId.AWAY),
            MarketId.BTTS: (OutcomeId.YES, OutcomeId.NO),
            MarketId.TOTAL_GOALS: (OutcomeId.OVER, OutcomeId.UNDER),
            MarketId.DRAW_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
            MarketId.HOME_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
            MarketId.AWAY_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
            MarketId.HOME_WIN_TO_NIL: (OutcomeId.YES, OutcomeId.NO),
            MarketId.AWAY_WIN_TO_NIL: (OutcomeId.YES, OutcomeId.NO),
        }
    )
)

_PARTITION_ANCESTRY_FIELDS = (
    "fixture_id",
    "event_id",
    "provider_market_id",
    "provider_specifier",
    "canonical_market_id",
    "canonical_line",
    "current_inventory_sha256",
    "source_manifest_sha256",
    "source_raw_sha256",
    "current_mapping_rebind_sha256",
    "current_mapping_contract_sha256",
    "source_current_reconciliation_sha256",
    "source_legacy_mapping_sha256",
)


class PriceAllV3CurrentProviderError(ValueError):
    """Raised when current-provider Price-all v3 fails closed."""


class CurrentProviderPriceDisposition(str, enum.Enum):
    PRICED = "PRICED"
    UNPRICED_SOURCE_MISMATCH = "UNPRICED_SOURCE_MISMATCH"
    UNPRICED_NO_EXACT_QUOTE = "UNPRICED_NO_EXACT_QUOTE"
    UNPRICED_STALE_QUOTE = "UNPRICED_STALE_QUOTE"
    UNPRICED_AMBIGUOUS_QUOTE = "UNPRICED_AMBIGUOUS_QUOTE"
    UNPRICED_NEAR_KICKOFF = "UNPRICED_NEAR_KICKOFF"
    UNPRICED_CURRENTLY_UNAVAILABLE = "UNPRICED_CURRENTLY_UNAVAILABLE"
    UNPRICED_SETTLEMENT_EQUIVALENCE_UNPROVEN = (
        "UNPRICED_SETTLEMENT_EQUIVALENCE_UNPROVEN"
    )
    BLOCKED_UPSTREAM_PROBABILITY_UNAVAILABLE = (
        "BLOCKED_UPSTREAM_PROBABILITY_UNAVAILABLE"
    )
    BLOCKED_SETTLEMENT_DISTRIBUTION_INCOMPLETE = (
        "BLOCKED_SETTLEMENT_DISTRIBUTION_INCOMPLETE"
    )


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise PriceAllV3CurrentProviderError(
            "canonical JSON serialization failed"
        ) from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise PriceAllV3CurrentProviderError(f"{label} must be timezone-aware")
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PriceAllV3CurrentProviderError(f"{label} is invalid") from exc


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "dataset_name": DATASET_NAME,
        "pr253_dataset_name": current.DATASET_NAME,
        "pr253_contract_sha256": PR253_CONTRACT_SHA256,
        "price_all_v2_contract_sha256": PRICE_ALL_V2_CONTRACT_SHA256,
        "source_replay_policy_id": SOURCE_REPLAY_POLICY_ID,
        "freshness_policy_id": FRESHNESS_POLICY_ID,
        "proof_modes": [AS_OF_REPLAY, LIVE_CURRENT],
        "max_quote_age_seconds": DEFAULT_MAX_QUOTE_AGE_SECONDS,
        "minimum_lead_seconds": DEFAULT_MINIMUM_LEAD_SECONDS,
        "devig_policy_id": DEVIG_POLICY_ID,
        "settlement_return_policy_id": SETTLEMENT_RETURN_POLICY_ID,
        "partition_policy_id": PARTITION_POLICY_ID,
        "partition_ancestry_fields": list(_PARTITION_ANCESTRY_FIELDS),
        "result_dispositions": [item.value for item in CurrentProviderPriceDisposition],
        "pr253_audit_disposition_projection": {
            "SETTLEMENT_EQUIVALENCE_UNPROVEN": "UNPRICED_SETTLEMENT_EQUIVALENCE_UNPROVEN",
            "CURRENTLY_UNAVAILABLE": "UNPRICED_CURRENTLY_UNAVAILABLE",
        },
        "provider_quote_timestamp": None,
        "provider_snapshot_id": None,
        "no_router_policy_id": NO_ROUTER_POLICY_ID,
        "authority": dict(_AUTHORITY),
        "next_boundary": NEXT_BOUNDARY,
    }


def calculate_price_all_v3_contract_sha256() -> str:
    return hashlib.sha256(_canonical_bytes(_contract_payload())).hexdigest()


def validate_price_all_v3_contract() -> Mapping[str, str]:
    try:
        source = current.validate_current_live_quote_mapping_contract()
        frozen_v2 = v2.validate_price_all_v2_contract()
    except (current.CurrentDirectProviderLiveQuoteMappingConsumptionError, v2.PriceAllV2DirectProviderError) as exc:
        raise PriceAllV3CurrentProviderError(
            "Price-all v3 dependency validation failed"
        ) from exc
    if source["current_live_quote_mapping_contract_sha256"] != PR253_CONTRACT_SHA256:
        raise PriceAllV3CurrentProviderError("PR253 contract identity drifted")
    if frozen_v2["price_all_v2_contract_sha256"] != PRICE_ALL_V2_CONTRACT_SHA256:
        raise PriceAllV3CurrentProviderError("frozen Price-all v2 identity drifted")
    actual = calculate_price_all_v3_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise PriceAllV3CurrentProviderError("Price-all v3 contract drifted")
    return types.MappingProxyType(
        {
            "price_all_v3_contract_sha256": actual,
            "pr253_contract_sha256": source[
                "current_live_quote_mapping_contract_sha256"
            ],
            "price_all_v2_contract_sha256": frozen_v2[
                "price_all_v2_contract_sha256"
            ],
        }
    )


def _same_partition_ancestry(
    left: current.CurrentDirectProviderMappedQuote,
    right: current.CurrentDirectProviderMappedQuote,
) -> bool:
    return all(
        getattr(left, field) == getattr(right, field)
        for field in _PARTITION_ANCESTRY_FIELDS
    )


def _partition_quotes(
    candidate: CalibratedValueCandidate,
    quote: current.CurrentDirectProviderMappedQuote,
    quotes: Sequence[current.CurrentDirectProviderMappedQuote],
) -> tuple[DevigStatus, float | None, float | None]:
    family = MARKET_REGISTRY[candidate.market_id].family
    if family in {MarketFamily.DOUBLE_CHANCE, MarketFamily.EARLY_PAYOUT}:
        return DevigStatus.NOT_IDENTIFIABLE_OVERLAPPING_EVENTS, None, None
    if family in {MarketFamily.DRAW_NO_BET, MarketFamily.ASIAN_HANDICAP}:
        return DevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT, None, None
    if family is MarketFamily.TOTAL_GOALS:
        quarter_units = Decimal(str(candidate.line)) * 4
        if (
            quarter_units != quarter_units.to_integral_value()
            or int(quarter_units) % 4 != 2
        ):
            return DevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT, None, None
    expected = _ORDINARY_PARTITIONS.get(candidate.market_id)
    if expected is None:
        return DevigStatus.UNAVAILABLE_INCOMPLETE_PARTITION, None, None
    same = tuple(item for item in quotes if _same_partition_ancestry(item, quote))
    by_outcome: dict[OutcomeId, current.CurrentDirectProviderMappedQuote] = {}
    duplicate = False
    for item in same:
        if item.canonical_outcome_id in by_outcome:
            duplicate = True
        by_outcome[item.canonical_outcome_id] = item
    if duplicate or set(by_outcome) != set(expected):
        return DevigStatus.UNAVAILABLE_INCOMPLETE_PARTITION, None, None
    overround = math.fsum(1.0 / by_outcome[item].decimal_odds for item in expected)
    if not math.isfinite(overround) or overround <= 0.0:
        raise PriceAllV3CurrentProviderError("provider partition overround is invalid")
    return (
        DevigStatus.AVAILABLE_COMPLETE_PARTITION,
        overround,
        (1.0 / quote.decimal_odds) / overround,
    )


@dataclasses.dataclass(frozen=True, init=False)
class PriceAllV3CurrentProviderResult:
    candidate: CalibratedValueCandidate
    disposition: CurrentProviderPriceDisposition
    reason: str
    quote: current.CurrentDirectProviderMappedQuote | None
    evaluation_time: datetime
    quote_age_seconds: float | None
    kickoff_lead_seconds: float
    raw_implied_probability: float | None
    devig_status: DevigStatus | None
    devig_method: str | None
    overround: float | None
    fair_probability: float | None
    settlement_returns: tuple[tuple[str, float], ...]
    expected_return_multiplier: float | None
    net_expected_value: float | None
    ev_percentage: float | None
    source_bundle_sha256: str
    current_inventory_sha256: str
    source_manifest_sha256: str
    source_raw_sha256: str
    current_mapping_rebind_sha256: str
    current_mapping_contract_sha256: str
    source_current_reconciliation_sha256: str
    source_legacy_mapping_sha256: str
    price_all_v3_contract_sha256: str

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise PriceAllV3CurrentProviderError("Price-all v3 results are builder-only")

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "disposition": self.disposition.value,
            "reason": self.reason,
            "quote": None if self.quote is None else self.quote.to_dict(),
            "evaluation_time": self.evaluation_time.isoformat().replace("+00:00", "Z"),
            "quote_age_seconds": self.quote_age_seconds,
            "kickoff_lead_seconds": self.kickoff_lead_seconds,
            "raw_implied_probability": self.raw_implied_probability,
            "devig_status": None if self.devig_status is None else self.devig_status.value,
            "devig_method": self.devig_method,
            "overround": self.overround,
            "fair_probability": self.fair_probability,
            "settlement_returns": [
                {"state": state, "unit_stake_profit": profit}
                for state, profit in self.settlement_returns
            ],
            "expected_return_multiplier": self.expected_return_multiplier,
            "net_expected_value": self.net_expected_value,
            "ev_percentage": self.ev_percentage,
            "source_bundle_sha256": self.source_bundle_sha256,
            "current_inventory_sha256": self.current_inventory_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "current_mapping_rebind_sha256": self.current_mapping_rebind_sha256,
            "current_mapping_contract_sha256": self.current_mapping_contract_sha256,
            "source_current_reconciliation_sha256": self.source_current_reconciliation_sha256,
            "source_legacy_mapping_sha256": self.source_legacy_mapping_sha256,
            "price_all_v3_contract_sha256": self.price_all_v3_contract_sha256,
            "authority": dict(_AUTHORITY),
        }


@dataclasses.dataclass(frozen=True, init=False)
class PriceAllV3CurrentProviderEvaluation:
    dataset_name: str
    status: str
    proof_mode: str
    fixture_id: str
    event_id: str
    home_team_name: str
    away_team_name: str
    evaluation_time: datetime
    source_evaluation_time: datetime
    discovery_observed_at: datetime
    direct_event_observed_at: datetime
    kickoff_utc: datetime
    discovery_age_seconds: float
    direct_event_age_seconds: float
    kickoff_lead_seconds: float
    max_quote_age_seconds: int
    minimum_lead_seconds: int
    source_bundle_sha256: str
    pr253_contract_sha256: str
    price_all_v2_contract_sha256: str
    price_all_v3_contract_sha256: str
    current_mapping_rebind_sha256: str
    current_mapping_contract_sha256: str
    source_current_reconciliation_sha256: str
    source_legacy_mapping_sha256: str
    current_inventory_sha256: str
    current_manifest_sha256: str
    current_raw_sha256: str
    results: tuple[PriceAllV3CurrentProviderResult, ...]
    quote_audits: tuple[current.CurrentMappedQuoteAudit, ...]
    authority: Mapping[str, bool]
    next_boundary: str
    _candidates: tuple[CalibratedValueCandidate, ...]
    _source_bundle: current.CurrentDirectProviderMappedQuoteBundle
    _require_live_current: bool

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise PriceAllV3CurrentProviderError("Price-all v3 evaluations are builder-only")

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "status": self.status,
            "proof_mode": self.proof_mode,
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "evaluation_time": self.evaluation_time.isoformat().replace("+00:00", "Z"),
            "source_evaluation_time": self.source_evaluation_time.isoformat().replace("+00:00", "Z"),
            "discovery_observed_at": self.discovery_observed_at.isoformat().replace("+00:00", "Z"),
            "direct_event_observed_at": self.direct_event_observed_at.isoformat().replace("+00:00", "Z"),
            "kickoff_utc": self.kickoff_utc.isoformat().replace("+00:00", "Z"),
            "discovery_age_seconds": self.discovery_age_seconds,
            "direct_event_age_seconds": self.direct_event_age_seconds,
            "kickoff_lead_seconds": self.kickoff_lead_seconds,
            "max_quote_age_seconds": self.max_quote_age_seconds,
            "minimum_lead_seconds": self.minimum_lead_seconds,
            "source_bundle_sha256": self.source_bundle_sha256,
            "pr253_contract_sha256": self.pr253_contract_sha256,
            "price_all_v2_contract_sha256": self.price_all_v2_contract_sha256,
            "price_all_v3_contract_sha256": self.price_all_v3_contract_sha256,
            "current_mapping_rebind_sha256": self.current_mapping_rebind_sha256,
            "current_mapping_contract_sha256": self.current_mapping_contract_sha256,
            "source_current_reconciliation_sha256": self.source_current_reconciliation_sha256,
            "source_legacy_mapping_sha256": self.source_legacy_mapping_sha256,
            "current_inventory_sha256": self.current_inventory_sha256,
            "current_manifest_sha256": self.current_manifest_sha256,
            "current_raw_sha256": self.current_raw_sha256,
            "result_count": len(self.results),
            "results": [item.to_dict() for item in self.results],
            "quote_audits": [item.to_dict() for item in self.quote_audits],
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "wager_placed": False,
        }


def _set_frozen(obj: Any, values: Mapping[str, Any]) -> Any:
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    return obj


def _empty_result(
    *,
    candidate: CalibratedValueCandidate,
    disposition: CurrentProviderPriceDisposition,
    reason: str,
    now: datetime,
    kickoff_lead_seconds: float,
    source: current.CurrentDirectProviderMappedQuoteBundle,
    contract_sha256: str,
    quote: current.CurrentDirectProviderMappedQuote | None = None,
    quote_age_seconds: float | None = None,
) -> PriceAllV3CurrentProviderResult:
    value = object.__new__(PriceAllV3CurrentProviderResult)
    return _set_frozen(
        value,
        {
            "candidate": candidate,
            "disposition": disposition,
            "reason": reason,
            "quote": quote,
            "evaluation_time": now,
            "quote_age_seconds": quote_age_seconds,
            "kickoff_lead_seconds": kickoff_lead_seconds,
            "raw_implied_probability": None,
            "devig_status": None,
            "devig_method": None,
            "overround": None,
            "fair_probability": None,
            "settlement_returns": (),
            "expected_return_multiplier": None,
            "net_expected_value": None,
            "ev_percentage": None,
            "source_bundle_sha256": source.canonical_sha256,
            "current_inventory_sha256": source.current_inventory_sha256,
            "source_manifest_sha256": source.current_manifest_sha256,
            "source_raw_sha256": source.current_raw_sha256,
            "current_mapping_rebind_sha256": source.current_mapping_rebind_sha256,
            "current_mapping_contract_sha256": source.current_mapping_contract_sha256,
            "source_current_reconciliation_sha256": source.source_current_reconciliation_sha256,
            "source_legacy_mapping_sha256": source.source_legacy_mapping_sha256,
            "price_all_v3_contract_sha256": contract_sha256,
        },
    )


def _price_one(
    *,
    candidate: CalibratedValueCandidate,
    source: current.CurrentDirectProviderMappedQuoteBundle,
    now: datetime,
    discovery_age: float,
    direct_age: float,
    kickoff_lead: float,
    max_age: int,
    minimum_lead: int,
    contract_sha256: str,
) -> PriceAllV3CurrentProviderResult:
    common = {
        "candidate": candidate,
        "now": now,
        "kickoff_lead_seconds": kickoff_lead,
        "source": source,
        "contract_sha256": contract_sha256,
    }
    if candidate.market_id in _EARLY_OR_WEH:
        return _empty_result(
            **common,
            disposition=CurrentProviderPriceDisposition.BLOCKED_UPSTREAM_PROBABILITY_UNAVAILABLE,
            reason="upstream calibrated specialist probability authority is unavailable",
        )
    if candidate.fixture_id != source.fixture_id or candidate.sportybet_event_id != source.event_id:
        return _empty_result(
            **common,
            disposition=CurrentProviderPriceDisposition.UNPRICED_SOURCE_MISMATCH,
            reason="candidate fixture/event differs from exact PR253 source",
        )
    exact = tuple(
        quote
        for quote in source.quotes
        if quote.fixture_id == candidate.fixture_id
        and quote.event_id == candidate.sportybet_event_id
        and quote.canonical_market_id is candidate.market_id
        and quote.canonical_outcome_id is candidate.outcome_id
        and quote.canonical_line == candidate.line
    )
    if not exact:
        audits = tuple(
            audit for audit in source.quote_audits
            if audit.canonical_market_id is candidate.market_id
            and audit.canonical_outcome_id is candidate.outcome_id
            and audit.canonical_line == candidate.line
        )
        if len(audits) == 1 and audits[0].disposition is current.QuoteAuditDisposition.SETTLEMENT_EQUIVALENCE_UNPROVEN:
            return _empty_result(
                **common,
                disposition=CurrentProviderPriceDisposition.UNPRICED_SETTLEMENT_EQUIVALENCE_UNPROVEN,
                reason="PR253 exact mapping lacks reviewed settlement equivalence",
            )
        if len(audits) == 1 and audits[0].disposition is current.QuoteAuditDisposition.CURRENTLY_UNAVAILABLE:
            return _empty_result(
                **common,
                disposition=CurrentProviderPriceDisposition.UNPRICED_CURRENTLY_UNAVAILABLE,
                reason="PR253 exact provider outcome is currently unavailable",
            )
        return _empty_result(
            **common,
            disposition=CurrentProviderPriceDisposition.UNPRICED_NO_EXACT_QUOTE,
            reason="no exact current fixture/event/market/outcome/line quote",
        )
    if len(exact) != 1:
        return _empty_result(
            **common,
            disposition=CurrentProviderPriceDisposition.UNPRICED_AMBIGUOUS_QUOTE,
            reason="duplicate exact PR253 current quote",
        )
    quote = exact[0]
    quote_age = (now - quote.observed_at).total_seconds()
    if (
        quote.observed_at != source.direct_event_observed_at
        or quote.current_inventory_sha256 != source.current_inventory_sha256
        or quote.source_manifest_sha256 != source.current_manifest_sha256
        or quote.source_raw_sha256 != source.current_raw_sha256
        or quote.current_mapping_rebind_sha256 != source.current_mapping_rebind_sha256
        or quote.source_current_reconciliation_sha256 != source.source_current_reconciliation_sha256
        or quote.source_legacy_mapping_sha256 != source.source_legacy_mapping_sha256
    ):
        raise PriceAllV3CurrentProviderError(
            "quote ancestry differs from reconstructed PR253 source"
        )
    if not math.isclose(quote_age, direct_age, abs_tol=1e-9, rel_tol=0.0):
        raise PriceAllV3CurrentProviderError("quote/source age identity mismatch")
    if discovery_age > max_age or quote_age > max_age:
        return _empty_result(
            **common,
            quote=quote,
            quote_age_seconds=quote_age,
            disposition=CurrentProviderPriceDisposition.UNPRICED_STALE_QUOTE,
            reason="PR253 source exceeds Price-all v3 freshness policy",
        )
    if kickoff_lead <= minimum_lead:
        return _empty_result(
            **common,
            quote=quote,
            quote_age_seconds=quote_age,
            disposition=CurrentProviderPriceDisposition.UNPRICED_NEAR_KICKOFF,
            reason="current provider quote is too close to kickoff at Price-all v3 evaluation",
        )
    if quote.settlement_equivalence_authority is SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN:
        return _empty_result(
            **common,
            quote=quote,
            quote_age_seconds=quote_age,
            disposition=CurrentProviderPriceDisposition.UNPRICED_SETTLEMENT_EQUIVALENCE_UNPROVEN,
            reason="reviewed provider settlement equivalence is absent",
        )
    try:
        returns, ev = v2._settlement_ev(candidate, quote.decimal_odds)
    except v2.PriceAllV2DirectProviderError:
        return _empty_result(
            **common,
            quote=quote,
            quote_age_seconds=quote_age,
            disposition=CurrentProviderPriceDisposition.BLOCKED_SETTLEMENT_DISTRIBUTION_INCOMPLETE,
            reason="full reviewed settlement probability representation is required",
        )
    devig, overround, fair = _partition_quotes(candidate, quote, source.quotes)
    value = _empty_result(
        **common,
        disposition=CurrentProviderPriceDisposition.PRICED,
        reason="exact reconstructed PR253 quote priced without routing or selection",
        quote=quote,
        quote_age_seconds=quote_age,
    )
    return _set_frozen(
        value,
        {
            "raw_implied_probability": 1.0 / quote.decimal_odds,
            "devig_status": devig,
            "devig_method": "PROPORTIONAL_MULTIPLICATIVE" if fair is not None else None,
            "overround": overround,
            "fair_probability": fair,
            "settlement_returns": returns,
            "expected_return_multiplier": 1.0 + ev,
            "net_expected_value": ev,
            "ev_percentage": ev * 100.0,
        },
    )


def _build(
    candidates: Iterable[CalibratedValueCandidate],
    source_bundle: current.CurrentDirectProviderMappedQuoteBundle,
    *,
    evaluation_time: datetime,
    max_quote_age_seconds: int,
    minimum_lead_seconds: int,
    require_live_current: bool,
) -> PriceAllV3CurrentProviderEvaluation:
    contracts = validate_price_all_v3_contract()
    now = _utc(evaluation_time, "evaluation_time")
    if type(source_bundle) is not current.CurrentDirectProviderMappedQuoteBundle:
        raise PriceAllV3CurrentProviderError(
            "source_bundle must be exact PR253 mapped quote bundle"
        )
    try:
        source = current.verify_current_direct_provider_mapped_quote_bundle(source_bundle)
    except current.CurrentDirectProviderLiveQuoteMappingConsumptionError as exc:
        raise PriceAllV3CurrentProviderError("PR253 source reconstruction failed") from exc
    if (
        source.dataset_name != current.DATASET_NAME
        or source.contract_sha256 != PR253_CONTRACT_SHA256
        or source.next_boundary != current.NEXT_BOUNDARY
    ):
        raise PriceAllV3CurrentProviderError("PR253 source state is not approved")
    if require_live_current and (
        source.proof_mode != LIVE_CURRENT
        or source.status != current.STATUS_LIVE
        or source.authority.get("wall_clock_currentness_at_issuance") is not True
    ):
        raise PriceAllV3CurrentProviderError(
            "live Price-all v3 requires exact PR253 LIVE_CURRENT source"
        )
    if (
        source.authority.get("current_provider_mapped_quote_evidence") is not bool(source.quotes)
        or source.authority.get("price_all") is not False
        or source.authority.get("bet") is not False
    ):
        raise PriceAllV3CurrentProviderError("PR253 authority flags mismatch")
    if type(max_quote_age_seconds) is not int or not 0 <= max_quote_age_seconds <= min(DEFAULT_MAX_QUOTE_AGE_SECONDS, source.max_source_age_seconds):
        raise PriceAllV3CurrentProviderError("max_quote_age_seconds weakens upstream policy")
    if type(minimum_lead_seconds) is not int or minimum_lead_seconds < max(DEFAULT_MINIMUM_LEAD_SECONDS, source.minimum_lead_seconds):
        raise PriceAllV3CurrentProviderError("minimum_lead_seconds weakens upstream policy")
    if now < source.evaluation_time:
        raise PriceAllV3CurrentProviderError("evaluation_time predates PR253 issuance")
    discovery_age = (now - _utc(source.discovery_observed_at, "discovery_observed_at")).total_seconds()
    direct_age = (now - _utc(source.direct_event_observed_at, "direct_event_observed_at")).total_seconds()
    kickoff_lead = (_utc(source.kickoff_utc, "kickoff_utc") - now).total_seconds()
    if any(not math.isfinite(value) for value in (discovery_age, direct_age, kickoff_lead)):
        raise PriceAllV3CurrentProviderError("Price-all v3 source timing is non-finite")
    if discovery_age < 0 or direct_age < 0:
        raise PriceAllV3CurrentProviderError("PR253 evidence is future-dated")
    values = tuple(candidates)
    if any(type(item) is not CalibratedValueCandidate for item in values):
        raise PriceAllV3CurrentProviderError(
            "candidates must be exact Phase 6 calibrated value candidates"
        )
    if len({item.candidate_id for item in values}) != len(values):
        raise PriceAllV3CurrentProviderError("candidate_id must be unique")
    results = tuple(
        _price_one(
            candidate=item,
            source=source,
            now=now,
            discovery_age=discovery_age,
            direct_age=direct_age,
            kickoff_lead=kickoff_lead,
            max_age=max_quote_age_seconds,
            minimum_lead=minimum_lead_seconds,
            contract_sha256=contracts["price_all_v3_contract_sha256"],
        )
        for item in sorted(values, key=lambda row: row.candidate_id)
    )
    value = object.__new__(PriceAllV3CurrentProviderEvaluation)
    return _set_frozen(
        value,
        {
            "dataset_name": DATASET_NAME,
            "status": STATUS_LIVE if require_live_current else STATUS_AS_OF,
            "proof_mode": source.proof_mode,
            "fixture_id": source.fixture_id,
            "event_id": source.event_id,
            "home_team_name": source.home_team_name,
            "away_team_name": source.away_team_name,
            "evaluation_time": now,
            "source_evaluation_time": source.evaluation_time,
            "discovery_observed_at": source.discovery_observed_at,
            "direct_event_observed_at": source.direct_event_observed_at,
            "kickoff_utc": source.kickoff_utc,
            "discovery_age_seconds": discovery_age,
            "direct_event_age_seconds": direct_age,
            "kickoff_lead_seconds": kickoff_lead,
            "max_quote_age_seconds": max_quote_age_seconds,
            "minimum_lead_seconds": minimum_lead_seconds,
            "source_bundle_sha256": source.canonical_sha256,
            "pr253_contract_sha256": PR253_CONTRACT_SHA256,
            "price_all_v2_contract_sha256": PRICE_ALL_V2_CONTRACT_SHA256,
            "price_all_v3_contract_sha256": contracts["price_all_v3_contract_sha256"],
            "current_mapping_rebind_sha256": source.current_mapping_rebind_sha256,
            "current_mapping_contract_sha256": source.current_mapping_contract_sha256,
            "source_current_reconciliation_sha256": source.source_current_reconciliation_sha256,
            "source_legacy_mapping_sha256": source.source_legacy_mapping_sha256,
            "current_inventory_sha256": source.current_inventory_sha256,
            "current_manifest_sha256": source.current_manifest_sha256,
            "current_raw_sha256": source.current_raw_sha256,
            "results": results,
            "quote_audits": tuple(source.quote_audits),
            "authority": types.MappingProxyType(dict(_AUTHORITY)),
            "next_boundary": NEXT_BOUNDARY,
            "_candidates": values,
            "_source_bundle": source_bundle,
            "_require_live_current": require_live_current,
        },
    )


def price_all_current_provider_candidates_as_of(
    candidates: Iterable[CalibratedValueCandidate],
    source_bundle: current.CurrentDirectProviderMappedQuoteBundle,
    *,
    evaluation_time: datetime,
    max_quote_age_seconds: int = DEFAULT_MAX_QUOTE_AGE_SECONDS,
    minimum_lead_seconds: int = DEFAULT_MINIMUM_LEAD_SECONDS,
) -> PriceAllV3CurrentProviderEvaluation:
    """Deterministic replay lane; never claims wall-clock currentness."""
    return _build(
        candidates,
        source_bundle,
        evaluation_time=evaluation_time,
        max_quote_age_seconds=max_quote_age_seconds,
        minimum_lead_seconds=minimum_lead_seconds,
        require_live_current=False,
    )


def price_all_current_provider_candidates(
    candidates: Iterable[CalibratedValueCandidate],
    source_bundle: current.CurrentDirectProviderMappedQuoteBundle,
    *,
    max_quote_age_seconds: int = DEFAULT_MAX_QUOTE_AGE_SECONDS,
    minimum_lead_seconds: int = DEFAULT_MINIMUM_LEAD_SECONDS,
) -> PriceAllV3CurrentProviderEvaluation:
    """Production lane requiring exact PR253 live-current issuance.

    Wall-clock evaluation time is acquired internally so a production caller
    cannot mint freshness by supplying a favorable timestamp.
    """
    return _build(
        candidates,
        source_bundle,
        evaluation_time=_now_utc(),
        max_quote_age_seconds=max_quote_age_seconds,
        minimum_lead_seconds=minimum_lead_seconds,
        require_live_current=True,
    )


def verify_price_all_v3_current_provider_evaluation(
    value: Any,
) -> PriceAllV3CurrentProviderEvaluation:
    if type(value) is not PriceAllV3CurrentProviderEvaluation:
        raise PriceAllV3CurrentProviderError(
            "value must be exact PriceAllV3CurrentProviderEvaluation"
        )
    rebuilt = _build(
        value._candidates,
        value._source_bundle,
        evaluation_time=value.evaluation_time,
        max_quote_age_seconds=value.max_quote_age_seconds,
        minimum_lead_seconds=value.minimum_lead_seconds,
        require_live_current=value._require_live_current,
    )
    if _canonical_bytes(rebuilt.to_dict()) != _canonical_bytes(value.to_dict()):
        raise PriceAllV3CurrentProviderError(
            "Price-all v3 evaluation differs from exact source reconstruction"
        )
    return rebuilt


__all__ = [name for name in globals() if not name.startswith("_")]
