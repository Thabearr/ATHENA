"""Verified anonymous share-code transport for ATHENA research shadow portfolios.

This boundary never upgrades research evidence into production authority. It
rebuilds the exact research portfolio from its source decisions, rechecks
currentness at transport time, resolves each semantic intent against a fresh
SportyBet event response, requires the fresh native identity and odds to equal
what the research portfolio actually priced, and only then invokes the existing
anonymous SportyBet create -> reload transport.

A returned share code is a research field-trial artifact, not a wager. No login,
cookie, wallet, stake submission, or bet placement is permitted.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import types
from collections.abc import Mapping, Sequence
from typing import Any

from domain import current_shadow_sportybet_field_trial as field_trial
from scripts import sportybet_direct_share_bridge as direct_bridge
from scripts import sportybet_semantic_share_bridge as semantic_bridge


SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-shadow-sportybet-share-code-v1"

STATUS_CODE_VERIFIED = "RESEARCH_SHADOW_SHARE_CODE_VERIFIED"
STATUS_CODE_VERIFIED_WITH_SHORTFALL = (
    "RESEARCH_SHADOW_SHARE_CODE_VERIFIED_WITH_SHORTFALL"
)
STATUS_NO_QUALIFIED_LEGS = "RESEARCH_NO_CODE_NO_QUALIFIED_LEGS"
STATUS_REPRICE_REQUIRED = "RESEARCH_NO_CODE_REPRICE_REQUIRED"
STATUS_PROVIDER_CHANGED = "RESEARCH_NO_CODE_PROVIDER_CHANGED_REBIND_REQUIRED"
STATUS_ROUNDTRIP_CHANGED = "RESEARCH_NO_CODE_PROVIDER_ROUNDTRIP_CHANGED"

AUTHORITY = types.MappingProxyType(
    {
        "research_shadow_portfolio_consumption": True,
        "fresh_semantic_resolution": True,
        "fresh_odds_equality_verification": True,
        "anonymous_research_share_code_generation": True,
        "provider_create_reload_verification": True,
        "production_model": False,
        "phase6": False,
        "production_selection": False,
        "production_sportybet_execution": False,
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


class CurrentShadowSportyBetShareCodeError(ValueError):
    """Raised when research share-code verification cannot preserve exact evidence."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise CurrentShadowSportyBetShareCodeError(
            f"{label} must be timezone-aware"
        )
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentShadowSportyBetShareCodeError(f"{label} is invalid") from exc


def _canonical(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentShadowSportyBetShareCodeError(
            "canonical serialization failed"
        ) from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise CurrentShadowSportyBetShareCodeError(
            f"{label} odds are missing"
        )
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CurrentShadowSportyBetShareCodeError(
            f"{label} odds are invalid"
        ) from exc
    if not result.is_finite() or result <= Decimal("1"):
        raise CurrentShadowSportyBetShareCodeError(
            f"{label} odds are invalid"
        )
    return result


def _safety_false(receipt: Mapping[str, Any], label: str) -> None:
    for field in _SAFETY_FIELDS:
        if receipt.get(field) is not False:
            raise CurrentShadowSportyBetShareCodeError(
                f"{label} safety field {field} must remain false"
            )


def _write_receipt(output_dir: Path, payload: Mapping[str, Any]) -> None:
    if not isinstance(output_dir, Path):
        raise CurrentShadowSportyBetShareCodeError(
            "output_dir must be Path"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "research-shadow-share-code-receipt.json").write_bytes(
        _canonical(dict(payload))
    )


@dataclasses.dataclass(frozen=True)
class ResearchShadowShareCodeReceipt:
    status: str
    observed_at: datetime
    portfolio_sha256: str
    requested_target_size: int
    portfolio_shortfall: int
    selected_leg_count: int
    reasons: tuple[str, ...]
    semantic_resolution_receipt_sha256: str | None
    transport_receipt_sha256: str | None
    share_code: str | None
    share_url: str | None
    combined_odds: str | None

    def __post_init__(self) -> None:
        allowed = {
            STATUS_CODE_VERIFIED,
            STATUS_CODE_VERIFIED_WITH_SHORTFALL,
            STATUS_NO_QUALIFIED_LEGS,
            STATUS_REPRICE_REQUIRED,
            STATUS_PROVIDER_CHANGED,
            STATUS_ROUNDTRIP_CHANGED,
        }
        if self.status not in allowed:
            raise CurrentShadowSportyBetShareCodeError(
                "research share-code status escaped reviewed vocabulary"
            )
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, "observed_at"),
        )
        if (
            type(self.portfolio_sha256) is not str
            or len(self.portfolio_sha256) != 64
            or any(
                ch not in "0123456789abcdef"
                for ch in self.portfolio_sha256
            )
        ):
            raise CurrentShadowSportyBetShareCodeError(
                "portfolio_sha256 is invalid"
            )
        for value, label in (
            (self.requested_target_size, "requested_target_size"),
            (self.portfolio_shortfall, "portfolio_shortfall"),
            (self.selected_leg_count, "selected_leg_count"),
        ):
            if type(value) is not int or value < 0:
                raise CurrentShadowSportyBetShareCodeError(
                    f"{label} must be non-negative int"
                )
        reasons = tuple(sorted(set(self.reasons)))
        if type(self.reasons) is not tuple or reasons != self.reasons:
            raise CurrentShadowSportyBetShareCodeError(
                "reasons must be sorted unique tuple"
            )
        for value, label in (
            (
                self.semantic_resolution_receipt_sha256,
                "semantic_resolution_receipt_sha256",
            ),
            (self.transport_receipt_sha256, "transport_receipt_sha256"),
        ):
            if value is not None and (
                type(value) is not str
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise CurrentShadowSportyBetShareCodeError(
                    f"{label} is invalid"
                )
        verified = self.status in {
            STATUS_CODE_VERIFIED,
            STATUS_CODE_VERIFIED_WITH_SHORTFALL,
        }
        if verified:
            if (
                type(self.share_code) is not str
                or not self.share_code
                or type(self.share_url) is not str
                or not self.share_url.startswith("http")
                or type(self.combined_odds) is not str
                or not self.combined_odds
                or self.semantic_resolution_receipt_sha256 is None
                or self.transport_receipt_sha256 is None
                or self.selected_leg_count < 1
            ):
                raise CurrentShadowSportyBetShareCodeError(
                    "verified research code receipt is incomplete"
                )
        elif (
            self.share_code is not None
            or self.share_url is not None
            or self.combined_odds is not None
        ):
            raise CurrentShadowSportyBetShareCodeError(
                "non-verified research result cannot expose a share code"
            )

    @property
    def code_verified(self) -> bool:
        return self.status in {
            STATUS_CODE_VERIFIED,
            STATUS_CODE_VERIFIED_WITH_SHORTFALL,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "status": self.status,
            "observed_at": self.observed_at.isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
            "portfolio_sha256": self.portfolio_sha256,
            "requested_target_size": self.requested_target_size,
            "portfolio_shortfall": self.portfolio_shortfall,
            "selected_leg_count": self.selected_leg_count,
            "reasons": list(self.reasons),
            "semantic_resolution_receipt_sha256": (
                self.semantic_resolution_receipt_sha256
            ),
            "transport_receipt_sha256": self.transport_receipt_sha256,
            "shareCode": self.share_code,
            "shareURL": self.share_url,
            "combined_odds": self.combined_odds,
            "code_verified": self.code_verified,
            "authority": dict(AUTHORITY),
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        }


def _verify_portfolio(
    portfolio: Any,
    source_decisions: Sequence[field_trial.ResearchFixtureDecision],
) -> field_trial.ResearchShadowPortfolio:
    if type(portfolio) is not field_trial.ResearchShadowPortfolio:
        raise CurrentShadowSportyBetShareCodeError(
            "exact ResearchShadowPortfolio is required"
        )
    if (
        isinstance(source_decisions, (str, bytes))
        or not isinstance(source_decisions, Sequence)
    ):
        raise CurrentShadowSportyBetShareCodeError(
            "source_decisions must be a sequence"
        )
    values = tuple(source_decisions)
    if any(
        type(item) is not field_trial.ResearchFixtureDecision
        for item in values
    ):
        raise CurrentShadowSportyBetShareCodeError(
            "source_decisions contain invalid item"
        )
    try:
        rebuilt = field_trial.optimize_research_shadow_portfolio(
            values,
            target_size=portfolio.requested_target_size,
            evaluation_time=portfolio.evaluation_time,
        )
    except Exception as exc:
        raise CurrentShadowSportyBetShareCodeError(
            "research portfolio source reconstruction failed"
        ) from exc
    if rebuilt.to_dict() != portfolio.to_dict():
        raise CurrentShadowSportyBetShareCodeError(
            "research portfolio differs from exact source-decision reconstruction"
        )
    if portfolio.authority["production_selection"] is not False:
        raise CurrentShadowSportyBetShareCodeError(
            "research portfolio acquired production selection authority"
        )
    return rebuilt


def _terminal(
    *,
    portfolio: field_trial.ResearchShadowPortfolio,
    observed_at: datetime,
    status: str,
    reasons: Sequence[str],
    semantic_receipt: Mapping[str, Any] | None = None,
    transport_receipt: Mapping[str, Any] | None = None,
) -> ResearchShadowShareCodeReceipt:
    return ResearchShadowShareCodeReceipt(
        status=status,
        observed_at=observed_at,
        portfolio_sha256=portfolio.canonical_sha256,
        requested_target_size=portfolio.requested_target_size,
        portfolio_shortfall=portfolio.shortfall,
        selected_leg_count=len(portfolio.selected_legs),
        reasons=tuple(sorted(set(reasons))),
        semantic_resolution_receipt_sha256=(
            None
            if semantic_receipt is None
            else _sha(dict(semantic_receipt))
        ),
        transport_receipt_sha256=(
            None
            if transport_receipt is None
            else _sha(dict(transport_receipt))
        ),
        share_code=None,
        share_url=None,
        combined_odds=None,
    )


def _fresh_at_transport(
    portfolio: field_trial.ResearchShadowPortfolio,
    now: datetime,
) -> tuple[str, ...]:
    reasons: list[str] = []
    for leg in portfolio.selected_legs:
        age = (now - leg.quote_observed_at).total_seconds()
        lead = (leg.fixture.kickoff_utc - now).total_seconds()
        if not math.isfinite(age) or age < 0:
            raise CurrentShadowSportyBetShareCodeError(
                "selected research quote is future-dated"
            )
        if age > field_trial.MAX_SOURCE_AGE_SECONDS:
            reasons.append(
                f"{leg.fixture.fixture_identifier}:CURRENT_PROVIDER_QUOTE_STALE"
            )
        if (
            not math.isfinite(lead)
            or lead <= field_trial.MINIMUM_LEAD_SECONDS
        ):
            reasons.append(
                f"{leg.fixture.fixture_identifier}:FIXTURE_TOO_CLOSE_TO_KICKOFF"
            )
    return tuple(sorted(set(reasons)))


def _verify_semantic_resolution(
    portfolio: field_trial.ResearchShadowPortfolio,
    selections: Sequence[Mapping[str, str]],
    receipt: Mapping[str, Any],
) -> tuple[str, ...]:
    _safety_false(receipt, "semantic resolution")
    if receipt.get("caller_supplied_market_outcome_ids_accepted") is not False:
        raise CurrentShadowSportyBetShareCodeError(
            "semantic gate accepted caller provider-native IDs"
        )
    audits = receipt.get("resolved")
    if (
        type(audits) is not list
        or len(audits) != len(portfolio.selected_legs)
        or len(selections) != len(portfolio.selected_legs)
    ):
        raise CurrentShadowSportyBetShareCodeError(
            "semantic resolution count differs from selected research portfolio"
        )
    audit_by_event = {
        item.get("eventId"): item
        for item in audits
        if type(item) is dict
    }
    selection_by_event = {
        item.get("eventId"): item
        for item in selections
        if isinstance(item, Mapping)
    }
    if (
        len(audit_by_event) != len(portfolio.selected_legs)
        or len(selection_by_event) != len(portfolio.selected_legs)
    ):
        raise CurrentShadowSportyBetShareCodeError(
            "semantic resolution event identities are duplicate or incomplete"
        )

    reasons: list[str] = []
    for leg in portfolio.selected_legs:
        event_id = leg.fixture.event_id
        audit = audit_by_event.get(event_id)
        selection = selection_by_event.get(event_id)
        if audit is None or selection is None:
            reasons.append(
                f"{leg.fixture.fixture_identifier}:SEMANTIC_EVENT_MISSING"
            )
            continue
        expected_native = leg.expected_provider_native_identity()
        if dict(selection) != expected_native:
            reasons.append(
                f"{leg.fixture.fixture_identifier}:PROVIDER_NATIVE_IDENTITY_CHANGED"
            )
        expected_semantics = {
            "observed_home_team": leg.fixture.home_team,
            "observed_away_team": leg.fixture.away_team,
            "observed_market_name": leg.provider_market_name,
            "observed_outcome_name": leg.provider_outcome_name,
            "observed_specifier": leg.provider_specifier,
            "marketId": leg.provider_market_id,
            "outcomeId": leg.provider_outcome_id,
        }
        if any(audit.get(key) != value for key, value in expected_semantics.items()):
            reasons.append(
                f"{leg.fixture.fixture_identifier}:PROVIDER_SEMANTICS_CHANGED"
            )
        if _decimal(audit.get("odds"), "semantic resolved") != _decimal(
            leg.decimal_odds,
            "research priced",
        ):
            reasons.append(
                f"{leg.fixture.fixture_identifier}:PROVIDER_ODDS_CHANGED"
            )
    return tuple(sorted(set(reasons)))


def _accepted_row(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CurrentShadowSportyBetShareCodeError(
            f"{label} accepted event is invalid"
        )
    event_id = value.get("eventId")
    home = value.get("homeTeamName")
    away = value.get("awayTeamName")
    if any(
        type(item) is not str or not item or item != item.strip()
        for item in (event_id, home, away)
    ):
        raise CurrentShadowSportyBetShareCodeError(
            f"{label} accepted fixture semantics are invalid"
        )
    markets = value.get("markets")
    if (
        type(markets) is not list
        or len(markets) != 1
        or type(markets[0]) is not dict
    ):
        raise CurrentShadowSportyBetShareCodeError(
            f"{label} accepted event must contain exactly one market"
        )
    market = markets[0]
    outcomes = market.get("outcomes")
    if (
        type(outcomes) is not list
        or len(outcomes) != 1
        or type(outcomes[0]) is not dict
    ):
        raise CurrentShadowSportyBetShareCodeError(
            f"{label} accepted market must contain exactly one outcome"
        )
    outcome = outcomes[0]
    market_id = market.get("id", market.get("marketId"))
    outcome_id = outcome.get("id", outcome.get("outcomeId"))
    market_name = semantic_bridge._market_text(market)
    outcome_name = semantic_bridge._outcome_text(outcome)
    specifier = market.get("specifier")
    if market_id is None or outcome_id is None:
        raise CurrentShadowSportyBetShareCodeError(
            f"{label} accepted native identity is missing"
        )
    if (
        type(market_name) is not str
        or not market_name
        or type(outcome_name) is not str
        or not outcome_name
    ):
        raise CurrentShadowSportyBetShareCodeError(
            f"{label} accepted semantic labels are missing"
        )
    if specifier is not None and (
        type(specifier) is not str
        or not specifier
        or specifier != specifier.strip()
    ):
        raise CurrentShadowSportyBetShareCodeError(
            f"{label} accepted specifier is invalid"
        )
    return {
        "eventId": event_id,
        "homeTeamName": home,
        "awayTeamName": away,
        "marketId": str(market_id),
        "marketName": market_name,
        "specifier": specifier,
        "outcomeId": str(outcome_id),
        "outcomeName": outcome_name,
        "odds": _decimal(outcome.get("odds"), label),
    }


def _verify_transport_roundtrip(
    portfolio: field_trial.ResearchShadowPortfolio,
    receipt: Mapping[str, Any],
) -> tuple[str, ...]:
    _safety_false(receipt, "direct transport")
    if (
        receipt.get("create_unavailable_outcomes") != 0
        or receipt.get("load_unavailable_outcomes") != 0
        or receipt.get("selection_count") != len(portfolio.selected_legs)
        or receipt.get("create_accepted_selection_count")
        != len(portfolio.selected_legs)
        or receipt.get("load_accepted_selection_count")
        != len(portfolio.selected_legs)
        or receipt.get("exact_roundtrip_selection_identity_verified") is not True
    ):
        return ("DIRECT_TRANSPORT_COUNT_OR_AVAILABILITY_CHANGED",)

    create = receipt.get("create_accepted_outcomes")
    load = receipt.get("load_accepted_outcomes")
    if (
        type(create) is not list
        or type(load) is not list
        or len(create) != len(portfolio.selected_legs)
        or len(load) != len(portfolio.selected_legs)
    ):
        return ("DIRECT_TRANSPORT_ACCEPTED_ROWS_CHANGED",)

    try:
        create_rows = {
            row["eventId"]: row
            for row in (
                _accepted_row(item, "create")
                for item in create
            )
        }
        load_rows = {
            row["eventId"]: row
            for row in (
                _accepted_row(item, "load")
                for item in load
            )
        }
    except CurrentShadowSportyBetShareCodeError:
        return ("DIRECT_TRANSPORT_ACCEPTED_ROWS_CHANGED",)

    if create_rows != load_rows:
        return ("DIRECT_TRANSPORT_CREATE_RELOAD_CHANGED",)
    if len(create_rows) != len(portfolio.selected_legs):
        return ("DIRECT_TRANSPORT_ACCEPTED_ROWS_CHANGED",)

    reasons: list[str] = []
    for leg in portfolio.selected_legs:
        row = load_rows.get(leg.fixture.event_id)
        if row is None:
            reasons.append(
                f"{leg.fixture.fixture_identifier}:DIRECT_EVENT_MISSING"
            )
            continue
        expected = {
            "eventId": leg.fixture.event_id,
            "homeTeamName": leg.fixture.home_team,
            "awayTeamName": leg.fixture.away_team,
            "marketId": leg.provider_market_id,
            "marketName": leg.provider_market_name,
            "specifier": leg.provider_specifier,
            "outcomeId": leg.provider_outcome_id,
            "outcomeName": leg.provider_outcome_name,
        }
        if any(row[key] != value for key, value in expected.items()):
            reasons.append(
                f"{leg.fixture.fixture_identifier}:DIRECT_PROVIDER_SEMANTICS_CHANGED"
            )
        if row["odds"] != _decimal(
            leg.decimal_odds,
            "research priced",
        ):
            reasons.append(
                f"{leg.fixture.fixture_identifier}:DIRECT_PROVIDER_ODDS_CHANGED"
            )
    return tuple(sorted(set(reasons)))


def create_current_shadow_sportybet_share_code(
    *,
    portfolio: field_trial.ResearchShadowPortfolio,
    source_decisions: Sequence[field_trial.ResearchFixtureDecision],
    output_dir: Path,
    delay_seconds: float = 0.25,
) -> ResearchShadowShareCodeReceipt:
    """Create a research-only anonymous share code after fresh exact re-verification."""

    rebuilt = _verify_portfolio(portfolio, source_decisions)
    now = _now_utc()
    if now < rebuilt.evaluation_time:
        raise CurrentShadowSportyBetShareCodeError(
            "transport time predates research portfolio"
        )

    if not rebuilt.selected_legs:
        result = _terminal(
            portfolio=rebuilt,
            observed_at=now,
            status=STATUS_NO_QUALIFIED_LEGS,
            reasons=("NO_QUALIFIED_RESEARCH_LEGS",),
        )
        _write_receipt(output_dir, result.to_dict())
        return result

    freshness = _fresh_at_transport(rebuilt, now)
    if freshness:
        result = _terminal(
            portfolio=rebuilt,
            observed_at=now,
            status=STATUS_REPRICE_REQUIRED,
            reasons=freshness,
        )
        _write_receipt(output_dir, result.to_dict())
        return result

    intents = semantic_bridge.validate_intents(
        list(rebuilt.semantic_intents())
    )
    semantic_dir = output_dir / "semantic-resolution"
    try:
        selections, semantic_receipt = semantic_bridge.resolve_live_intents(
            intents=intents,
            output_dir=semantic_dir,
            minimum_lead_seconds=field_trial.MINIMUM_LEAD_SECONDS,
            delay_seconds=delay_seconds,
        )
    except semantic_bridge.SportyBetSemanticShareError as exc:
        result = _terminal(
            portfolio=rebuilt,
            observed_at=now,
            status=STATUS_PROVIDER_CHANGED,
            reasons=(f"SEMANTIC_RESOLUTION_FAILED:{exc}",),
        )
        _write_receipt(output_dir, result.to_dict())
        return result

    semantic_reasons = _verify_semantic_resolution(
        rebuilt,
        selections,
        semantic_receipt,
    )
    if semantic_reasons:
        status = (
            STATUS_REPRICE_REQUIRED
            if all("ODDS_CHANGED" in item for item in semantic_reasons)
            else STATUS_PROVIDER_CHANGED
        )
        result = _terminal(
            portfolio=rebuilt,
            observed_at=now,
            status=status,
            reasons=semantic_reasons,
            semantic_receipt=semantic_receipt,
        )
        _write_receipt(output_dir, result.to_dict())
        return result

    # Network time spent on semantic re-resolution counts against the original
    # priced quote and kickoff window. Re-evaluate those exact gates immediately
    # before the provider create request; never let the earlier pre-network time
    # snapshot authorize a now-stale or now-too-close selection.
    precreate_now = _now_utc()
    if precreate_now < now:
        raise CurrentShadowSportyBetShareCodeError(
            "transport clock moved backwards during semantic resolution"
        )
    precreate_freshness = _fresh_at_transport(rebuilt, precreate_now)
    if precreate_freshness:
        result = _terminal(
            portfolio=rebuilt,
            observed_at=precreate_now,
            status=STATUS_REPRICE_REQUIRED,
            reasons=precreate_freshness,
            semantic_receipt=semantic_receipt,
        )
        _write_receipt(output_dir, result.to_dict())
        return result
    now = precreate_now

    transport_dir = output_dir / "transport-roundtrip"
    try:
        transport_receipt = direct_bridge.create_and_roundtrip(
            selections=selections,
            output_dir=transport_dir,
        )
    except direct_bridge.SportyBetDirectShareError as exc:
        result = _terminal(
            portfolio=rebuilt,
            observed_at=now,
            status=STATUS_ROUNDTRIP_CHANGED,
            reasons=(f"DIRECT_CREATE_RELOAD_FAILED:{exc}",),
            semantic_receipt=semantic_receipt,
        )
        _write_receipt(output_dir, result.to_dict())
        return result

    transport_reasons = _verify_transport_roundtrip(
        rebuilt,
        transport_receipt,
    )
    if transport_reasons:
        result = _terminal(
            portfolio=rebuilt,
            observed_at=now,
            status=STATUS_ROUNDTRIP_CHANGED,
            reasons=transport_reasons,
            semantic_receipt=semantic_receipt,
            transport_receipt=transport_receipt,
        )
        _write_receipt(output_dir, result.to_dict())
        return result

    share_code_value = transport_receipt.get("shareCode")
    share_url = transport_receipt.get("shareURL")
    combined_odds = transport_receipt.get("combined_odds")
    if (
        type(share_code_value) is not str
        or not share_code_value
        or type(share_url) is not str
        or not share_url.startswith("http")
        or type(combined_odds) is not str
        or not combined_odds
    ):
        result = _terminal(
            portfolio=rebuilt,
            observed_at=now,
            status=STATUS_ROUNDTRIP_CHANGED,
            reasons=("DIRECT_VERIFIED_RESPONSE_OMITTED_SHARE_CODE_FIELDS",),
            semantic_receipt=semantic_receipt,
            transport_receipt=transport_receipt,
        )
        _write_receipt(output_dir, result.to_dict())
        return result

    status = (
        STATUS_CODE_VERIFIED
        if rebuilt.shortfall == 0
        else STATUS_CODE_VERIFIED_WITH_SHORTFALL
    )
    result = ResearchShadowShareCodeReceipt(
        status=status,
        observed_at=now,
        portfolio_sha256=rebuilt.canonical_sha256,
        requested_target_size=rebuilt.requested_target_size,
        portfolio_shortfall=rebuilt.shortfall,
        selected_leg_count=len(rebuilt.selected_legs),
        reasons=(
            ("EXACT_RESEARCH_SHADOW_CREATE_RELOAD_VERIFIED",)
            if rebuilt.shortfall == 0
            else (
                "EXACT_RESEARCH_SHADOW_CREATE_RELOAD_VERIFIED",
                "REQUESTED_TARGET_SHORTFALL_PRESERVED_NO_PADDING",
            )
        ),
        semantic_resolution_receipt_sha256=_sha(
            dict(semantic_receipt)
        ),
        transport_receipt_sha256=_sha(
            dict(transport_receipt)
        ),
        share_code=share_code_value,
        share_url=share_url,
        combined_odds=combined_odds,
    )
    _write_receipt(output_dir, result.to_dict())
    return result


__all__ = [
    "AUTHORITY",
    "DATASET_NAME",
    "SCHEMA_VERSION",
    "STATUS_CODE_VERIFIED",
    "STATUS_CODE_VERIFIED_WITH_SHORTFALL",
    "STATUS_NO_QUALIFIED_LEGS",
    "STATUS_PROVIDER_CHANGED",
    "STATUS_REPRICE_REQUIRED",
    "STATUS_ROUNDTRIP_CHANGED",
    "CurrentShadowSportyBetShareCodeError",
    "ResearchShadowShareCodeReceipt",
    "create_current_shadow_sportybet_share_code",
]
