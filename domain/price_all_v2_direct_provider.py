"""ATHENA Price-all v2 direct-provider current quote consumption.

This boundary consumes only the exact current SportyBet direct-provider quote
source issued by ``sportybet_price_all_direct_provider_quote_adapter``.  It
preserves the frozen Phase 7 v1 contract and adds an explicit v2 lane for the
reviewed FactsCenter event-read ancestry introduced by PR246/PR247.

The evaluator recomputes source freshness and kickoff lead at its own
evaluation time, prices every exact calibrated candidate, and never ranks,
routes, selects, constructs an accumulator, generates a booking code, stakes,
or places a wager.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
import math
import types
from typing import Any, Iterable, Mapping, Sequence

from domain import sportybet_live_event_quote_evidence as live
from domain import sportybet_price_all_direct_provider_quote_adapter as adapter
from domain._price_all_contracts import (
    CalibratedValueCandidate,
    DevigStatus,
    DEVIG_POLICY_ID,
    PriceAllError,
    SETTLEMENT_RETURN_POLICY_ID,
    SettlementState,
    validate_price_all_contract,
)
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId
from domain.sportybet_reviewed_canonical_market_mapping import (
    SettlementEquivalenceAuthority,
)


SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-price-all-v2-direct-provider-value-evaluation-v1"
STATUS = "PRICE_ALL_V2_DIRECT_PROVIDER_VALUE_EVALUATION_VERIFIED"
QUOTE_POLICY_ID = (
    "DIRECT_PROVIDER_RESPONSE_COMPLETION_FRESH_900S_AND_120S_KICKOFF_LEAD_V1"
)
NO_ROUTER_POLICY_ID = "PRICE_ALL_V2_NO_RANK_ROUTE_SELECT_OR_BET_V1"
DEFAULT_MAX_QUOTE_AGE_SECONDS = live.MAX_OBSERVATION_AGE_SECONDS
DEFAULT_MINIMUM_LEAD_SECONDS = live.MINIMUM_LEAD_SECONDS
LEGACY_PRICE_ALL_V1_CONTRACT_SHA256 = adapter.LEGACY_PRICE_ALL_V1_CONTRACT_SHA256
SOURCE_ADAPTER_CONTRACT_SHA256 = adapter.EXPECTED_CONTRACT_SHA256
NEXT_BOUNDARY = "MARKET_ROUTER_V2_DIRECT_PROVIDER_VALUE_CONSUMPTION_REQUIRED"
EXPECTED_CONTRACT_SHA256 = (
    "b5e3c063ac8b4e9fc1521cabbfe1da873a67b70efc67bc08d8ada61f2024e599"
)

_AUTHORITY = types.MappingProxyType(
    {
        "verified_direct_provider_price_consumption": True,
        "value_record_computation": True,
        "football_probability_generation": False,
        "model_promotion": False,
        "market_router": False,
        "final_selection": False,
        "accumulator": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
    }
)

_PARTITION_ANCESTRY_FIELDS = (
    "fixture_id",
    "event_id",
    "source",
    "provider_market_id",
    "provider_specifier",
    "canonical_market_id",
    "canonical_line",
    "live_inventory_sha256",
    "source_bundle_sha256",
    "source_manifest_sha256",
    "source_raw_sha256",
    "reviewed_mapping_sha256",
    "fixture_reconciliation_sha256",
)

_EARLY_OR_WEH = frozenset(
    {
        MarketId.HOME_WIN_EITHER_HALF,
        MarketId.AWAY_WIN_EITHER_HALF,
        MarketId.MATCH_RESULT_1UP,
        MarketId.MATCH_RESULT_2UP,
    }
)

_ORDINARY_PARTITIONS: Mapping[MarketId, tuple[OutcomeId, ...]] = types.MappingProxyType(
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


class PriceAllV2DirectProviderError(ValueError):
    """Raised when the v2 direct-provider Price-all boundary fails closed."""


class DirectProviderPriceDisposition(str, Enum):
    PRICED = "PRICED"
    UNPRICED_SOURCE_MISMATCH = "UNPRICED_SOURCE_MISMATCH"
    UNPRICED_NO_EXACT_QUOTE = "UNPRICED_NO_EXACT_QUOTE"
    UNPRICED_STALE_QUOTE = "UNPRICED_STALE_QUOTE"
    UNPRICED_AMBIGUOUS_QUOTE = "UNPRICED_AMBIGUOUS_QUOTE"
    UNPRICED_NEAR_KICKOFF = "UNPRICED_NEAR_KICKOFF"
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
        raise PriceAllV2DirectProviderError(
            "canonical JSON serialization failed"
        ) from exc


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise PriceAllV2DirectProviderError(f"{label} must be timezone-aware")
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PriceAllV2DirectProviderError(f"{label} is invalid") from exc


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "source_adapter_dataset_name": adapter.DATASET_NAME,
        "source_adapter_status": adapter.STATUS,
        "source_adapter_contract_sha256": SOURCE_ADAPTER_CONTRACT_SHA256,
        "legacy_price_all_v1_contract_sha256": LEGACY_PRICE_ALL_V1_CONTRACT_SHA256,
        "source_observation_authority": live.OBSERVATION_AUTHORITY,
        "provider_quote_timestamp": None,
        "provider_snapshot_id": None,
        "quote_policy_id": QUOTE_POLICY_ID,
        "max_quote_age_seconds": DEFAULT_MAX_QUOTE_AGE_SECONDS,
        "minimum_kickoff_lead_seconds": DEFAULT_MINIMUM_LEAD_SECONDS,
        "devig_policy_id": DEVIG_POLICY_ID,
        "settlement_return_policy_id": SETTLEMENT_RETURN_POLICY_ID,
        "partition_ancestry_fields": list(_PARTITION_ANCESTRY_FIELDS),
        "no_router_policy_id": NO_ROUTER_POLICY_ID,
        "next_boundary": NEXT_BOUNDARY,
        "authority": dict(_AUTHORITY),
    }


def calculate_price_all_v2_contract_sha256() -> str:
    return hashlib.sha256(
        _canonical_bytes(
            {"version": CONTRACT_VERSION, "semantics": _contract_payload()}
        )
    ).hexdigest()


def validate_price_all_v2_contract() -> Mapping[str, str]:
    try:
        source_contracts = adapter.validate_adapter_contract()
        legacy = validate_price_all_contract()
    except (adapter.SportyBetPriceAllDirectProviderQuoteAdapterError, PriceAllError) as exc:
        raise PriceAllV2DirectProviderError(
            "Price-all v2 dependency validation failed"
        ) from exc
    if source_contracts["adapter_contract_sha256"] != SOURCE_ADAPTER_CONTRACT_SHA256:
        raise PriceAllV2DirectProviderError("direct-provider adapter identity drifted")
    if (
        source_contracts["legacy_price_all_v1_contract_sha256"]
        != LEGACY_PRICE_ALL_V1_CONTRACT_SHA256
        or legacy["price_all_contract_sha256"] != LEGACY_PRICE_ALL_V1_CONTRACT_SHA256
    ):
        raise PriceAllV2DirectProviderError("legacy Price-all v1 identity drifted")
    actual = calculate_price_all_v2_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise PriceAllV2DirectProviderError("Price-all v2 contract drifted")
    return types.MappingProxyType(
        {
            "price_all_v2_contract_sha256": actual,
            "source_adapter_contract_sha256": source_contracts[
                "adapter_contract_sha256"
            ],
            "legacy_price_all_v1_contract_sha256": legacy[
                "price_all_contract_sha256"
            ],
        }
    )


def _required_states(
    candidate: CalibratedValueCandidate,
) -> tuple[SettlementState, ...]:
    family = MARKET_REGISTRY[candidate.market_id].family
    if family is MarketFamily.DRAW_NO_BET:
        return (SettlementState.WIN, SettlementState.PUSH, SettlementState.LOSS)
    if family is MarketFamily.ASIAN_HANDICAP:
        return tuple(SettlementState)
    if family is MarketFamily.TOTAL_GOALS:
        quarter_units = Decimal(str(candidate.line)) * 4
        if quarter_units != quarter_units.to_integral_value():
            raise PriceAllV2DirectProviderError(
                "total-goals line lacks reviewed quarter-goal settlement semantics"
            )
        modulo = int(quarter_units) % 4
        if modulo == 0:
            return (SettlementState.WIN, SettlementState.PUSH, SettlementState.LOSS)
        if modulo == 2:
            return (SettlementState.WIN, SettlementState.LOSS)
        return tuple(SettlementState)
    return (SettlementState.WIN, SettlementState.LOSS)


def _settlement_ev(
    candidate: CalibratedValueCandidate,
    odds: float,
) -> tuple[tuple[tuple[str, float], ...], float]:
    required = _required_states(candidate)
    supplied = candidate.probability_map
    required_names = {state.value for state in required}
    if set(supplied) == required_names:
        settlement_probabilities = supplied
    else:
        partition = _ORDINARY_PARTITIONS.get(candidate.market_id)
        unit = dict(candidate.calibration_unit)
        if (
            required == (SettlementState.WIN, SettlementState.LOSS)
            and set(supplied) == {"YES", "NO"}
            and unit.get("selection_outcome") == candidate.outcome_id.value
        ):
            settlement_probabilities = types.MappingProxyType(
                {
                    SettlementState.WIN.value: supplied["YES"],
                    SettlementState.LOSS.value: supplied["NO"],
                }
            )
        elif (
            required == (SettlementState.WIN, SettlementState.LOSS)
            and partition is not None
            and set(supplied) == {outcome.value for outcome in partition}
        ):
            win = supplied[candidate.outcome_id.value]
            settlement_probabilities = types.MappingProxyType(
                {
                    SettlementState.WIN.value: win,
                    SettlementState.LOSS.value: math.fsum(
                        probability
                        for name, probability in supplied.items()
                        if name != candidate.outcome_id.value
                    ),
                }
            )
        else:
            raise PriceAllV2DirectProviderError(
                "calibrated settlement distribution is incomplete"
            )
    returns = {
        SettlementState.WIN: odds - 1.0,
        SettlementState.HALF_WIN: (odds - 1.0) / 2.0,
        SettlementState.PUSH: 0.0,
        SettlementState.HALF_LOSS: -0.5,
        SettlementState.LOSS: -1.0,
    }
    serialized = tuple((state.value, returns[state]) for state in required)
    ev = math.fsum(
        settlement_probabilities[state.value] * returns[state] for state in required
    )
    return serialized, ev


def _same_partition_ancestry(
    left: adapter.SportyBetDirectProviderPriceAllQuote,
    right: adapter.SportyBetDirectProviderPriceAllQuote,
) -> bool:
    return (
        left.fixture_id == right.fixture_id
        and left.event_id == right.event_id
        and left.source == right.source
        and left.provider_market_id == right.provider_market_id
        and left.provider_specifier == right.provider_specifier
        and left.canonical_market_id is right.canonical_market_id
        and left.canonical_line == right.canonical_line
        and left.live_inventory_sha256 == right.live_inventory_sha256
        and left.source_bundle_sha256 == right.source_bundle_sha256
        and left.source_manifest_sha256 == right.source_manifest_sha256
        and left.source_raw_sha256 == right.source_raw_sha256
        and left.reviewed_mapping_sha256 == right.reviewed_mapping_sha256
        and left.fixture_reconciliation_sha256
        == right.fixture_reconciliation_sha256
    )


def _partition_quotes(
    candidate: CalibratedValueCandidate,
    quote: adapter.SportyBetDirectProviderPriceAllQuote,
    quotes: Sequence[adapter.SportyBetDirectProviderPriceAllQuote],
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
            return (
                DevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT,
                None,
                None,
            )
    expected = _ORDINARY_PARTITIONS.get(candidate.market_id)
    if expected is None:
        return DevigStatus.UNAVAILABLE_INCOMPLETE_PARTITION, None, None

    same = tuple(item for item in quotes if _same_partition_ancestry(item, quote))
    by_outcome: dict[OutcomeId, adapter.SportyBetDirectProviderPriceAllQuote] = {}
    duplicate = False
    for item in same:
        if item.canonical_outcome_id in by_outcome:
            duplicate = True
        by_outcome[item.canonical_outcome_id] = item
    if duplicate or set(by_outcome) != set(expected):
        return DevigStatus.UNAVAILABLE_INCOMPLETE_PARTITION, None, None
    overround = math.fsum(1.0 / by_outcome[outcome].decimal_odds for outcome in expected)
    if not math.isfinite(overround) or overround <= 0:
        raise PriceAllV2DirectProviderError("direct-provider partition overround is invalid")
    fair = (1.0 / quote.decimal_odds) / overround
    return DevigStatus.AVAILABLE_COMPLETE_PARTITION, overround, fair


@dataclass(frozen=True, init=False)
class PriceAllV2DirectProviderResult:
    candidate: CalibratedValueCandidate
    disposition: DirectProviderPriceDisposition
    reason: str
    quote: adapter.SportyBetDirectProviderPriceAllQuote | None
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
    source_quote_source_sha256: str
    source_bundle_sha256: str
    adapter_contract_sha256: str
    legacy_price_all_v1_contract_sha256: str
    price_all_v2_contract_sha256: str

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise PriceAllV2DirectProviderError(
            "Price-all v2 results are issued only by verified direct-provider evaluation"
        )

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "disposition": self.disposition.value,
            "reason": self.reason,
            "quote": None if self.quote is None else self.quote.to_dict(),
            "evaluation_time": self.evaluation_time.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "quote_age_seconds": self.quote_age_seconds,
            "kickoff_lead_seconds": self.kickoff_lead_seconds,
            "raw_implied_probability": self.raw_implied_probability,
            "devig_status": (
                None if self.devig_status is None else self.devig_status.value
            ),
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
            "source_quote_source_sha256": self.source_quote_source_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "adapter_contract_sha256": self.adapter_contract_sha256,
            "legacy_price_all_v1_contract_sha256": (
                self.legacy_price_all_v1_contract_sha256
            ),
            "price_all_v2_contract_sha256": self.price_all_v2_contract_sha256,
            "authority": dict(_AUTHORITY),
        }


@dataclass(frozen=True, init=False)
class PriceAllV2DirectProviderEvaluation:
    dataset_name: str
    status: str
    fixture_id: str
    event_id: str
    evaluation_time: datetime
    source_observed_at: datetime
    source_evaluation_time: datetime
    kickoff_utc: datetime
    quote_age_seconds: float
    kickoff_lead_seconds: float
    max_quote_age_seconds: int
    minimum_lead_seconds: int
    source_quote_source_sha256: str
    source_bundle_sha256: str
    source_adapter_contract_sha256: str
    legacy_price_all_v1_contract_sha256: str
    price_all_v2_contract_sha256: str
    results: tuple[PriceAllV2DirectProviderResult, ...]
    mapping_audits: tuple[live.SportyBetLiveMappingAudit, ...]
    authority: Mapping[str, bool]
    next_boundary: str
    _candidates: tuple[CalibratedValueCandidate, ...]
    _quote_source: adapter.SportyBetDirectProviderPriceAllQuoteSource

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise PriceAllV2DirectProviderError(
            "Price-all v2 evaluations are issued only by verified direct-provider evaluation"
        )

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "status": self.status,
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "evaluation_time": self.evaluation_time.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "source_observed_at": self.source_observed_at.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "source_evaluation_time": self.source_evaluation_time.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "kickoff_utc": self.kickoff_utc.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "quote_age_seconds": self.quote_age_seconds,
            "kickoff_lead_seconds": self.kickoff_lead_seconds,
            "max_quote_age_seconds": self.max_quote_age_seconds,
            "minimum_lead_seconds": self.minimum_lead_seconds,
            "source_quote_source_sha256": self.source_quote_source_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_adapter_contract_sha256": self.source_adapter_contract_sha256,
            "legacy_price_all_v1_contract_sha256": (
                self.legacy_price_all_v1_contract_sha256
            ),
            "price_all_v2_contract_sha256": self.price_all_v2_contract_sha256,
            "result_count": len(self.results),
            "results": [item.to_dict() for item in self.results],
            "mapping_audits": [item.to_dict() for item in self.mapping_audits],
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
    disposition: DirectProviderPriceDisposition,
    reason: str,
    now: datetime,
    kickoff_lead_seconds: float,
    source_sha: str,
    source_bundle_sha: str,
    contracts: Mapping[str, str],
    quote: adapter.SportyBetDirectProviderPriceAllQuote | None = None,
    quote_age_seconds: float | None = None,
) -> PriceAllV2DirectProviderResult:
    value = object.__new__(PriceAllV2DirectProviderResult)
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
            "source_quote_source_sha256": source_sha,
            "source_bundle_sha256": source_bundle_sha,
            "adapter_contract_sha256": contracts["source_adapter_contract_sha256"],
            "legacy_price_all_v1_contract_sha256": contracts[
                "legacy_price_all_v1_contract_sha256"
            ],
            "price_all_v2_contract_sha256": contracts[
                "price_all_v2_contract_sha256"
            ],
        },
    )


def _price_one(
    *,
    candidate: CalibratedValueCandidate,
    quote_source: adapter.SportyBetDirectProviderPriceAllQuoteSource,
    now: datetime,
    source_age_seconds: float,
    kickoff_lead_seconds: float,
    max_quote_age_seconds: int,
    minimum_lead_seconds: int,
    contracts: Mapping[str, str],
    source_sha: str,
) -> PriceAllV2DirectProviderResult:
    if candidate.market_id in _EARLY_OR_WEH:
        return _empty_result(
            candidate=candidate,
            disposition=DirectProviderPriceDisposition.BLOCKED_UPSTREAM_PROBABILITY_UNAVAILABLE,
            reason="upstream calibrated probability authority is unavailable",
            now=now,
            kickoff_lead_seconds=kickoff_lead_seconds,
            source_sha=source_sha,
            source_bundle_sha=quote_source.source_bundle_sha256,
            contracts=contracts,
        )
    if (
        candidate.fixture_id != quote_source.fixture_id
        or candidate.sportybet_event_id != quote_source.event_id
    ):
        return _empty_result(
            candidate=candidate,
            disposition=DirectProviderPriceDisposition.UNPRICED_SOURCE_MISMATCH,
            reason="candidate fixture/event differs from direct-provider quote source",
            now=now,
            kickoff_lead_seconds=kickoff_lead_seconds,
            source_sha=source_sha,
            source_bundle_sha=quote_source.source_bundle_sha256,
            contracts=contracts,
        )
    exact = tuple(
        item
        for item in quote_source.quotes
        if item.fixture_id == candidate.fixture_id
        and item.event_id == candidate.sportybet_event_id
        and item.canonical_market_id is candidate.market_id
        and item.canonical_outcome_id is candidate.outcome_id
        and item.canonical_line == candidate.line
    )
    if not exact:
        return _empty_result(
            candidate=candidate,
            disposition=DirectProviderPriceDisposition.UNPRICED_NO_EXACT_QUOTE,
            reason="no exact current direct-provider fixture/event/market/outcome/line quote",
            now=now,
            kickoff_lead_seconds=kickoff_lead_seconds,
            source_sha=source_sha,
            source_bundle_sha=quote_source.source_bundle_sha256,
            contracts=contracts,
        )
    if len(exact) != 1:
        return _empty_result(
            candidate=candidate,
            disposition=DirectProviderPriceDisposition.UNPRICED_AMBIGUOUS_QUOTE,
            reason="duplicate exact current direct-provider quote",
            now=now,
            kickoff_lead_seconds=kickoff_lead_seconds,
            source_sha=source_sha,
            source_bundle_sha=quote_source.source_bundle_sha256,
            contracts=contracts,
        )
    quote = exact[0]
    quote_age = (now - quote.observed_at).total_seconds()
    if (
        quote.observed_at != quote_source.source_observed_at
        or quote.source_bundle_sha256 != quote_source.source_bundle_sha256
    ):
        raise PriceAllV2DirectProviderError(
            "direct-provider quote ancestry differs from verified quote source"
        )
    if not math.isclose(quote_age, source_age_seconds, abs_tol=1e-9, rel_tol=0):
        raise PriceAllV2DirectProviderError(
            "direct-provider quote/source observation age mismatch"
        )
    if quote_age > max_quote_age_seconds:
        return _empty_result(
            candidate=candidate,
            disposition=DirectProviderPriceDisposition.UNPRICED_STALE_QUOTE,
            reason="direct-provider quote exceeds Price-all v2 freshness policy",
            now=now,
            kickoff_lead_seconds=kickoff_lead_seconds,
            source_sha=source_sha,
            source_bundle_sha=quote_source.source_bundle_sha256,
            contracts=contracts,
            quote=quote,
            quote_age_seconds=quote_age,
        )
    if kickoff_lead_seconds <= minimum_lead_seconds:
        return _empty_result(
            candidate=candidate,
            disposition=DirectProviderPriceDisposition.UNPRICED_NEAR_KICKOFF,
            reason="direct-provider quote is too close to kickoff at Price-all v2 evaluation",
            now=now,
            kickoff_lead_seconds=kickoff_lead_seconds,
            source_sha=source_sha,
            source_bundle_sha=quote_source.source_bundle_sha256,
            contracts=contracts,
            quote=quote,
            quote_age_seconds=quote_age,
        )
    if (
        quote.settlement_equivalence_authority
        is SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN
    ):
        return _empty_result(
            candidate=candidate,
            disposition=DirectProviderPriceDisposition.UNPRICED_SETTLEMENT_EQUIVALENCE_UNPROVEN,
            reason="reviewed settlement equivalence is absent",
            now=now,
            kickoff_lead_seconds=kickoff_lead_seconds,
            source_sha=source_sha,
            source_bundle_sha=quote_source.source_bundle_sha256,
            contracts=contracts,
            quote=quote,
            quote_age_seconds=quote_age,
        )
    try:
        returns, ev = _settlement_ev(candidate, quote.decimal_odds)
    except PriceAllV2DirectProviderError:
        return _empty_result(
            candidate=candidate,
            disposition=DirectProviderPriceDisposition.BLOCKED_SETTLEMENT_DISTRIBUTION_INCOMPLETE,
            reason="full settlement probability representation is required",
            now=now,
            kickoff_lead_seconds=kickoff_lead_seconds,
            source_sha=source_sha,
            source_bundle_sha=quote_source.source_bundle_sha256,
            contracts=contracts,
            quote=quote,
            quote_age_seconds=quote_age,
        )
    devig, overround, fair = _partition_quotes(
        candidate, quote, quote_source.quotes
    )
    value = object.__new__(PriceAllV2DirectProviderResult)
    return _set_frozen(
        value,
        {
            "candidate": candidate,
            "disposition": DirectProviderPriceDisposition.PRICED,
            "reason": (
                "exact verified current direct-provider quote priced without "
                "routing or selection"
            ),
            "quote": quote,
            "evaluation_time": now,
            "quote_age_seconds": quote_age,
            "kickoff_lead_seconds": kickoff_lead_seconds,
            "raw_implied_probability": 1.0 / quote.decimal_odds,
            "devig_status": devig,
            "devig_method": (
                "PROPORTIONAL_MULTIPLICATIVE" if fair is not None else None
            ),
            "overround": overround,
            "fair_probability": fair,
            "settlement_returns": returns,
            "expected_return_multiplier": 1.0 + ev,
            "net_expected_value": ev,
            "ev_percentage": ev * 100.0,
            "source_quote_source_sha256": source_sha,
            "source_bundle_sha256": quote_source.source_bundle_sha256,
            "adapter_contract_sha256": contracts[
                "source_adapter_contract_sha256"
            ],
            "legacy_price_all_v1_contract_sha256": contracts[
                "legacy_price_all_v1_contract_sha256"
            ],
            "price_all_v2_contract_sha256": contracts[
                "price_all_v2_contract_sha256"
            ],
        },
    )


def price_all_direct_provider_candidates(
    candidates: Iterable[CalibratedValueCandidate],
    quote_source: adapter.SportyBetDirectProviderPriceAllQuoteSource,
    *,
    evaluation_time: datetime,
    max_quote_age_seconds: int = DEFAULT_MAX_QUOTE_AGE_SECONDS,
    minimum_lead_seconds: int = DEFAULT_MINIMUM_LEAD_SECONDS,
) -> PriceAllV2DirectProviderEvaluation:
    """Price every candidate from one exact verified current direct-provider source."""
    contracts = validate_price_all_v2_contract()
    now = _utc(evaluation_time, "evaluation_time")
    if (
        type(max_quote_age_seconds) is not int
        or max_quote_age_seconds < 0
        or max_quote_age_seconds > DEFAULT_MAX_QUOTE_AGE_SECONDS
    ):
        raise PriceAllV2DirectProviderError(
            "max_quote_age_seconds must be an integer in the reviewed 0..900 range"
        )
    if (
        type(minimum_lead_seconds) is not int
        or minimum_lead_seconds < DEFAULT_MINIMUM_LEAD_SECONDS
    ):
        raise PriceAllV2DirectProviderError(
            "minimum_lead_seconds cannot weaken the reviewed 120-second floor"
        )
    if type(quote_source) is not adapter.SportyBetDirectProviderPriceAllQuoteSource:
        raise PriceAllV2DirectProviderError(
            "quote_source must be exact direct-provider Price-all adapter output"
        )
    try:
        verified = adapter.verify_direct_provider_price_all_quote_source(quote_source)
    except adapter.SportyBetPriceAllDirectProviderQuoteAdapterError as exc:
        raise PriceAllV2DirectProviderError(
            "direct-provider quote source reconstruction failed"
        ) from exc
    if (
        verified.dataset_name != adapter.DATASET_NAME
        or verified.status != adapter.STATUS
        or verified.next_boundary != adapter.NEXT_BOUNDARY
    ):
        raise PriceAllV2DirectProviderError(
            "direct-provider quote source state is not approved for Price-all v2"
        )
    if (
        verified.authority.get("direct_provider_quote_source_adaptation") is not True
        or verified.authority.get("source_live_current_issuance_required") is not True
        or verified.authority.get("legacy_price_all_v1_consumption_authorized") is not False
        or verified.authority.get("price_all_value_computation") is not False
        or verified.authority.get("bet") is not False
    ):
        raise PriceAllV2DirectProviderError(
            "direct-provider quote source authority flags mismatch"
        )
    source_eval = _utc(verified.source_evaluation_time, "source_evaluation_time")
    source_observed = _utc(verified.source_observed_at, "source_observed_at")
    if now < source_eval:
        raise PriceAllV2DirectProviderError(
            "evaluation_time predates current direct-provider source issuance"
        )
    source_age = (now - source_observed).total_seconds()
    if not math.isfinite(source_age) or source_age < 0:
        raise PriceAllV2DirectProviderError(
            "current direct-provider source observation is future-dated"
        )
    source_bundle = verified._source_bundle
    kickoff = _utc(source_bundle.kickoff_utc, "kickoff_utc")
    kickoff_lead = (kickoff - now).total_seconds()
    if not math.isfinite(kickoff_lead):
        raise PriceAllV2DirectProviderError("kickoff lead is invalid")
    candidate_values = tuple(candidates)
    if any(type(item) is not CalibratedValueCandidate for item in candidate_values):
        raise PriceAllV2DirectProviderError(
            "candidates must be exact Phase 6 calibrated value candidates"
        )
    if len({item.candidate_id for item in candidate_values}) != len(candidate_values):
        raise PriceAllV2DirectProviderError("candidate_id must be unique")
    if len({item.quote_identity for item in verified.quotes}) != len(verified.quotes):
        raise PriceAllV2DirectProviderError(
            "direct-provider quote identities must be unique"
        )
    source_sha = verified.canonical_sha256
    results = tuple(
        _price_one(
            candidate=item,
            quote_source=verified,
            now=now,
            source_age_seconds=source_age,
            kickoff_lead_seconds=kickoff_lead,
            max_quote_age_seconds=max_quote_age_seconds,
            minimum_lead_seconds=minimum_lead_seconds,
            contracts=contracts,
            source_sha=source_sha,
        )
        for item in sorted(candidate_values, key=lambda value: value.candidate_id)
    )
    value = object.__new__(PriceAllV2DirectProviderEvaluation)
    return _set_frozen(
        value,
        {
            "dataset_name": DATASET_NAME,
            "status": STATUS,
            "fixture_id": verified.fixture_id,
            "event_id": verified.event_id,
            "evaluation_time": now,
            "source_observed_at": source_observed,
            "source_evaluation_time": source_eval,
            "kickoff_utc": kickoff,
            "quote_age_seconds": source_age,
            "kickoff_lead_seconds": kickoff_lead,
            "max_quote_age_seconds": max_quote_age_seconds,
            "minimum_lead_seconds": minimum_lead_seconds,
            "source_quote_source_sha256": source_sha,
            "source_bundle_sha256": verified.source_bundle_sha256,
            "source_adapter_contract_sha256": contracts[
                "source_adapter_contract_sha256"
            ],
            "legacy_price_all_v1_contract_sha256": contracts[
                "legacy_price_all_v1_contract_sha256"
            ],
            "price_all_v2_contract_sha256": contracts[
                "price_all_v2_contract_sha256"
            ],
            "results": results,
            "mapping_audits": tuple(verified.mapping_audits),
            "authority": types.MappingProxyType(dict(_AUTHORITY)),
            "next_boundary": NEXT_BOUNDARY,
            "_candidates": candidate_values,
            "_quote_source": verified,
        },
    )


def verify_price_all_v2_direct_provider_evaluation(
    value: PriceAllV2DirectProviderEvaluation,
) -> PriceAllV2DirectProviderEvaluation:
    """Rebuild an evaluation from its exact retained candidate/source ancestry."""
    if type(value) is not PriceAllV2DirectProviderEvaluation:
        raise PriceAllV2DirectProviderError(
            "value must be exact PriceAllV2DirectProviderEvaluation"
        )
    rebuilt = price_all_direct_provider_candidates(
        value._candidates,
        value._quote_source,
        evaluation_time=value.evaluation_time,
        max_quote_age_seconds=value.max_quote_age_seconds,
        minimum_lead_seconds=value.minimum_lead_seconds,
    )
    if rebuilt.to_dict() != value.to_dict():
        raise PriceAllV2DirectProviderError(
            "Price-all v2 evaluation differs from exact source reconstruction"
        )
    return rebuilt


__all__ = [name for name in globals() if not name.startswith("_")]
