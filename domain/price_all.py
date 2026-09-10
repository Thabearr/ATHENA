"""Canonical ATHENA Price-all interface.

P1.3 promotes the reviewed current-provider Price-all v3 semantics behind the
unversioned ``domain.price_all`` boundary.  This module deliberately delegates
the pricing implementation to ``price_all_v3_current_provider`` during the
migration window; it does not copy or alter quote matching, freshness, de-vig,
settlement-return, or expected-value mathematics.

The public canonical wrappers preserve the v3 canonical payload byte-for-byte
so replay parity is directly auditable.  They grant no routing, portfolio,
SportyBet execution, staking, or wager authority.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
import enum
import hashlib
import json
import types
from typing import Any

from domain import price_all_v3_current_provider as _v3
from domain._price_all_contracts import CalibratedValueCandidate
from domain.current_direct_provider_live_quote_mapping_consumption import (
    CurrentDirectProviderMappedQuoteBundle,
)


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CANONICAL_PRICE_ALL_V1"
IMPLEMENTATION_ID = "domain.price_all_v3_current_provider"
IMPLEMENTATION_CONTRACT_SHA256 = _v3.EXPECTED_CONTRACT_SHA256
SOURCE_CONTRACT_SHA256 = _v3.PR253_CONTRACT_SHA256
FROZEN_V2_CONTRACT_SHA256 = _v3.PRICE_ALL_V2_CONTRACT_SHA256
DEFAULT_MAX_QUOTE_AGE_SECONDS = _v3.DEFAULT_MAX_QUOTE_AGE_SECONDS
DEFAULT_MINIMUM_LEAD_SECONDS = _v3.DEFAULT_MINIMUM_LEAD_SECONDS
AS_OF_REPLAY = _v3.AS_OF_REPLAY
LIVE_CURRENT = _v3.LIVE_CURRENT

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


class PriceAllError(ValueError):
    """Canonical Price-all rejected an input or delegated replay."""


class PriceDisposition(str, enum.Enum):
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


def canonical_json_bytes(value: Any) -> bytes:
    """Return the exact compact canonical JSON bytes used by the promoted v3.

    P1.3 intentionally preserves v3 serialization semantics so the canonical
    and v3 outputs can be compared byte-for-byte on the replay corpus.
    """
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise PriceAllError("canonical JSON serialization failed") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _delegate_error(exc: Exception) -> PriceAllError:
    return PriceAllError(str(exc))


def _require_exact_v3_dispositions() -> None:
    canonical = tuple(item.value for item in PriceDisposition)
    implementation = tuple(item.value for item in _v3.CurrentProviderPriceDisposition)
    if canonical != implementation:
        raise PriceAllError("canonical Price-all disposition vocabulary drifted from v3")


def validate_price_all_contract() -> Mapping[str, Any]:
    """Validate the canonical ownership boundary and exact delegated contracts."""
    _require_exact_v3_dispositions()
    try:
        identities = _v3.validate_price_all_v3_contract()
    except _v3.PriceAllV3CurrentProviderError as exc:
        raise _delegate_error(exc) from exc
    if identities.get("price_all_v3_contract_sha256") != IMPLEMENTATION_CONTRACT_SHA256:
        raise PriceAllError("delegated Price-all v3 contract identity drifted")
    if identities.get("pr253_contract_sha256") != SOURCE_CONTRACT_SHA256:
        raise PriceAllError("delegated current-provider source contract identity drifted")
    if identities.get("price_all_v2_contract_sha256") != FROZEN_V2_CONTRACT_SHA256:
        raise PriceAllError("delegated frozen Price-all v2 contract identity drifted")
    return types.MappingProxyType(
        {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "implementation_id": IMPLEMENTATION_ID,
            "implementation_contract_sha256": IMPLEMENTATION_CONTRACT_SHA256,
            "source_contract_sha256": SOURCE_CONTRACT_SHA256,
            "frozen_v2_contract_sha256": FROZEN_V2_CONTRACT_SHA256,
            "authority": types.MappingProxyType(dict(_AUTHORITY)),
        }
    )


class PriceAllResult:
    """Immutable canonical view of one exact delegated v3 pricing result."""

    __slots__ = ("_delegate",)

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise PriceAllError("canonical PriceAllResult is builder-only")

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise AttributeError("canonical PriceAllResult is immutable")

    @classmethod
    def _from_v3(cls, value: Any) -> "PriceAllResult":
        if type(value) is not _v3.PriceAllV3CurrentProviderResult:
            raise PriceAllError("result delegate must be exact Price-all v3 result")
        result = object.__new__(cls)
        object.__setattr__(result, "_delegate", value)
        return result

    @property
    def disposition(self) -> PriceDisposition:
        return PriceDisposition(self._delegate.disposition.value)

    @property
    def canonical_sha256(self) -> str:
        return canonical_sha256(self)

    def to_dict(self) -> dict[str, Any]:
        return self._delegate.to_dict()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._delegate, name)


class PriceAllEvaluation:
    """Immutable canonical view of an exact delegated v3 Price-all evaluation."""

    __slots__ = ("_delegate", "_results")

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise PriceAllError("canonical PriceAllEvaluation is builder-only")

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise AttributeError("canonical PriceAllEvaluation is immutable")

    @classmethod
    def _from_v3(cls, value: Any) -> "PriceAllEvaluation":
        if type(value) is not _v3.PriceAllV3CurrentProviderEvaluation:
            raise PriceAllError("evaluation delegate must be exact Price-all v3 evaluation")
        result = object.__new__(cls)
        object.__setattr__(result, "_delegate", value)
        object.__setattr__(
            result,
            "_results",
            tuple(PriceAllResult._from_v3(item) for item in value.results),
        )
        return result

    @property
    def results(self) -> tuple[PriceAllResult, ...]:
        return self._results

    @property
    def authority(self) -> Mapping[str, bool]:
        return types.MappingProxyType(dict(self._delegate.authority))

    @property
    def canonical_sha256(self) -> str:
        return canonical_sha256(self)

    def to_dict(self) -> dict[str, Any]:
        # Exact output parity is the P1.3 promotion gate.  Do not add wrapper
        # metadata to the pricing evidence payload.
        return self._delegate.to_dict()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._delegate, name)


def _wrap(value: Any) -> PriceAllEvaluation:
    _require_exact_v3_dispositions()
    return PriceAllEvaluation._from_v3(value)


def price_all_as_of(
    candidates: Iterable[CalibratedValueCandidate],
    source_bundle: CurrentDirectProviderMappedQuoteBundle,
    *,
    evaluation_time: datetime,
    max_quote_age_seconds: int = DEFAULT_MAX_QUOTE_AGE_SECONDS,
    minimum_lead_seconds: int = DEFAULT_MINIMUM_LEAD_SECONDS,
) -> PriceAllEvaluation:
    """Deterministic canonical replay lane backed by exact v3 source replay."""
    validate_price_all_contract()
    try:
        value = _v3.price_all_current_provider_candidates_as_of(
            candidates,
            source_bundle,
            evaluation_time=evaluation_time,
            max_quote_age_seconds=max_quote_age_seconds,
            minimum_lead_seconds=minimum_lead_seconds,
        )
    except _v3.PriceAllV3CurrentProviderError as exc:
        raise _delegate_error(exc) from exc
    return _wrap(value)


def price_all_current(
    candidates: Iterable[CalibratedValueCandidate],
    source_bundle: CurrentDirectProviderMappedQuoteBundle,
    *,
    max_quote_age_seconds: int = DEFAULT_MAX_QUOTE_AGE_SECONDS,
    minimum_lead_seconds: int = DEFAULT_MINIMUM_LEAD_SECONDS,
) -> PriceAllEvaluation:
    """Canonical current lane; wall-clock freshness remains owned by v3.

    There is deliberately no caller-supplied evaluation timestamp in this
    interface.  The delegated v3 current lane acquires the wall clock and
    requires an exact LIVE_CURRENT source before issuing an evaluation.
    """
    validate_price_all_contract()
    try:
        value = _v3.price_all_current_provider_candidates(
            candidates,
            source_bundle,
            max_quote_age_seconds=max_quote_age_seconds,
            minimum_lead_seconds=minimum_lead_seconds,
        )
    except _v3.PriceAllV3CurrentProviderError as exc:
        raise _delegate_error(exc) from exc
    return _wrap(value)


def verify_price_all_evaluation(value: Any) -> PriceAllEvaluation:
    """Replay the exact delegated source and require byte-identical output."""
    if type(value) is not PriceAllEvaluation:
        raise PriceAllError("value must be exact canonical PriceAllEvaluation")
    validate_price_all_contract()
    try:
        rebuilt = _v3.verify_price_all_v3_current_provider_evaluation(value._delegate)
    except _v3.PriceAllV3CurrentProviderError as exc:
        raise _delegate_error(exc) from exc
    wrapped = _wrap(rebuilt)
    if canonical_json_bytes(wrapped) != canonical_json_bytes(value):
        raise PriceAllError("canonical Price-all evaluation differs on exact v3 replay")
    return wrapped


def unwrap_v3_evaluation(value: Any) -> _v3.PriceAllV3CurrentProviderEvaluation:
    """Temporary one-way migration adapter for reviewed v3 router callers.

    This does not grant the v3 router canonical ownership.  P1.4 owns the
    router/coherence promotion and may use this adapter only while preserving
    exact replay parity.
    """
    verified = verify_price_all_evaluation(value)
    return verified._delegate


__all__ = [
    "AS_OF_REPLAY",
    "DEFAULT_MAX_QUOTE_AGE_SECONDS",
    "DEFAULT_MINIMUM_LEAD_SECONDS",
    "FROZEN_V2_CONTRACT_SHA256",
    "IMPLEMENTATION_CONTRACT_SHA256",
    "IMPLEMENTATION_ID",
    "LIVE_CURRENT",
    "POLICY_ID",
    "PriceAllError",
    "PriceAllEvaluation",
    "PriceAllResult",
    "PriceDisposition",
    "SCHEMA_VERSION",
    "SOURCE_CONTRACT_SHA256",
    "canonical_json_bytes",
    "canonical_sha256",
    "price_all_as_of",
    "price_all_current",
    "unwrap_v3_evaluation",
    "validate_price_all_contract",
    "verify_price_all_evaluation",
]
