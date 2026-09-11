"""Canonical non-wager SportyBet share-code delivery service (P1.6).

The canonical entrypoint accepts a verified P1.5 ``SelectedPortfolio`` plus an
exact provider-binding set. It re-resolves semantic intent from SportyBet,
requires the resolved native IDs/odds to equal the selected evidence, performs
the existing anonymous create -> reload round trip, and returns either a
``VerifiedShareCode`` or a typed ``ShareCodeFailure``.

No browser automation, login, cookies, wallet, staking or wagering authority is
introduced here. A temporary Current Shadow compatibility entrypoint keeps the
existing research runner behavior unchanged while routing that caller through
this canonical delivery module; profile-core migration remains a later wave.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import types
from enum import Enum
from typing import Any

from domain import current_sportybet_accumulator_execution as _source
from domain import portfolio_optimizer as _portfolio
from scripts import sportybet_direct_share_bridge as direct_bridge
from scripts import sportybet_semantic_share_bridge as semantic_bridge


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CANONICAL_SPORTYBET_SHARE_CODE_V1"
IMPLEMENTATION_ID = "domain.sportybet_share_code"
OUTPUT_CONTRACT = "VerifiedShareCode|ShareCodeFailure"
CANONICAL_PORTFOLIO_CONTRACT_SHA256 = _portfolio.EXPECTED_CONTRACT_SHA256
SOURCE_EXECUTION_CONTRACT_SHA256 = _source.EXPECTED_CONTRACT_SHA256
SEMANTIC_BRIDGE_SCHEMA = "athena-sportybet-semantic-share-gate-v1"
DIRECT_BRIDGE_SCHEMA = "athena-sportybet-direct-share-proof-v2"
MINIMUM_LEAD_SECONDS = _source.MINIMUM_LEAD_SECONDS
RECEIPT_FILENAME = "sportybet-share-code-receipt.json"

# Compatibility status vocabulary retained for the existing Current Shadow
# receipt mapper. These strings are not the canonical result contract below.
STATUS_CODE_VERIFIED = "RESEARCH_SHADOW_CODE_VERIFIED"
STATUS_CODE_VERIFIED_WITH_SHORTFALL = "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL"
STATUS_REPRICE_REQUIRED = "RESEARCH_NO_CODE_REPRICE_REQUIRED"
STATUS_PROVIDER_CHANGED = "RESEARCH_NO_CODE_PROVIDER_CHANGED"

AUTHORITY = types.MappingProxyType(
    {
        "selected_portfolio_consumption": True,
        "exact_provider_binding_required": True,
        "anonymous_share_code_generation": True,
        "provider_create_reload_verification": True,
        "current_shadow_compatibility_entrypoint": True,
        "football_probability_generation": False,
        "calibration": False,
        "price_all_value_computation": False,
        "market_routing": False,
        "portfolio_optimization": False,
        "provider_semantic_verification": True,
        "source_acquisition": False,
        "browser_automation": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)

_SAFETY_FIELDS = (
    "sportybet_login_used",
    "sportybet_cookie_used",
    "sportybet_wallet_used",
    "stake_submitted",
    "wager_placed",
)


class SportyBetShareCodeError(ValueError):
    """Canonical delivery evidence is invalid or cannot be replayed safely."""


class CurrentShadowAllMarketShareCodeError(SportyBetShareCodeError):
    """Temporary compatibility entrypoint rejected legacy Shadow delivery."""


class ShareCodeFailureCode(str, Enum):
    NO_SELECTED_LEGS = "NO_SELECTED_LEGS"
    REPRICE_REQUIRED = "REPRICE_REQUIRED"
    PROVIDER_CHANGED = "PROVIDER_CHANGED"
    CREATE_RELOAD_FAILED = "CREATE_RELOAD_FAILED"
    VERIFIED_RESPONSE_INCOMPLETE = "VERIFIED_RESPONSE_INCOMPLETE"


def _canonical_bytes(value: Any) -> bytes:
    if hasattr(value, "to_dict") and callable(value.to_dict):
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
        raise SportyBetShareCodeError("canonical serialization failed") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise SportyBetShareCodeError(f"{label} must be timezone-aware")
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetShareCodeError(f"{label} is invalid") from exc


def _iso(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace("+00:00", "Z")


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "implementation_id": IMPLEMENTATION_ID,
        "output_contract": OUTPUT_CONTRACT,
        "canonical_portfolio_contract_sha256": CANONICAL_PORTFOLIO_CONTRACT_SHA256,
        "source_execution_contract_sha256": SOURCE_EXECUTION_CONTRACT_SHA256,
        "semantic_bridge_schema": SEMANTIC_BRIDGE_SCHEMA,
        "direct_bridge_schema": DIRECT_BRIDGE_SCHEMA,
        "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
        "shortfall_can_still_verify": True,
        "provider_native_ids_are_verification_not_caller_authority": True,
        "authority": dict(AUTHORITY),
    }


def calculate_share_code_contract_sha256() -> str:
    return _sha(_contract_payload())


EXPECTED_CONTRACT_SHA256 = "f324076f377340b30c10fcc13a166655f27ac427b162d0a4ee318661bc71f1d9"


def _assert_non_wager_authority() -> None:
    required_true = (
        "selected_portfolio_consumption",
        "exact_provider_binding_required",
        "anonymous_share_code_generation",
        "provider_create_reload_verification",
        "provider_semantic_verification",
    )
    required_false = (
        "source_acquisition",
        "browser_automation",
        "login",
        "cookies",
        "wallet",
        "staking",
        "bet",
        "wager_placed",
    )
    if any(AUTHORITY[key] is not True for key in required_true):
        raise SportyBetShareCodeError("canonical share-code positive authority drifted")
    if any(AUTHORITY[key] is not False for key in required_false):
        raise SportyBetShareCodeError("canonical share-code non-wager authority drifted")


def validate_share_code_contract() -> Mapping[str, str]:
    try:
        portfolio = _portfolio.validate_portfolio_contract()
        source = _source.validate_current_execution_contract()
    except Exception as exc:
        raise SportyBetShareCodeError("share-code dependency validation failed") from exc
    if portfolio["canonical_portfolio_contract_sha256"] != CANONICAL_PORTFOLIO_CONTRACT_SHA256:
        raise SportyBetShareCodeError("canonical Portfolio contract identity drifted")
    if source["current_execution_contract_sha256"] != SOURCE_EXECUTION_CONTRACT_SHA256:
        raise SportyBetShareCodeError("reviewed create/reload source contract identity drifted")
    _assert_non_wager_authority()
    actual = calculate_share_code_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise SportyBetShareCodeError("canonical share-code contract drifted")
    return types.MappingProxyType(
        {
            "canonical_share_code_contract_sha256": actual,
            "canonical_portfolio_contract_sha256": CANONICAL_PORTFOLIO_CONTRACT_SHA256,
            "source_execution_contract_sha256": SOURCE_EXECUTION_CONTRACT_SHA256,
        }
    )


@dataclasses.dataclass(frozen=True)
class SportyBetProviderBinding:
    selected_portfolio_id: str
    leg_id: str
    canonical_router_decision_sha256: str
    source_router_v3_decision_sha256: str
    fixture_id: str
    event_id: str
    home_team_name: str
    away_team_name: str
    provider_market_id: str
    provider_market_name: str
    provider_specifier: str | None
    provider_outcome_id: str
    provider_outcome_name: str
    expected_decimal_odds: float
    quote_sha256: str
    current_inventory_sha256: str
    source_raw_sha256: str
    current_mapping_rebind_sha256: str
    current_mapping_contract_sha256: str
    current_reconciliation_sha256: str

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.to_dict())

    def to_bridge_intent(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "homeTeamName": self.home_team_name,
            "awayTeamName": self.away_team_name,
            "marketName": self.provider_market_name,
            "outcomeName": self.provider_outcome_name,
            "specifier": self.provider_specifier,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_portfolio_id": self.selected_portfolio_id,
            "leg_id": self.leg_id,
            "canonical_router_decision_sha256": self.canonical_router_decision_sha256,
            "source_router_v3_decision_sha256": self.source_router_v3_decision_sha256,
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "provider_market_id": self.provider_market_id,
            "provider_market_name": self.provider_market_name,
            "provider_specifier": self.provider_specifier,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_outcome_name": self.provider_outcome_name,
            "expected_decimal_odds": self.expected_decimal_odds,
            "quote_sha256": self.quote_sha256,
            "current_inventory_sha256": self.current_inventory_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "current_mapping_rebind_sha256": self.current_mapping_rebind_sha256,
            "current_mapping_contract_sha256": self.current_mapping_contract_sha256,
            "current_reconciliation_sha256": self.current_reconciliation_sha256,
            "bridge_intent": self.to_bridge_intent(),
        }


def _bindings_from_verified_portfolio(
    portfolio: _portfolio.SelectedPortfolio,
) -> tuple[SportyBetProviderBinding, ...]:
    rows = tuple(
        SportyBetProviderBinding(
            selected_portfolio_id=portfolio.selected_portfolio_id,
            leg_id=leg.leg_id,
            canonical_router_decision_sha256=leg.canonical_router_decision_sha256,
            source_router_v3_decision_sha256=leg.source_router_v3_decision_sha256,
            fixture_id=leg.fixture_id,
            event_id=leg.event_id,
            home_team_name=leg.home_team,
            away_team_name=leg.away_team,
            provider_market_id=leg.provider_market_id,
            provider_market_name=leg.provider_market_name,
            provider_specifier=leg.provider_specifier,
            provider_outcome_id=leg.provider_outcome_id,
            provider_outcome_name=leg.provider_outcome_name,
            expected_decimal_odds=leg.decimal_odds,
            quote_sha256=leg.quote_sha256,
            current_inventory_sha256=leg.current_inventory_sha256,
            source_raw_sha256=leg.source_raw_sha256,
            current_mapping_rebind_sha256=leg.current_mapping_rebind_sha256,
            current_mapping_contract_sha256=leg.current_mapping_contract_sha256,
            current_reconciliation_sha256=leg.current_reconciliation_sha256,
        )
        for leg in portfolio.selected_legs
    )
    if len({item.leg_id for item in rows}) != len(rows):
        raise SportyBetShareCodeError("selected Portfolio contains duplicate leg identity")
    if len({item.event_id for item in rows}) != len(rows):
        raise SportyBetShareCodeError("selected Portfolio contains duplicate provider event")
    return tuple(sorted(rows, key=lambda item: (item.fixture_id, item.leg_id)))


def build_provider_bindings(
    selected_portfolio: _portfolio.SelectedPortfolio,
) -> tuple[SportyBetProviderBinding, ...]:
    """Derive the exact delivery binding set from verified P1.5 evidence."""
    try:
        rebuilt = _portfolio.verify_selected_portfolio(selected_portfolio)
    except _portfolio.CanonicalPortfolioError as exc:
        raise SportyBetShareCodeError("SelectedPortfolio exact source replay failed") from exc
    return _bindings_from_verified_portfolio(rebuilt)


def _verify_bindings(
    portfolio: _portfolio.SelectedPortfolio,
    bindings: Sequence[SportyBetProviderBinding],
) -> tuple[SportyBetProviderBinding, ...]:
    supplied = tuple(bindings)
    if any(type(item) is not SportyBetProviderBinding for item in supplied):
        raise SportyBetShareCodeError("provider_bindings must contain exact SportyBetProviderBinding values")
    supplied = tuple(sorted(supplied, key=lambda item: (item.fixture_id, item.leg_id)))
    expected = _bindings_from_verified_portfolio(portfolio)
    if len(supplied) != len(expected):
        raise SportyBetShareCodeError("provider binding count differs from SelectedPortfolio")
    if [item.to_dict() for item in supplied] != [item.to_dict() for item in expected]:
        raise SportyBetShareCodeError("provider bindings differ from exact SelectedPortfolio evidence")
    return supplied


def _source_intents(
    portfolio: _portfolio.SelectedPortfolio,
    bindings: Sequence[SportyBetProviderBinding],
) -> tuple[_source.CurrentSemanticIntent, ...]:
    return tuple(
        _source.CurrentSemanticIntent(
            leg_id=item.leg_id,
            fixture_id=item.fixture_id,
            router_decision_sha256=item.source_router_v3_decision_sha256,
            optimizer_id=portfolio.selected_portfolio_id,
            event_id=item.event_id,
            home_team_name=item.home_team_name,
            away_team_name=item.away_team_name,
            market_name=item.provider_market_name,
            outcome_name=item.provider_outcome_name,
            specifier=item.provider_specifier,
            quote_sha256=item.quote_sha256,
            expected_decimal_odds=item.expected_decimal_odds,
            expected_provider_market_id=item.provider_market_id,
            expected_provider_outcome_id=item.provider_outcome_id,
            current_inventory_sha256=item.current_inventory_sha256,
            source_raw_sha256=item.source_raw_sha256,
            current_mapping_rebind_sha256=item.current_mapping_rebind_sha256,
            current_reconciliation_sha256=item.current_reconciliation_sha256,
        )
        for item in bindings
    )


def _freshness_reasons(
    portfolio: _portfolio.SelectedPortfolio,
    now: datetime,
) -> tuple[tuple[str, ...], int]:
    now = _utc(now, "share-code evaluation_time")
    if now < portfolio.evaluation_time:
        raise SportyBetShareCodeError("share-code evaluation_time predates SelectedPortfolio")
    delta = (now - portfolio.evaluation_time).total_seconds()
    by_router = {
        item.canonical_router_decision_sha256: item
        for item in portfolio._router_inputs
    }
    if len(by_router) != len(portfolio._router_inputs):
        raise SportyBetShareCodeError("SelectedPortfolio Router input identity is duplicate")
    reasons: list[str] = []
    minimum_leads = [MINIMUM_LEAD_SECONDS]
    for leg in portfolio.selected_legs:
        source = by_router.get(leg.canonical_router_decision_sha256)
        if source is None:
            raise SportyBetShareCodeError("selected leg lost canonical Router evidence")
        decision = source._source_portfolio_input.router_decision
        max_age = decision.price_all_evaluation.max_quote_age_seconds
        minimum_lead = max(MINIMUM_LEAD_SECONDS, decision.price_all_evaluation.minimum_lead_seconds)
        minimum_leads.append(int(minimum_lead))
        age = leg.portfolio_quote_age_seconds + delta
        lead = leg.portfolio_kickoff_lead_seconds - delta
        if not math.isfinite(age) or age < 0:
            raise SportyBetShareCodeError("selected provider quote age is invalid")
        if not math.isfinite(lead):
            raise SportyBetShareCodeError("selected fixture lead is invalid")
        if age > max_age:
            reasons.append(f"{leg.fixture_id}:CURRENT_PROVIDER_QUOTE_STALE")
        if lead <= minimum_lead:
            reasons.append(f"{leg.fixture_id}:FIXTURE_TOO_CLOSE_TO_KICKOFF")
    return tuple(sorted(set(reasons))), max(minimum_leads)


def _safety_false(receipt: Mapping[str, Any], label: str) -> None:
    if not isinstance(receipt, Mapping):
        raise SportyBetShareCodeError(f"{label} receipt must be a mapping")
    for field in _SAFETY_FIELDS:
        if receipt.get(field) is not False:
            raise SportyBetShareCodeError(f"{label} safety field {field} must remain false")


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_canonical_bytes(dict(payload)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@dataclasses.dataclass(frozen=True, init=False)
class ShareCodeFailure:
    contract_sha256: str
    observed_at: datetime
    selected_portfolio_id: str
    target_legs: int
    selected_leg_count: int
    shortfall: int
    failure_code: ShareCodeFailureCode
    stage: str
    reasons: tuple[str, ...]
    provider_binding_sha256s: tuple[str, ...]
    semantic_resolution_receipt_sha256: str | None = None
    provider_transport_receipt_sha256: str | None = None

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise SportyBetShareCodeError("ShareCodeFailure is builder-only")

    @classmethod
    def _create(cls, **fields: Any) -> "ShareCodeFailure":
        value = object.__new__(cls)
        for name, field in fields.items():
            object.__setattr__(value, name, field)
        if type(value.failure_code) is not ShareCodeFailureCode:
            raise SportyBetShareCodeError("share-code failure code is invalid")
        if type(value.stage) is not str or not value.stage:
            raise SportyBetShareCodeError("share-code failure stage is invalid")
        if type(value.reasons) is not tuple or value.reasons != tuple(sorted(set(value.reasons))) or not value.reasons:
            raise SportyBetShareCodeError("share-code failure reasons must be sorted unique non-empty tuple")
        if value.selected_leg_count + value.shortfall != value.target_legs:
            raise SportyBetShareCodeError("share-code failure target accounting drifted")
        return value

    @property
    def verified(self) -> bool:
        return False

    @property
    def share_code(self) -> None:
        return None

    @property
    def share_url(self) -> None:
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "contract_sha256": self.contract_sha256,
            "observed_at": _iso(self.observed_at),
            "selected_portfolio_id": self.selected_portfolio_id,
            "target_legs": self.target_legs,
            "selected_leg_count": self.selected_leg_count,
            "shortfall": self.shortfall,
            "verified": False,
            "failure_code": self.failure_code.value,
            "stage": self.stage,
            "reasons": list(self.reasons),
            "provider_binding_sha256s": list(self.provider_binding_sha256s),
            "semantic_resolution_receipt_sha256": self.semantic_resolution_receipt_sha256,
            "provider_transport_receipt_sha256": self.provider_transport_receipt_sha256,
            "shareCode": None,
            "shareURL": None,
            "combined_odds": None,
            "exact_create_reload_equality": False,
            "authority": dict(AUTHORITY),
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        }


@dataclasses.dataclass(frozen=True, init=False)
class VerifiedShareCode:
    contract_sha256: str
    observed_at: datetime
    selected_portfolio_id: str
    target_legs: int
    selected_leg_count: int
    shortfall: int
    provider_binding_sha256s: tuple[str, ...]
    semantic_resolution_receipt_sha256: str
    provider_transport_receipt_sha256: str
    exact_roundtrip_verification: tuple[Mapping[str, Any], ...]
    share_code: str
    share_url: str
    combined_odds: str | float | None

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise SportyBetShareCodeError("VerifiedShareCode is builder-only")

    @classmethod
    def _create(cls, **fields: Any) -> "VerifiedShareCode":
        value = object.__new__(cls)
        for name, field in fields.items():
            object.__setattr__(value, name, field)
        if value.selected_leg_count <= 0 or value.selected_leg_count + value.shortfall != value.target_legs:
            raise SportyBetShareCodeError("verified share-code target accounting drifted")
        if type(value.share_code) is not str or not value.share_code:
            raise SportyBetShareCodeError("verified share code is invalid")
        if type(value.share_url) is not str or not value.share_url.startswith(("http://", "https://")):
            raise SportyBetShareCodeError("verified share URL is invalid")
        if len(value.provider_binding_sha256s) != value.selected_leg_count:
            raise SportyBetShareCodeError("verified provider-binding count drifted")
        if len(value.exact_roundtrip_verification) != value.selected_leg_count:
            raise SportyBetShareCodeError("verified create/reload proof count drifted")
        if not all(item.get("exact_semantic_native_odds_match") is True for item in value.exact_roundtrip_verification):
            raise SportyBetShareCodeError("verified create/reload proof is incomplete")
        return value

    @property
    def verified(self) -> bool:
        return True

    @property
    def status(self) -> str:
        return "VERIFIED_SHARE_CODE" if self.shortfall == 0 else "VERIFIED_SHARE_CODE_WITH_SHORTFALL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "contract_sha256": self.contract_sha256,
            "status": self.status,
            "observed_at": _iso(self.observed_at),
            "selected_portfolio_id": self.selected_portfolio_id,
            "target_legs": self.target_legs,
            "selected_leg_count": self.selected_leg_count,
            "shortfall": self.shortfall,
            "verified": True,
            "provider_binding_sha256s": list(self.provider_binding_sha256s),
            "semantic_resolution_receipt_sha256": self.semantic_resolution_receipt_sha256,
            "provider_transport_receipt_sha256": self.provider_transport_receipt_sha256,
            "exact_roundtrip_verification": [dict(item) for item in self.exact_roundtrip_verification],
            "shareCode": self.share_code,
            "shareURL": self.share_url,
            "combined_odds": self.combined_odds,
            "exact_create_reload_equality": True,
            "authority": dict(AUTHORITY),
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        }


def _failure(
    *,
    contract_sha256: str,
    portfolio: _portfolio.SelectedPortfolio,
    bindings: Sequence[SportyBetProviderBinding],
    now: datetime,
    failure_code: ShareCodeFailureCode,
    stage: str,
    reasons: Sequence[str],
    semantic_receipt: Mapping[str, Any] | None = None,
    transport_receipt: Mapping[str, Any] | None = None,
) -> ShareCodeFailure:
    result = ShareCodeFailure._create(
        contract_sha256=contract_sha256,
        observed_at=now,
        selected_portfolio_id=portfolio.selected_portfolio_id,
        target_legs=portfolio.target_legs,
        selected_leg_count=portfolio.selected_count,
        shortfall=portfolio.shortfall,
        failure_code=failure_code,
        stage=stage,
        reasons=tuple(sorted(set(reasons))),
        provider_binding_sha256s=tuple(item.canonical_sha256 for item in bindings),
        semantic_resolution_receipt_sha256=(
            None if semantic_receipt is None else _sha(dict(semantic_receipt))
        ),
        provider_transport_receipt_sha256=(
            None if transport_receipt is None else _sha(dict(transport_receipt))
        ),
    )
    return result


def _execute(
    selected_portfolio: _portfolio.SelectedPortfolio,
    provider_bindings: Sequence[SportyBetProviderBinding],
    *,
    output_dir: Path,
    evaluation_time: datetime,
    require_live_current: bool,
    delay_seconds: float,
) -> VerifiedShareCode | ShareCodeFailure:
    identities = validate_share_code_contract()
    if not isinstance(output_dir, Path):
        raise SportyBetShareCodeError("output_dir must be Path")
    if (
        isinstance(delay_seconds, bool)
        or not isinstance(delay_seconds, (int, float))
        or not math.isfinite(delay_seconds)
        or delay_seconds < 0
    ):
        raise SportyBetShareCodeError("delay_seconds must be finite non-negative")
    try:
        portfolio = _portfolio.verify_selected_portfolio(selected_portfolio)
    except _portfolio.CanonicalPortfolioError as exc:
        raise SportyBetShareCodeError("SelectedPortfolio exact source replay failed") from exc
    if require_live_current and (
        portfolio.proof_mode != _portfolio.LIVE_CURRENT
        or portfolio._require_live_current is not True
    ):
        raise SportyBetShareCodeError("live share-code delivery requires LIVE_CURRENT SelectedPortfolio")
    bindings = _verify_bindings(portfolio, provider_bindings)
    now = _utc(evaluation_time, "evaluation_time")
    if not bindings:
        result = _failure(
            contract_sha256=identities["canonical_share_code_contract_sha256"],
            portfolio=portfolio,
            bindings=bindings,
            now=now,
            failure_code=ShareCodeFailureCode.NO_SELECTED_LEGS,
            stage="PRE_TRANSPORT",
            reasons=("SELECTED_PORTFOLIO_HAS_NO_LEGS",),
        )
        _atomic_write(output_dir / RECEIPT_FILENAME, result.to_dict())
        return result

    freshness, minimum_lead = _freshness_reasons(portfolio, now)
    if freshness:
        result = _failure(
            contract_sha256=identities["canonical_share_code_contract_sha256"],
            portfolio=portfolio,
            bindings=bindings,
            now=now,
            failure_code=ShareCodeFailureCode.REPRICE_REQUIRED,
            stage="PRE_TRANSPORT",
            reasons=freshness,
        )
        _atomic_write(output_dir / RECEIPT_FILENAME, result.to_dict())
        return result

    intents = _source_intents(portfolio, bindings)
    bridge_intents = tuple(item.to_bridge_intent() for item in bindings)
    semantic_receipt: Mapping[str, Any] | None = None
    transport_receipt: Mapping[str, Any] | None = None
    try:
        selections, semantic_receipt = semantic_bridge.resolve_live_intents(
            intents=bridge_intents,
            output_dir=output_dir / "semantic-resolution",
            minimum_lead_seconds=minimum_lead,
            delay_seconds=float(delay_seconds),
        )
        _safety_false(semantic_receipt, "semantic resolution")
        if semantic_receipt.get("caller_supplied_market_outcome_ids_accepted") is not False:
            raise SportyBetShareCodeError("semantic resolver accepted caller provider-native IDs")
        _source._verify_resolution(intents, selections, semantic_receipt)
    except semantic_bridge.SportyBetSemanticShareError as exc:
        result = _failure(
            contract_sha256=identities["canonical_share_code_contract_sha256"],
            portfolio=portfolio,
            bindings=bindings,
            now=now,
            failure_code=ShareCodeFailureCode.PROVIDER_CHANGED,
            stage="SEMANTIC_RESOLUTION",
            reasons=(f"SEMANTIC_RESOLUTION_FAILED:{exc}",),
            semantic_receipt=semantic_receipt,
        )
        _atomic_write(output_dir / RECEIPT_FILENAME, result.to_dict())
        return result
    except (_source.CurrentSportyBetAccumulatorExecutionError, SportyBetShareCodeError) as exc:
        result = _failure(
            contract_sha256=identities["canonical_share_code_contract_sha256"],
            portfolio=portfolio,
            bindings=bindings,
            now=now,
            failure_code=ShareCodeFailureCode.PROVIDER_CHANGED,
            stage="SEMANTIC_RESOLUTION",
            reasons=(f"SEMANTIC_VERIFICATION_FAILED:{exc}",),
            semantic_receipt=semantic_receipt,
        )
        _atomic_write(output_dir / RECEIPT_FILENAME, result.to_dict())
        return result

    # Live mode rechecks freshness immediately before create. Synthetic/as-of
    # mode keeps its supplied evaluation time deterministic.
    precreate_now = datetime.now(timezone.utc) if require_live_current else now
    precreate_freshness, _ = _freshness_reasons(portfolio, precreate_now)
    if precreate_freshness:
        result = _failure(
            contract_sha256=identities["canonical_share_code_contract_sha256"],
            portfolio=portfolio,
            bindings=bindings,
            now=precreate_now,
            failure_code=ShareCodeFailureCode.REPRICE_REQUIRED,
            stage="PRE_CREATE_FRESHNESS",
            reasons=precreate_freshness,
            semantic_receipt=semantic_receipt,
        )
        _atomic_write(output_dir / RECEIPT_FILENAME, result.to_dict())
        return result

    try:
        transport_receipt = direct_bridge.create_and_roundtrip(
            selections=selections,
            output_dir=output_dir / "transport-roundtrip",
        )
        _safety_false(transport_receipt, "provider transport")
        roundtrip = _source._verify_transport(intents, transport_receipt)
    except direct_bridge.SportyBetDirectShareError as exc:
        result = _failure(
            contract_sha256=identities["canonical_share_code_contract_sha256"],
            portfolio=portfolio,
            bindings=bindings,
            now=precreate_now,
            failure_code=ShareCodeFailureCode.CREATE_RELOAD_FAILED,
            stage="CREATE_RELOAD",
            reasons=(f"CREATE_RELOAD_FAILED:{exc}",),
            semantic_receipt=semantic_receipt,
            transport_receipt=transport_receipt,
        )
        _atomic_write(output_dir / RECEIPT_FILENAME, result.to_dict())
        return result
    except (_source.CurrentSportyBetAccumulatorExecutionError, SportyBetShareCodeError) as exc:
        result = _failure(
            contract_sha256=identities["canonical_share_code_contract_sha256"],
            portfolio=portfolio,
            bindings=bindings,
            now=precreate_now,
            failure_code=ShareCodeFailureCode.PROVIDER_CHANGED,
            stage="CREATE_RELOAD_VERIFICATION",
            reasons=(f"CREATE_RELOAD_VERIFICATION_FAILED:{exc}",),
            semantic_receipt=semantic_receipt,
            transport_receipt=transport_receipt,
        )
        _atomic_write(output_dir / RECEIPT_FILENAME, result.to_dict())
        return result

    share_code = transport_receipt.get("shareCode")
    share_url = transport_receipt.get("shareURL")
    if (
        type(share_code) is not str
        or not share_code
        or type(share_url) is not str
        or not share_url.startswith(("http://", "https://"))
    ):
        result = _failure(
            contract_sha256=identities["canonical_share_code_contract_sha256"],
            portfolio=portfolio,
            bindings=bindings,
            now=precreate_now,
            failure_code=ShareCodeFailureCode.VERIFIED_RESPONSE_INCOMPLETE,
            stage="FINALIZE",
            reasons=("VERIFIED_TRANSPORT_OMITTED_SHARE_CODE_OR_URL",),
            semantic_receipt=semantic_receipt,
            transport_receipt=transport_receipt,
        )
        _atomic_write(output_dir / RECEIPT_FILENAME, result.to_dict())
        return result

    result = VerifiedShareCode._create(
        contract_sha256=identities["canonical_share_code_contract_sha256"],
        observed_at=precreate_now,
        selected_portfolio_id=portfolio.selected_portfolio_id,
        target_legs=portfolio.target_legs,
        selected_leg_count=portfolio.selected_count,
        shortfall=portfolio.shortfall,
        provider_binding_sha256s=tuple(item.canonical_sha256 for item in bindings),
        semantic_resolution_receipt_sha256=_sha(dict(semantic_receipt)),
        provider_transport_receipt_sha256=_sha(dict(transport_receipt)),
        exact_roundtrip_verification=roundtrip,
        share_code=share_code,
        share_url=share_url,
        combined_odds=transport_receipt.get("combined_odds"),
    )
    _atomic_write(output_dir / RECEIPT_FILENAME, result.to_dict())
    return result


def create_verified_share_code_as_of(
    selected_portfolio: _portfolio.SelectedPortfolio,
    provider_bindings: Sequence[SportyBetProviderBinding],
    *,
    output_dir: Path,
    evaluation_time: datetime,
    delay_seconds: float = 0.0,
) -> VerifiedShareCode | ShareCodeFailure:
    """Deterministic/synthetic proof lane; provider bridges may be test doubles."""
    return _execute(
        selected_portfolio,
        provider_bindings,
        output_dir=output_dir,
        evaluation_time=evaluation_time,
        require_live_current=False,
        delay_seconds=delay_seconds,
    )


def create_verified_share_code(
    selected_portfolio: _portfolio.SelectedPortfolio,
    provider_bindings: Sequence[SportyBetProviderBinding],
    *,
    output_dir: Path,
    delay_seconds: float = 0.25,
) -> VerifiedShareCode | ShareCodeFailure:
    """Anonymous LIVE_CURRENT create/reload verification; never a wager."""
    return _execute(
        selected_portfolio,
        provider_bindings,
        output_dir=output_dir,
        evaluation_time=datetime.now(timezone.utc),
        require_live_current=True,
        delay_seconds=delay_seconds,
    )


def create_verified_shadow_all_market_share_code(
    *,
    portfolio: Any,
    output_dir: Path,
    delay_seconds: float = 0.25,
) -> Any:
    """Temporary one-way Current Shadow compatibility entrypoint.

    P1.6 moves the Current Shadow caller to this canonical delivery module while
    preserving the already reviewed Shadow fresh-fallback behavior exactly.
    P2.0 is responsible for migrating that profile to ``SelectedPortfolio``;
    this compatibility seam must not become an independent delivery authority.
    """
    _assert_non_wager_authority()
    from domain import current_shadow_all_market_share_code as _legacy_shadow

    try:
        receipt = _legacy_shadow.create_verified_shadow_all_market_share_code(
            portfolio=portfolio,
            output_dir=output_dir,
            delay_seconds=delay_seconds,
        )
    except _legacy_shadow.CurrentShadowAllMarketShareCodeError as exc:
        raise CurrentShadowAllMarketShareCodeError(
            "Current Shadow canonical delivery compatibility failed"
        ) from exc
    payload = receipt.to_dict()
    _safety_false(payload, "Current Shadow compatibility receipt")
    if receipt.status not in {
        STATUS_CODE_VERIFIED,
        STATUS_CODE_VERIFIED_WITH_SHORTFALL,
        STATUS_REPRICE_REQUIRED,
        STATUS_PROVIDER_CHANGED,
    }:
        raise CurrentShadowAllMarketShareCodeError(
            "Current Shadow compatibility status escaped reviewed vocabulary"
        )
    return receipt


# Postponed annotations in the existing runner do not require the concrete
# profile-specific receipt class at import time. This alias exists solely for
# compatibility with type-hint introspection; runtime output is returned intact.
ShadowAllMarketShareCodeReceipt = Any


__all__ = [
    "AUTHORITY",
    "CANONICAL_PORTFOLIO_CONTRACT_SHA256",
    "CurrentShadowAllMarketShareCodeError",
    "DIRECT_BRIDGE_SCHEMA",
    "EXPECTED_CONTRACT_SHA256",
    "IMPLEMENTATION_ID",
    "MINIMUM_LEAD_SECONDS",
    "OUTPUT_CONTRACT",
    "POLICY_ID",
    "RECEIPT_FILENAME",
    "SCHEMA_VERSION",
    "SEMANTIC_BRIDGE_SCHEMA",
    "SOURCE_EXECUTION_CONTRACT_SHA256",
    "STATUS_CODE_VERIFIED",
    "STATUS_CODE_VERIFIED_WITH_SHORTFALL",
    "STATUS_PROVIDER_CHANGED",
    "STATUS_REPRICE_REQUIRED",
    "ShadowAllMarketShareCodeReceipt",
    "ShareCodeFailure",
    "ShareCodeFailureCode",
    "SportyBetProviderBinding",
    "SportyBetShareCodeError",
    "VerifiedShareCode",
    "build_provider_bindings",
    "calculate_share_code_contract_sha256",
    "create_verified_shadow_all_market_share_code",
    "create_verified_share_code",
    "create_verified_share_code_as_of",
    "validate_share_code_contract",
]
