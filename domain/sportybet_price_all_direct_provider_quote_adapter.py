"""Reviewed adapter from PR246 live SportyBet evidence to a Price-all v2 quote source.

This boundary deliberately does not mutate or reinterpret the frozen Phase 7 v1
quote-source contract.  Phase 7 v1 remains bound to user-controlled SportyBet
Lite HTML ancestry.  The objects issued here preserve the direct-provider
FactsCenter ancestry from ``sportybet_live_event_quote_evidence`` so a later
Price-all v2 boundary can consume it explicitly.

No object issued here computes value, routes a market, selects a leg, constructs
an accumulator, generates a SportyBet code, stakes, or places a wager.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import types
from typing import Any, Mapping

from domain import sportybet_live_event_quote_evidence as live
from domain._price_all_contracts import validate_price_all_contract
from domain.markets import MarketId, OutcomeId, validate_selection
from domain.sportybet_reviewed_canonical_market_mapping import (
    SettlementEquivalenceAuthority,
    SportyBetReviewedCanonicalMarketMapping,
    canonical_mapping_sha256,
)


SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-sportybet-price-all-direct-provider-quote-source-adapter-v1"
STATUS = "DIRECT_PROVIDER_PRICE_ALL_QUOTE_SOURCE_ADAPTER_VERIFIED"
SOURCE = "SportyBet"
NEXT_BOUNDARY = "PRICE_ALL_V2_DIRECT_PROVIDER_QUOTE_CONSUMPTION_REQUIRED"
LEGACY_PRICE_ALL_V1_CONTRACT_SHA256 = (
    "1fb0a6c891adccd76b4864a6197e55d22154176a4191f57ce92cde13501535aa"
)
EXPECTED_CONTRACT_SHA256 = (
    "6813c74ca286f139f5cb0ac40a78147fd3762d76ca1e637aa0b7d6c5282bc903"
)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

_AUTHORITY = types.MappingProxyType(
    {
        "direct_provider_quote_source_adaptation": True,
        "source_live_current_issuance_required": True,
        "reviewed_mapping_rebind_required": True,
        "legacy_price_all_v1_consumption_authorized": False,
        "price_all_value_computation": False,
        "market_router": False,
        "final_selection": False,
        "accumulator": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
    }
)

_QUOTE_IDENTITY_FIELDS = (
    "fixture_id",
    "event_id",
    "provider_market_id",
    "provider_specifier",
    "provider_outcome_id",
    "canonical_market_id",
    "canonical_outcome_id",
    "canonical_line",
    "live_inventory_sha256",
)


class SportyBetPriceAllDirectProviderQuoteAdapterError(ValueError):
    """Raised when direct-provider quote-source adaptation fails closed."""


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
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "canonical JSON serialization failed"
        ) from exc


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            f"{label} must be an exact SHA-256"
        )
    return value


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            f"{label} must be timezone-aware"
        )
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            f"{label} is invalid"
        ) from exc


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "source_dataset_name": live.MAPPED_QUOTE_DATASET_NAME,
        "source_live_status": live.LIVE_STATUS,
        "source_live_proof_mode": live.LIVE_PROOF_MODE,
        "source_observation_authority": live.OBSERVATION_AUTHORITY,
        "source_direct_event_contract_sha256": live.EXPECTED_CONTRACT_SHA256,
        "legacy_price_all_v1_contract_sha256": LEGACY_PRICE_ALL_V1_CONTRACT_SHA256,
        "legacy_price_all_v1_direct_provider_consumption_authorized": False,
        "quote_identity_fields": list(_QUOTE_IDENTITY_FIELDS),
        "freshness_authority": (
            "PRESERVE_SOURCE_OBSERVED_AT_AND_LIVE_ISSUANCE_PROOF_"
            "PRICE_ALL_MUST_RECHECK_AGE"
        ),
        "provider_quote_timestamp": None,
        "provider_snapshot_id": None,
        "next_boundary": NEXT_BOUNDARY,
        "authority": dict(_AUTHORITY),
    }


def calculate_adapter_contract_sha256() -> str:
    return hashlib.sha256(
        _canonical_bytes(
            {"version": CONTRACT_VERSION, "semantics": _contract_payload()}
        )
    ).hexdigest()


def validate_adapter_contract() -> Mapping[str, str]:
    direct = live.validate_direct_event_source_contract()
    if direct["contract_sha256"] != live.EXPECTED_CONTRACT_SHA256:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "direct-provider source contract identity drifted"
        )
    price_all = validate_price_all_contract()
    if price_all["price_all_contract_sha256"] != LEGACY_PRICE_ALL_V1_CONTRACT_SHA256:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "legacy Price-all v1 identity drifted"
        )
    actual = calculate_adapter_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "direct-provider Price-all quote adapter contract drifted"
        )
    return types.MappingProxyType(
        {
            "adapter_contract_sha256": actual,
            "direct_event_contract_sha256": direct["contract_sha256"],
            "legacy_price_all_v1_contract_sha256": price_all[
                "price_all_contract_sha256"
            ],
        }
    )


@dataclass(frozen=True, init=False)
class SportyBetDirectProviderPriceAllQuote:
    fixture_id: str
    event_id: str
    provider_market_id: str
    provider_outcome_id: str
    provider_specifier: str | None
    canonical_market_id: MarketId
    canonical_outcome_id: OutcomeId
    canonical_line: float | None
    source: str
    source_method: str
    live_inventory_sha256: str
    source_bundle_sha256: str
    source_manifest_sha256: str
    source_raw_sha256: str
    reviewed_mapping_sha256: str
    fixture_reconciliation_sha256: str
    observed_at: datetime
    observation_authority: str
    provider_quote_at: None
    provider_snapshot_id: None
    odds_raw: str
    decimal_odds: float
    settlement_equivalence_authority: SettlementEquivalenceAuthority

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "direct-provider Price-all quotes are issued only by verified adaptation"
        )

    @property
    def quote_identity(self) -> tuple[Any, ...]:
        return (
            self.fixture_id,
            self.event_id,
            self.provider_market_id,
            self.provider_specifier,
            self.provider_outcome_id,
            self.canonical_market_id,
            self.canonical_outcome_id,
            self.canonical_line,
            self.live_inventory_sha256,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "provider_market_id": self.provider_market_id,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_specifier": self.provider_specifier,
            "canonical_market_id": self.canonical_market_id.value,
            "canonical_outcome_id": self.canonical_outcome_id.value,
            "canonical_line": self.canonical_line,
            "source": self.source,
            "source_method": self.source_method,
            "live_inventory_sha256": self.live_inventory_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "reviewed_mapping_sha256": self.reviewed_mapping_sha256,
            "fixture_reconciliation_sha256": self.fixture_reconciliation_sha256,
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
            "observation_authority": self.observation_authority,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "odds_raw": self.odds_raw,
            "decimal_odds": self.decimal_odds,
            "settlement_equivalence_authority": (
                self.settlement_equivalence_authority.value
            ),
        }


@dataclass(frozen=True, init=False)
class SportyBetDirectProviderPriceAllQuoteSource:
    dataset_name: str
    status: str
    event_id: str
    fixture_id: str
    source_observed_at: datetime
    source_evaluation_time: datetime
    source_bundle_sha256: str
    direct_event_contract_sha256: str
    adapter_contract_sha256: str
    legacy_price_all_v1_contract_sha256: str
    quotes: tuple[SportyBetDirectProviderPriceAllQuote, ...]
    mapping_audits: tuple[live.SportyBetLiveMappingAudit, ...]
    authority: Mapping[str, bool]
    next_boundary: str
    _source_bundle: live.SportyBetLiveMappedQuoteBundle

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "direct-provider Price-all quote sources are issued only by verified adaptation"
        )

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "status": self.status,
            "event_id": self.event_id,
            "fixture_id": self.fixture_id,
            "source_observed_at": self.source_observed_at.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "source_evaluation_time": self.source_evaluation_time.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "source_bundle_sha256": self.source_bundle_sha256,
            "direct_event_contract_sha256": self.direct_event_contract_sha256,
            "adapter_contract_sha256": self.adapter_contract_sha256,
            "legacy_price_all_v1_contract_sha256": (
                self.legacy_price_all_v1_contract_sha256
            ),
            "quote_count": len(self.quotes),
            "quotes": [item.to_dict() for item in self.quotes],
            "mapping_audits": [item.to_dict() for item in self.mapping_audits],
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "wager_placed": False,
        }


def _set_frozen(obj: Any, values: Mapping[str, Any]) -> Any:
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    return obj


def _adapt_quote(
    *,
    quote: live.SportyBetLiveMappedQuote,
    bundle: live.SportyBetLiveMappedQuoteBundle,
    mapping: SportyBetReviewedCanonicalMarketMapping,
) -> SportyBetDirectProviderPriceAllQuote:
    if type(quote) is not live.SportyBetLiveMappedQuote:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "source quote must be an exact verified live mapped quote"
        )
    if (
        quote.fixture_id != bundle.fixture_id
        or quote.event_id != bundle.event_id
        or quote.live_inventory_sha256 != bundle.live_inventory_sha256
        or quote.reviewed_mapping_sha256 != bundle.reviewed_mapping_sha256
        or quote.observed_at != bundle.observed_at
    ):
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "live quote ancestry differs from verified source bundle"
        )
    if quote.observation_authority != live.OBSERVATION_AUTHORITY:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "live quote observation authority mismatch"
        )
    if quote.provider_quote_at is not None or quote.provider_snapshot_id is not None:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "provider quote timestamp/snapshot identity remains unproven"
        )
    market, outcome, line = validate_selection(
        quote.canonical_market_id,
        quote.canonical_outcome_id,
        quote.canonical_line,
    )
    try:
        settlement = SettlementEquivalenceAuthority(
            quote.settlement_equivalence_authority
        )
    except ValueError as exc:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "settlement equivalence authority is invalid"
        ) from exc
    if settlement is SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "direct-provider quote lacks reviewed settlement equivalence"
        )
    if type(quote.odds_raw) is not str or not quote.odds_raw:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "direct-provider odds_raw is invalid"
        )
    try:
        odds = float(quote.odds_raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "direct-provider odds are invalid"
        ) from exc
    if (
        not math.isfinite(odds)
        or odds <= 1.0
        or not math.isfinite(quote.decimal_odds)
        or quote.decimal_odds != odds
    ):
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "direct-provider odds identity mismatch"
        )
    value = object.__new__(SportyBetDirectProviderPriceAllQuote)
    return _set_frozen(
        value,
        {
            "fixture_id": quote.fixture_id,
            "event_id": quote.event_id,
            "provider_market_id": quote.provider_market_id,
            "provider_outcome_id": quote.provider_outcome_id,
            "provider_specifier": quote.provider_specifier,
            "canonical_market_id": market,
            "canonical_outcome_id": outcome,
            "canonical_line": line,
            "source": SOURCE,
            "source_method": live.SOURCE_METHOD,
            "live_inventory_sha256": _sha(
                quote.live_inventory_sha256, "live_inventory_sha256"
            ),
            "source_bundle_sha256": bundle.canonical_sha256,
            "source_manifest_sha256": _sha(
                quote.source_manifest_sha256, "source_manifest_sha256"
            ),
            "source_raw_sha256": _sha(quote.source_raw_sha256, "source_raw_sha256"),
            "reviewed_mapping_sha256": _sha(
                quote.reviewed_mapping_sha256, "reviewed_mapping_sha256"
            ),
            "fixture_reconciliation_sha256": _sha(
                mapping.source_reconciliation_receipt_sha256,
                "fixture_reconciliation_sha256",
            ),
            "observed_at": _utc(quote.observed_at, "observed_at"),
            "observation_authority": live.OBSERVATION_AUTHORITY,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "odds_raw": quote.odds_raw,
            "decimal_odds": quote.decimal_odds,
            "settlement_equivalence_authority": settlement,
        },
    )


def adapt_current_live_quote_bundle(
    bundle: live.SportyBetLiveMappedQuoteBundle,
) -> SportyBetDirectProviderPriceAllQuoteSource:
    """Adapt an exact PR246 LIVE_CURRENT bundle without granting Phase 7 v1 use."""
    contracts = validate_adapter_contract()
    if type(bundle) is not live.SportyBetLiveMappedQuoteBundle:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "source bundle must be exact SportyBetLiveMappedQuoteBundle"
        )
    try:
        verified = live.verify_mapped_quote_bundle(bundle)
    except live.SportyBetLiveEventQuoteEvidenceError as exc:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "live mapped quote source replay verification failed"
        ) from exc
    if (
        verified.dataset_name != live.MAPPED_QUOTE_DATASET_NAME
        or verified.status != live.LIVE_STATUS
        or verified.proof_mode != live.LIVE_PROOF_MODE
        or verified.next_boundary != live.NEXT_BOUNDARY
    ):
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "adapter requires exact PR246 LIVE_CURRENT source state"
        )
    if (
        verified.authority.get("current_observation_freshness_proven") is not True
        or verified.authority.get("reviewed_mapping_rebind") is not True
        or verified.authority.get("price_all") is not False
        or verified.authority.get("bet") is not False
    ):
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "live source authority flags do not match reviewed adapter boundary"
        )
    mapping = verified._mapping
    if type(mapping) is not SportyBetReviewedCanonicalMarketMapping:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "verified bundle retained mapping type is invalid"
        )
    mapping_sha = canonical_mapping_sha256(mapping)
    if (
        mapping_sha != verified.reviewed_mapping_sha256
        or mapping.sportybet_event_id != verified.event_id
        or mapping.matched_fotmob_fixture_id != verified.fixture_id
    ):
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "verified bundle mapping ancestry mismatch"
        )
    quotes = tuple(
        sorted(
            (
                _adapt_quote(quote=item, bundle=verified, mapping=mapping)
                for item in verified.quotes
            ),
            key=lambda item: (
                item.canonical_market_id.value,
                "" if item.canonical_line is None else str(item.canonical_line),
                item.canonical_outcome_id.value,
                item.provider_market_id,
                item.provider_outcome_id,
            ),
        )
    )
    if len({item.quote_identity for item in quotes}) != len(quotes):
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "adapted quote identities are not unique"
        )
    value = object.__new__(SportyBetDirectProviderPriceAllQuoteSource)
    return _set_frozen(
        value,
        {
            "dataset_name": DATASET_NAME,
            "status": STATUS,
            "event_id": verified.event_id,
            "fixture_id": verified.fixture_id,
            "source_observed_at": _utc(verified.observed_at, "source_observed_at"),
            "source_evaluation_time": _utc(
                verified.evaluation_time, "source_evaluation_time"
            ),
            "source_bundle_sha256": verified.canonical_sha256,
            "direct_event_contract_sha256": contracts[
                "direct_event_contract_sha256"
            ],
            "adapter_contract_sha256": contracts["adapter_contract_sha256"],
            "legacy_price_all_v1_contract_sha256": contracts[
                "legacy_price_all_v1_contract_sha256"
            ],
            "quotes": quotes,
            "mapping_audits": tuple(verified.mapping_audits),
            "authority": types.MappingProxyType(dict(_AUTHORITY)),
            "next_boundary": NEXT_BOUNDARY,
            "_source_bundle": verified,
        },
    )


def verify_direct_provider_price_all_quote_source(
    value: SportyBetDirectProviderPriceAllQuoteSource,
) -> SportyBetDirectProviderPriceAllQuoteSource:
    """Rebuild the adapter output from its retained exact PR246 source bundle."""
    if type(value) is not SportyBetDirectProviderPriceAllQuoteSource:
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "value must be exact SportyBetDirectProviderPriceAllQuoteSource"
        )
    rebuilt = adapt_current_live_quote_bundle(value._source_bundle)
    if rebuilt.to_dict() != value.to_dict():
        raise SportyBetPriceAllDirectProviderQuoteAdapterError(
            "adapted quote source differs from exact source reconstruction"
        )
    return rebuilt


__all__ = [name for name in globals() if not name.startswith("_")]
