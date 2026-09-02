"""Anonymous create/reload verification for PR-E all-market Shadow portfolios.

This boundary accepts only the replay-verifiable PR-E portfolio.  It rechecks
quote freshness, re-resolves exact provider semantics/odds, then performs the
existing anonymous SportyBet create + reload proof.  It never logs in, uses a
wallet, submits a stake, or places a wager.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import time
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from domain import current_shadow_all_market_portfolio as portfolio_module
from domain._current_shadow_price_core import (
    MAX_QUOTE_AGE_SECONDS,
    MINIMUM_DECIMAL_ODDS,
    MINIMUM_LEAD_SECONDS,
    MINIMUM_PREDICTION_CONFIDENCE,
    ShadowPriceDisposition,
)
from domain._current_shadow_quote_binding import build_current_shadow_exact_quotes
from scripts import sportybet_direct_share_bridge as direct_bridge
from scripts import sportybet_semantic_share_bridge as semantic_bridge

SCHEMA_VERSION = 2
DATASET_NAME = "athena-current-shadow-all-market-share-code-v2"
STATUS_CODE_VERIFIED = "RESEARCH_SHADOW_CODE_VERIFIED"
STATUS_CODE_VERIFIED_WITH_SHORTFALL = "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL"
STATUS_REPRICE_REQUIRED = "RESEARCH_NO_CODE_REPRICE_REQUIRED"
STATUS_PROVIDER_CHANGED = "RESEARCH_NO_CODE_PROVIDER_CHANGED"

AUTHORITY = MappingProxyType({
    "research_shadow_portfolio_consumption": True,
    "research_fresh_semantic_resolution": True,
    "research_exact_odds_equality_verification": True,
    "research_anonymous_share_code_generation": True,
    "provider_create_reload_verification": True,
    "production_model": False,
    "production_probability": False,
    "phase6": False,
    "production_selection": False,
    "production_sportybet_execution": False,
    "login": False,
    "cookies": False,
    "wallet": False,
    "staking": False,
    "bet": False,
    "wager_placed": False,
})

_SAFETY_FIELDS = (
    "sportybet_login_used",
    "sportybet_cookie_used",
    "sportybet_wallet_used",
    "stake_submitted",
    "wager_placed",
)


class CurrentShadowAllMarketShareCodeError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                           separators=(",", ":")) + "\n").encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentShadowAllMarketShareCodeError("canonical serialization failed") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise CurrentShadowAllMarketShareCodeError(f"{label} odds are missing")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CurrentShadowAllMarketShareCodeError(f"{label} odds are invalid") from exc
    if not result.is_finite() or result <= Decimal("1"):
        raise CurrentShadowAllMarketShareCodeError(f"{label} odds are invalid")
    return result


def _safety_false(receipt: Mapping[str, Any], label: str) -> None:
    for field in _SAFETY_FIELDS:
        if receipt.get(field) is not False:
            raise CurrentShadowAllMarketShareCodeError(
                f"{label} safety field {field} must remain false"
            )


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    if not isinstance(path, Path):
        raise CurrentShadowAllMarketShareCodeError("output path must be Path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(dict(payload)))


@dataclass(frozen=True)
class ShadowAllMarketShareCodeReceipt:
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
    fresh_selected_legs: tuple[Mapping[str, Any], ...] = ()
    fallback_events: tuple[Mapping[str, Any], ...] = ()
    exact_create_reload_equality: bool = False

    def __post_init__(self) -> None:
        allowed = {
            STATUS_CODE_VERIFIED,
            STATUS_CODE_VERIFIED_WITH_SHORTFALL,
            STATUS_REPRICE_REQUIRED,
            STATUS_PROVIDER_CHANGED,
        }
        if self.status not in allowed:
            raise CurrentShadowAllMarketShareCodeError(
                "share-code receipt status escaped reviewed vocabulary"
            )
        if (
            type(self.observed_at) is not datetime
            or self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() is None
        ):
            raise CurrentShadowAllMarketShareCodeError("observed_at must be timezone-aware")
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(timezone.utc))
        if (
            type(self.portfolio_sha256) is not str
            or len(self.portfolio_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in self.portfolio_sha256)
        ):
            raise CurrentShadowAllMarketShareCodeError("portfolio_sha256 is invalid")
        if (
            type(self.requested_target_size) is not int
            or not 1 <= self.requested_target_size <= 50
        ):
            raise CurrentShadowAllMarketShareCodeError("requested_target_size is invalid")
        if type(self.portfolio_shortfall) is not int or self.portfolio_shortfall < 0:
            raise CurrentShadowAllMarketShareCodeError("portfolio_shortfall is invalid")
        if type(self.selected_leg_count) is not int or self.selected_leg_count < 0:
            raise CurrentShadowAllMarketShareCodeError("selected_leg_count is invalid")
        if self.selected_leg_count + self.portfolio_shortfall != self.requested_target_size:
            raise CurrentShadowAllMarketShareCodeError("selected leg count and shortfall do not match target")
        if type(self.reasons) is not tuple or self.reasons != tuple(sorted(set(self.reasons))):
            raise CurrentShadowAllMarketShareCodeError("reasons must be sorted unique tuple")
        for value, label in (
            (self.semantic_resolution_receipt_sha256, "semantic_resolution_receipt_sha256"),
            (self.transport_receipt_sha256, "transport_receipt_sha256"),
        ):
            if value is not None and (
                type(value) is not str
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise CurrentShadowAllMarketShareCodeError(f"{label} is invalid")
        verified = self.status in {STATUS_CODE_VERIFIED, STATUS_CODE_VERIFIED_WITH_SHORTFALL}
        if self.status == STATUS_CODE_VERIFIED and self.portfolio_shortfall != 0:
            raise CurrentShadowAllMarketShareCodeError("fully verified code cannot carry shortfall")
        if self.status == STATUS_CODE_VERIFIED_WITH_SHORTFALL and self.portfolio_shortfall <= 0:
            raise CurrentShadowAllMarketShareCodeError("shortfall verified status requires positive shortfall")
        if verified:
            if (
                type(self.share_code) is not str
                or not self.share_code
                or type(self.share_url) is not str
                or not self.share_url.startswith(("http://", "https://"))
                or type(self.combined_odds) is not str
                or not self.combined_odds
                or self.semantic_resolution_receipt_sha256 is None
                or self.transport_receipt_sha256 is None
            ):
                raise CurrentShadowAllMarketShareCodeError("verified share-code receipt is incomplete")
            if self.exact_create_reload_equality is not True:
                raise CurrentShadowAllMarketShareCodeError("verified receipt requires exact create/reload equality")
        elif any(
            value is not None for value in (self.share_code, self.share_url, self.combined_odds)
        ):
            raise CurrentShadowAllMarketShareCodeError(
                "non-verified receipt cannot expose provider code metadata"
            )

    @property
    def code_verified(self) -> bool:
        return self.status in {STATUS_CODE_VERIFIED, STATUS_CODE_VERIFIED_WITH_SHORTFALL}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "status": self.status,
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "portfolio_sha256": self.portfolio_sha256,
            "requested_target_size": self.requested_target_size,
            "portfolio_shortfall": self.portfolio_shortfall,
            "selected_leg_count": self.selected_leg_count,
            "reasons": list(self.reasons),
            "semantic_resolution_receipt_sha256": self.semantic_resolution_receipt_sha256,
            "transport_receipt_sha256": self.transport_receipt_sha256,
            "shareCode": self.share_code,
            "shareURL": self.share_url,
            "combined_odds": self.combined_odds,
            "fresh_selected_legs": [dict(item) for item in self.fresh_selected_legs],
            "fallback_events": [dict(item) for item in self.fallback_events],
            "exact_create_reload_equality": self.exact_create_reload_equality,
            "code_verified": self.code_verified,
            "authority": dict(AUTHORITY),
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        }


def _terminal(
    *, portfolio: portfolio_module.ShadowPortfolioOptimization, status: str,
    reasons: Sequence[str], semantic_receipt: Mapping[str, Any] | None = None,
    transport_receipt: Mapping[str, Any] | None = None,
    fresh_selected_legs: Sequence[Mapping[str, Any]] | None = None,
    fallback_events: Sequence[Mapping[str, Any]] = (),
) -> ShadowAllMarketShareCodeReceipt:
    selected_count = len(portfolio.selected_legs) if fresh_selected_legs is None else len(fresh_selected_legs)
    shortfall = portfolio.requested_target_size - selected_count
    return ShadowAllMarketShareCodeReceipt(
        status=status,
        observed_at=_now(),
        portfolio_sha256=portfolio.canonical_sha256,
        requested_target_size=portfolio.requested_target_size,
        portfolio_shortfall=shortfall,
        selected_leg_count=selected_count,
        reasons=tuple(sorted(set(reasons))),
        semantic_resolution_receipt_sha256=None if semantic_receipt is None else _sha(dict(semantic_receipt)),
        transport_receipt_sha256=None if transport_receipt is None else _sha(dict(transport_receipt)),
        share_code=None,
        share_url=None,
        combined_odds=None,
        fresh_selected_legs=tuple(
            MappingProxyType(dict(item)) for item in (fresh_selected_legs or ())
        ),
        fallback_events=tuple(MappingProxyType(dict(item)) for item in fallback_events),
        exact_create_reload_equality=False,
    )


def _quote_times(
    portfolio: portfolio_module.ShadowPortfolioOptimization,
) -> dict[str, datetime]:
    result: dict[str, datetime] = {}
    by_fixture = {item.fixture_identity: item for item in portfolio._router_inputs}
    for leg in portfolio.selected_legs:
        source = by_fixture.get(leg.fixture_identity)
        if source is None:
            raise CurrentShadowAllMarketShareCodeError("selected leg lost retained Router input")
        _opportunity, _price_result, quote = portfolio_module._selected_opportunity(source)
        if quote.identity_sha256 != leg.quote_identity_sha256:
            raise CurrentShadowAllMarketShareCodeError("selected leg quote differs on retained source replay")
        result[leg.leg_id] = quote.observed_at
    return result


def _freshness(
    portfolio: portfolio_module.ShadowPortfolioOptimization,
    now: datetime,
) -> tuple[str, ...]:
    quote_times = _quote_times(portfolio)
    reasons: list[str] = []
    for leg in portfolio.selected_legs:
        observed = quote_times[leg.leg_id]
        age = (now - observed).total_seconds()
        lead = (leg.kickoff_utc - now).total_seconds()
        if not math.isfinite(age) or age < 0:
            raise CurrentShadowAllMarketShareCodeError("selected quote is future-dated at transport")
        if age > MAX_QUOTE_AGE_SECONDS:
            reasons.append(f"{leg.fixture_identity}:CURRENT_PROVIDER_QUOTE_STALE")
        if not math.isfinite(lead) or lead <= MINIMUM_LEAD_SECONDS:
            reasons.append(f"{leg.fixture_identity}:FIXTURE_TOO_CLOSE_TO_KICKOFF")
    return tuple(sorted(set(reasons)))


def _semantic_intents(portfolio: portfolio_module.ShadowPortfolioOptimization) -> list[dict[str, Any]]:
    return [
        {
            "eventId": leg.provider_event_id,
            "homeTeamName": leg.home_team,
            "awayTeamName": leg.away_team,
            "marketName": leg.provider_market_name,
            "outcomeName": leg.provider_outcome_name,
            "specifier": leg.provider_specifier,
        }
        for leg in portfolio.selected_legs
    ]


def _verify_semantic(
    portfolio: portfolio_module.ShadowPortfolioOptimization,
    selections: Sequence[Mapping[str, str]],
    receipt: Mapping[str, Any],
) -> tuple[str, ...]:
    _safety_false(receipt, "semantic resolution")
    if receipt.get("caller_supplied_market_outcome_ids_accepted") is not False:
        raise CurrentShadowAllMarketShareCodeError("semantic resolver accepted caller native IDs")
    audits = receipt.get("resolved")
    if type(audits) is not list or len(audits) != len(portfolio.selected_legs) or len(selections) != len(portfolio.selected_legs):
        raise CurrentShadowAllMarketShareCodeError("semantic resolution count mismatch")
    audit_by_event = {item.get("eventId"): item for item in audits if type(item) is dict}
    selection_by_event = {item.get("eventId"): item for item in selections if isinstance(item, Mapping)}
    if len(audit_by_event) != len(portfolio.selected_legs) or len(selection_by_event) != len(portfolio.selected_legs):
        raise CurrentShadowAllMarketShareCodeError("semantic event identities are duplicate/incomplete")
    reasons: list[str] = []
    for leg in portfolio.selected_legs:
        audit = audit_by_event.get(leg.provider_event_id)
        selection = selection_by_event.get(leg.provider_event_id)
        if audit is None or selection is None:
            reasons.append(f"{leg.fixture_identity}:SEMANTIC_EVENT_MISSING")
            continue
        expected_native = {
            "eventId": leg.provider_event_id,
            "marketId": leg.provider_market_id,
            "outcomeId": leg.provider_outcome_id,
        }
        if leg.provider_specifier is not None:
            expected_native["specifier"] = leg.provider_specifier
        if dict(selection) != expected_native:
            reasons.append(f"{leg.fixture_identity}:PROVIDER_NATIVE_IDENTITY_CHANGED")
        expected_semantics = {
            "observed_home_team": leg.home_team,
            "observed_away_team": leg.away_team,
            "observed_market_name": leg.provider_market_name,
            "observed_outcome_name": leg.provider_outcome_name,
            "observed_specifier": leg.provider_specifier,
            "marketId": leg.provider_market_id,
            "outcomeId": leg.provider_outcome_id,
        }
        if any(audit.get(key) != value for key, value in expected_semantics.items()):
            reasons.append(f"{leg.fixture_identity}:PROVIDER_SEMANTICS_CHANGED")
        if _decimal(audit.get("odds"), "semantic resolved") != _decimal(leg.decimal_odds, "priced"):
            reasons.append(f"{leg.fixture_identity}:PROVIDER_ODDS_CHANGED")
    return tuple(sorted(set(reasons)))


def _transport_lead_reasons(
    portfolio: portfolio_module.ShadowPortfolioOptimization,
    now: datetime,
) -> tuple[str, ...]:
    reasons = []
    for leg in portfolio.selected_legs:
        lead = (leg.kickoff_utc - now).total_seconds()
        if not math.isfinite(lead) or lead <= MINIMUM_LEAD_SECONDS:
            reasons.append(f"{leg.fixture_identity}:FIXTURE_TOO_CLOSE_TO_KICKOFF")
    return tuple(sorted(set(reasons)))


def _opportunity_quote(source: portfolio_module.ShadowPortfolioRouterInput, opportunity: Any):
    result = opportunity.price_result
    if result.disposition is not ShadowPriceDisposition.PRICED or result.quote_identity_sha256 is None:
        return None
    matches = [
        quote for quote in build_current_shadow_exact_quotes(source.price_all_bundle._context)
        if quote.identity_sha256 == result.quote_identity_sha256
    ]
    if len(matches) != 1:
        raise CurrentShadowAllMarketShareCodeError(
            "prediction candidate does not bind one exact retained provider quote"
        )
    return matches[0]


def _fresh_candidate_key(opportunity: Any) -> tuple[Any, ...]:
    if opportunity.prediction_confidence is None:
        raise CurrentShadowAllMarketShareCodeError("fresh candidate lacks prediction confidence")
    return (
        -opportunity.prediction_confidence,
        portfolio_module.router._prediction_canonical_key(opportunity.price_result),
    )


def _fresh_ev_diagnostic(opportunity: Any, odds: Decimal) -> float | None:
    result = opportunity.price_result
    settlement_probabilities = getattr(result, "settlement_state_probabilities", ())
    if settlement_probabilities:
        try:
            return math.fsum(
                probability * portfolio_module.router.settlement_unit_return(state, float(odds))
                for state, probability in settlement_probabilities
            )
        except (TypeError, ValueError):
            return None
    model_probability = getattr(result, "model_probability", None)
    if model_probability is None:
        return None
    return model_probability * float(odds) - 1.0


def _fresh_resolve_portfolio(
    portfolio: portfolio_module.ShadowPortfolioOptimization,
    *,
    output_dir: Path,
    delay_seconds: float,
) -> tuple[tuple[dict[str, str], ...], dict[str, Any], tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    """Resolve each fixture once and apply current Prediction-first fallback."""

    output_dir.mkdir(parents=True, exist_ok=True)
    event_dir = output_dir / "events"
    event_dir.mkdir(parents=True, exist_ok=True)
    source_by_fixture = {item.fixture_identity: item for item in portfolio._router_inputs}
    selections: list[dict[str, str]] = []
    fresh_legs: list[Mapping[str, Any]] = []
    fallback_events: list[Mapping[str, Any]] = []
    source_hashes: list[dict[str, Any]] = []
    candidate_audits: list[dict[str, Any]] = []
    selected_ids = {leg.fixture_identity: leg.selected_opportunity_id for leg in portfolio.selected_legs}

    for index, leg in enumerate(portfolio.selected_legs):
        if index and delay_seconds:
            time.sleep(delay_seconds)
        source = source_by_fixture.get(leg.fixture_identity)
        if source is None:
            raise CurrentShadowAllMarketShareCodeError("selected fixture lost Router evidence")
        payload, raw, status, url = semantic_bridge._fetch_event(leg.provider_event_id)
        (event_dir / f"{leg.provider_event_id.replace(':', '_')}.raw.json").write_bytes(raw)
        if status != 200 or payload.get("bizCode") != 10000:
            fallback_events.append(MappingProxyType({
                "fixture_identity": leg.fixture_identity,
                "from_opportunity_id": leg.selected_opportunity_id,
                "to_opportunity_id": None,
                "reason": "FRESH_PROVIDER_EVENT_UNAVAILABLE",
            }))
            continue
        event = semantic_bridge._event_with_markets(payload, leg.provider_event_id)
        source_hashes.append({
            "eventId": leg.provider_event_id,
            "request_url": url,
            "http_status": status,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_size": len(raw),
        })
        candidates = sorted(
            (
                opportunity for opportunity in source.router_decision.opportunities
                if opportunity.prediction_confidence is not None
                and opportunity.prediction_confidence >= MINIMUM_PREDICTION_CONFIDENCE
                and opportunity.prediction_confidence_method is not None
                and opportunity.price_result.disposition is ShadowPriceDisposition.PRICED
            ),
            key=_fresh_candidate_key,
        )
        chosen: tuple[Any, Any, dict[str, str], dict[str, Any], Decimal] | None = None
        per_fixture: list[dict[str, Any]] = []
        for opportunity in candidates:
            quote = _opportunity_quote(source, opportunity)
            if quote is None:
                continue
            intent = {
                "eventId": leg.provider_event_id,
                "homeTeamName": leg.home_team,
                "awayTeamName": leg.away_team,
                "marketName": quote.provider_market_name,
                "outcomeName": quote.provider_outcome_name,
                "specifier": quote.provider_specifier,
            }
            try:
                selection, audit = semantic_bridge.resolve_intent(
                    event=event,
                    intent=intent,
                    minimum_lead_seconds=MINIMUM_LEAD_SECONDS,
                )
                odds = _decimal(audit.get("odds"), "fresh semantic resolved")
            except semantic_bridge.SportyBetSemanticShareError as exc:
                per_fixture.append({
                    "opportunity_id": opportunity.opportunity_id,
                    "prediction_confidence": opportunity.prediction_confidence,
                    "eligible": False,
                    "reason": f"EXACT_PROVIDER_SEMANTICS_UNAVAILABLE:{exc}",
                })
                continue
            eligible = odds >= Decimal(str(MINIMUM_DECIMAL_ODDS))
            per_fixture.append({
                "opportunity_id": opportunity.opportunity_id,
                "prediction_confidence": opportunity.prediction_confidence,
                "exact_current_odds": str(odds),
                "eligible": eligible,
                "reason": None if eligible else "EXACT_CURRENT_ODDS_BELOW_1_09",
            })
            if eligible:
                chosen = opportunity, quote, selection, audit, odds
                break
        candidate_audits.append({
            "fixture_identity": leg.fixture_identity,
            "candidates": per_fixture,
        })
        if chosen is None:
            fallback_events.append(MappingProxyType({
                "fixture_identity": leg.fixture_identity,
                "from_opportunity_id": leg.selected_opportunity_id,
                "to_opportunity_id": None,
                "reason": "NO_CURRENT_PREDICTION_QUALIFIED_FALLBACK",
            }))
            continue
        opportunity, quote, selection, audit, odds = chosen
        prediction_identity = "|".join(
            portfolio_module.router._prediction_canonical_key(opportunity.price_result)
        )
        fresh = MappingProxyType({
            "fixture_identity": leg.fixture_identity,
            "provider_event_id": leg.provider_event_id,
            "home_team": leg.home_team,
            "away_team": leg.away_team,
            "competition": leg.competition,
            "market_id": opportunity.price_result.market_id.value,
            "outcome_id": opportunity.price_result.outcome_id.value,
            "line": opportunity.price_result.line,
            "canonical_prediction_identity": prediction_identity,
            "selected_opportunity_id": opportunity.opportunity_id,
            "prediction_confidence": opportunity.prediction_confidence,
            "prediction_confidence_method": opportunity.prediction_confidence_method,
            "router_policy_id": source.router_decision.router_policy_id,
            "portfolio_policy_id": portfolio_module.PORTFOLIO_POLICY_ID,
            "provider_market_id": selection["marketId"],
            "provider_market_name": audit["observed_market_name"],
            "provider_specifier": audit["observed_specifier"],
            "provider_outcome_id": selection["outcomeId"],
            "provider_outcome_name": audit["observed_outcome_name"],
            "decimal_odds": str(odds),
            "stale_portfolio_decimal_odds": leg.decimal_odds,
            "fresh_net_expected_value_diagnostic": _fresh_ev_diagnostic(opportunity, odds),
            "fresh_robust_edge_diagnostic": None,
            "fresh_robust_edge_unavailable_reason": "FULL_CURRENT_MARKET_PARTITION_NOT_FETCHED_BY_TRANSPORT_GATE",
            "stale_router_net_expected_value_diagnostic": opportunity.robust_net_expected_value,
            "stale_router_robust_edge_diagnostic": opportunity.robust_edge,
            "fresh_provider_source_sha256": source_hashes[-1]["raw_sha256"],
        })
        selections.append(selection)
        fresh_legs.append(fresh)
        if opportunity.opportunity_id != selected_ids[leg.fixture_identity]:
            fallback_events.append(MappingProxyType({
                "fixture_identity": leg.fixture_identity,
                "from_opportunity_id": leg.selected_opportunity_id,
                "to_opportunity_id": opportunity.opportunity_id,
                "reason": "PREDICTION_FIRST_FRESH_FALLBACK",
            }))

    receipt = {
        "schema": "athena-sportybet-prediction-first-fresh-resolution-v2",
        "observed_at": semantic_bridge._utc_now(),
        "minimum_prediction_confidence": MINIMUM_PREDICTION_CONFIDENCE,
        "minimum_decimal_odds": MINIMUM_DECIMAL_ODDS,
        "intent_count": len(portfolio.selected_legs),
        "resolved_count": len(selections),
        "source_hashes": sorted(source_hashes, key=lambda item: item["eventId"]),
        "candidate_audits": sorted(candidate_audits, key=lambda item: item["fixture_identity"]),
        "fresh_selected_legs": [dict(item) for item in fresh_legs],
        "fallback_events": [dict(item) for item in fallback_events],
        "caller_supplied_market_outcome_ids_accepted": False,
        "wager_placed": False,
    }
    _write(output_dir / "fresh-prediction-resolution-receipt.json", receipt)
    return tuple(selections), receipt, tuple(fresh_legs), tuple(fallback_events)


def _accepted_row(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CurrentShadowAllMarketShareCodeError(f"{label} accepted event is invalid")
    event_id = value.get("eventId")
    home = value.get("homeTeamName")
    away = value.get("awayTeamName")
    if any(type(item) is not str or not item or item != item.strip() for item in (event_id, home, away)):
        raise CurrentShadowAllMarketShareCodeError(f"{label} accepted fixture identity is invalid")
    markets = value.get("markets")
    if type(markets) is not list or len(markets) != 1 or type(markets[0]) is not dict:
        raise CurrentShadowAllMarketShareCodeError(f"{label} accepted event must contain one market")
    market = markets[0]
    outcomes = market.get("outcomes")
    if type(outcomes) is not list or len(outcomes) != 1 or type(outcomes[0]) is not dict:
        raise CurrentShadowAllMarketShareCodeError(f"{label} accepted market must contain one outcome")
    outcome = outcomes[0]
    market_id = market.get("id", market.get("marketId"))
    outcome_id = outcome.get("id", outcome.get("outcomeId"))
    if market_id is None or outcome_id is None:
        raise CurrentShadowAllMarketShareCodeError(
            f"{label} accepted provider-native identity is missing"
        )
    if not str(market_id).strip() or not str(outcome_id).strip():
        raise CurrentShadowAllMarketShareCodeError(
            f"{label} accepted provider-native identity is empty"
        )
    market_name = semantic_bridge._market_text(market)
    outcome_name = semantic_bridge._outcome_text(outcome)
    specifier = market.get("specifier")
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


def _verify_roundtrip(
    fresh_selected_legs: Sequence[Mapping[str, Any]],
    receipt: Mapping[str, Any],
) -> tuple[str, ...]:
    _safety_false(receipt, "direct transport")
    count = len(fresh_selected_legs)
    if (
        receipt.get("create_unavailable_outcomes") != 0
        or receipt.get("load_unavailable_outcomes") != 0
        or receipt.get("selection_count") != count
        or receipt.get("create_accepted_selection_count") != count
        or receipt.get("load_accepted_selection_count") != count
        or receipt.get("exact_roundtrip_selection_identity_verified") is not True
    ):
        return ("DIRECT_TRANSPORT_COUNT_OR_AVAILABILITY_CHANGED",)
    create = receipt.get("create_accepted_outcomes")
    load = receipt.get("load_accepted_outcomes")
    if type(create) is not list or type(load) is not list or len(create) != count or len(load) != count:
        return ("DIRECT_TRANSPORT_ACCEPTED_ROWS_CHANGED",)
    try:
        create_rows = {row["eventId"]: row for row in (_accepted_row(item, "create") for item in create)}
        load_rows = {row["eventId"]: row for row in (_accepted_row(item, "load") for item in load)}
    except CurrentShadowAllMarketShareCodeError:
        return ("DIRECT_TRANSPORT_ACCEPTED_ROWS_CHANGED",)
    if create_rows != load_rows:
        return ("DIRECT_TRANSPORT_CREATE_RELOAD_CHANGED",)
    if len(load_rows) != count:
        return ("DIRECT_TRANSPORT_ACCEPTED_ROWS_CHANGED",)
    reasons: list[str] = []
    for leg in fresh_selected_legs:
        row = load_rows.get(leg["provider_event_id"])
        if row is None:
            reasons.append(f"{leg['fixture_identity']}:DIRECT_EVENT_MISSING")
            continue
        expected = {
            "eventId": leg["provider_event_id"],
            "homeTeamName": leg["home_team"],
            "awayTeamName": leg["away_team"],
            "marketId": leg["provider_market_id"],
            "marketName": leg["provider_market_name"],
            "specifier": leg["provider_specifier"],
            "outcomeId": leg["provider_outcome_id"],
            "outcomeName": leg["provider_outcome_name"],
        }
        if any(row[key] != value for key, value in expected.items()):
            reasons.append(f"{leg['fixture_identity']}:DIRECT_PROVIDER_SEMANTICS_CHANGED")
        if row["odds"] != _decimal(leg["decimal_odds"], "fresh priced"):
            reasons.append(f"{leg['fixture_identity']}:DIRECT_PROVIDER_ODDS_CHANGED")
    return tuple(sorted(set(reasons)))


def create_verified_shadow_all_market_share_code(
    *, portfolio: portfolio_module.ShadowPortfolioOptimization, output_dir: Path,
    delay_seconds: float = 0.25,
) -> ShadowAllMarketShareCodeReceipt:
    try:
        rebuilt = portfolio_module.verify_shadow_portfolio_optimization(portfolio)
    except portfolio_module.CurrentShadowPortfolioError as exc:
        raise CurrentShadowAllMarketShareCodeError("Portfolio exact source replay failed") from exc
    if not rebuilt.selected_legs:
        raise CurrentShadowAllMarketShareCodeError("share-code transport requires at least one selected leg")
    now = _now()
    if now < rebuilt.evaluation_time:
        raise CurrentShadowAllMarketShareCodeError("transport time predates Portfolio")
    freshness = _transport_lead_reasons(rebuilt, now)
    if freshness:
        result = _terminal(portfolio=rebuilt, status=STATUS_REPRICE_REQUIRED, reasons=freshness)
        _write(output_dir / "research-shadow-all-market-share-code-receipt.json", result.to_dict())
        return result
    try:
        selections, semantic_receipt, fresh_legs, fallback_events = _fresh_resolve_portfolio(
            rebuilt,
            output_dir=output_dir / "semantic-resolution",
            delay_seconds=delay_seconds,
        )
    except semantic_bridge.SportyBetSemanticShareError as exc:
        result = _terminal(
            portfolio=rebuilt,
            status=STATUS_PROVIDER_CHANGED,
            reasons=(f"SEMANTIC_RESOLUTION_FAILED:{exc}",),
        )
        _write(output_dir / "research-shadow-all-market-share-code-receipt.json", result.to_dict())
        return result
    if not selections:
        result = _terminal(
            portfolio=rebuilt,
            status=STATUS_REPRICE_REQUIRED,
            reasons=("NO_CURRENT_PREDICTION_QUALIFIED_SELECTIONS",),
            semantic_receipt=semantic_receipt,
            fresh_selected_legs=(),
            fallback_events=fallback_events,
        )
        _write(output_dir / "research-shadow-all-market-share-code-receipt.json", result.to_dict())
        return result

    try:
        precreate_rebuilt = portfolio_module.verify_shadow_portfolio_optimization(rebuilt)
    except portfolio_module.CurrentShadowPortfolioError as exc:
        raise CurrentShadowAllMarketShareCodeError(
            "Portfolio exact source replay failed immediately before transport"
        ) from exc
    if precreate_rebuilt.canonical_sha256 != rebuilt.canonical_sha256:
        raise CurrentShadowAllMarketShareCodeError(
            "Portfolio identity changed on immediate pre-transport replay"
        )
    precreate_now = _now()
    if precreate_now < now:
        raise CurrentShadowAllMarketShareCodeError(
            "transport clock moved backwards during semantic resolution"
        )
    precreate_freshness = _transport_lead_reasons(precreate_rebuilt, precreate_now)
    if precreate_freshness:
        result = _terminal(
            portfolio=precreate_rebuilt,
            status=STATUS_REPRICE_REQUIRED,
            reasons=precreate_freshness,
            semantic_receipt=semantic_receipt,
            fresh_selected_legs=fresh_legs,
            fallback_events=fallback_events,
        )
        _write(output_dir / "research-shadow-all-market-share-code-receipt.json", result.to_dict())
        return result
    rebuilt = precreate_rebuilt
    now = precreate_now

    try:
        transport_receipt = direct_bridge.create_and_roundtrip(
            selections=selections,
            output_dir=output_dir / "transport-roundtrip",
        )
    except direct_bridge.SportyBetDirectShareError as exc:
        result = _terminal(
            portfolio=rebuilt,
            status=STATUS_PROVIDER_CHANGED,
            reasons=(f"CREATE_RELOAD_FAILED:{exc}",),
            semantic_receipt=semantic_receipt,
            fresh_selected_legs=fresh_legs,
            fallback_events=fallback_events,
        )
        _write(output_dir / "research-shadow-all-market-share-code-receipt.json", result.to_dict())
        return result

    roundtrip_reasons = _verify_roundtrip(fresh_legs, transport_receipt)
    if roundtrip_reasons:
        status = STATUS_REPRICE_REQUIRED if all("ODDS_CHANGED" in item for item in roundtrip_reasons) else STATUS_PROVIDER_CHANGED
        result = _terminal(
            portfolio=rebuilt,
            status=status,
            reasons=roundtrip_reasons,
            semantic_receipt=semantic_receipt,
            transport_receipt=transport_receipt,
            fresh_selected_legs=fresh_legs,
            fallback_events=fallback_events,
        )
        _write(output_dir / "research-shadow-all-market-share-code-receipt.json", result.to_dict())
        return result

    share_code = transport_receipt.get("shareCode")
    share_url = transport_receipt.get("shareURL")
    combined_odds = transport_receipt.get("combined_odds")
    if (
        type(share_code) is not str
        or not share_code
        or type(share_url) is not str
        or not share_url.startswith(("http://", "https://"))
        or type(combined_odds) is not str
        or not combined_odds
    ):
        result = _terminal(
            portfolio=rebuilt,
            status=STATUS_PROVIDER_CHANGED,
            reasons=("DIRECT_VERIFIED_RESPONSE_OMITTED_CODE_FIELDS",),
            semantic_receipt=semantic_receipt,
            transport_receipt=transport_receipt,
            fresh_selected_legs=fresh_legs,
            fallback_events=fallback_events,
        )
        _write(output_dir / "research-shadow-all-market-share-code-receipt.json", result.to_dict())
        return result
    fresh_shortfall = rebuilt.requested_target_size - len(fresh_legs)
    status = STATUS_CODE_VERIFIED if fresh_shortfall == 0 else STATUS_CODE_VERIFIED_WITH_SHORTFALL
    result = ShadowAllMarketShareCodeReceipt(
        status=status,
        observed_at=_now(),
        portfolio_sha256=rebuilt.canonical_sha256,
        requested_target_size=rebuilt.requested_target_size,
        portfolio_shortfall=fresh_shortfall,
        selected_leg_count=len(fresh_legs),
        reasons=(),
        semantic_resolution_receipt_sha256=_sha(dict(semantic_receipt)),
        transport_receipt_sha256=_sha(dict(transport_receipt)),
        share_code=share_code,
        share_url=share_url,
        combined_odds=combined_odds,
        fresh_selected_legs=fresh_legs,
        fallback_events=fallback_events,
        exact_create_reload_equality=True,
    )
    _write(output_dir / "research-shadow-all-market-share-code-receipt.json", result.to_dict())
    return result


__all__ = [
    "AUTHORITY",
    "CurrentShadowAllMarketShareCodeError",
    "ShadowAllMarketShareCodeReceipt",
    "STATUS_CODE_VERIFIED",
    "STATUS_CODE_VERIFIED_WITH_SHORTFALL",
    "STATUS_PROVIDER_CHANGED",
    "STATUS_REPRICE_REQUIRED",
    "create_verified_shadow_all_market_share_code",
]
