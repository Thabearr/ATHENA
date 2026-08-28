"""Final current-source Portfolio v3 to direct SportyBet execution boundary.

Only anonymous share-code creation is authorized.  The semantic gate derives
provider-native IDs from current SportyBet event responses; create and reload
must then prove exact semantic, native, specifier, odds, and count equality.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import types
from collections.abc import Mapping, Sequence
from typing import Any
import unicodedata

from domain import portfolio_optimizer_v3_current_provider as portfolio_v3
from scripts import sportybet_direct_share_bridge as direct_bridge
from scripts import sportybet_semantic_share_bridge as semantic_bridge

SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-current-sportybet-accumulator-execution-v1"
PORTFOLIO_V3_CONTRACT_SHA256 = portfolio_v3.EXPECTED_CONTRACT_SHA256
SEMANTIC_INTENT_POLICY_ID = "ONLY_EVENT_TEAMS_MARKET_OUTCOME_AND_EXACT_SPECIFIER_V1"
FINAL_REPLAY_POLICY_ID = "REPLAY_PORTFOLIO_ROUTER_PRICE253_MAPPING252_RECON251_BEFORE_CREATE_V1"
COUNT_POLICY_ID = "ROUTER_OPTIMIZER_INTENT_RESOLVE_CREATE_RELOAD_EXACT_OR_NO_CODE_V1"
ROUNDTRIP_POLICY_ID = "SEMANTIC_NATIVE_SPECIFIER_ODDS_CREATE_RELOAD_EXACT_V1"
SHORTFALL_POLICY_ID = "TARGET_IS_NOT_PADDED_OR_REPLACED_AND_SHORTFALL_RETURNS_NO_CODE_V1"
MINIMUM_LEAD_SECONDS = 120
EXPECTED_CONTRACT_SHA256 = "62d0f48942ca28eb9566f4803deea07e61598732198882cc515cd88c6209d359"

AUTHORITY = types.MappingProxyType({
    "current_portfolio_consumption": True,
    "semantic_intent_adaptation": True,
    "anonymous_share_code_generation": True,
    "direct_sportybet_create_reload": True,
    "third_party_booking_service": False,
    "login": False,
    "cookies": False,
    "wallet": False,
    "staking": False,
    "bet": False,
    "wager_placed": False,
})


class CurrentSportyBetAccumulatorExecutionError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentSportyBetAccumulatorExecutionError("canonical serialization failed") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise CurrentSportyBetAccumulatorExecutionError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "dataset_name": DATASET_NAME,
        "portfolio_v3_contract_sha256": PORTFOLIO_V3_CONTRACT_SHA256,
        "semantic_bridge_schema": "athena-sportybet-semantic-share-gate-v1",
        "direct_bridge_schema": "athena-sportybet-direct-share-proof-v2",
        "semantic_intent_policy_id": SEMANTIC_INTENT_POLICY_ID,
        "final_replay_policy_id": FINAL_REPLAY_POLICY_ID,
        "count_policy_id": COUNT_POLICY_ID,
        "roundtrip_policy_id": ROUNDTRIP_POLICY_ID,
        "shortfall_policy_id": SHORTFALL_POLICY_ID,
        "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
        "authority": dict(AUTHORITY),
    }


def calculate_current_execution_contract_sha256() -> str:
    return _sha(_contract_payload())


def validate_current_execution_contract() -> Mapping[str, str]:
    try:
        portfolio = portfolio_v3.validate_portfolio_optimizer_v3_contract()
    except Exception as exc:
        raise CurrentSportyBetAccumulatorExecutionError("execution dependency validation failed") from exc
    if portfolio["portfolio_optimizer_v3_contract_sha256"] != PORTFOLIO_V3_CONTRACT_SHA256:
        raise CurrentSportyBetAccumulatorExecutionError("Portfolio v3 identity drifted")
    actual = calculate_current_execution_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise CurrentSportyBetAccumulatorExecutionError("execution contract drifted")
    return types.MappingProxyType({
        "current_execution_contract_sha256": actual,
        "portfolio_optimizer_v3_contract_sha256": PORTFOLIO_V3_CONTRACT_SHA256,
    })


def _name_key(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    ascii_text = folded.encode("ascii", "ignore").decode("ascii")
    return "".join(ch.lower() for ch in ascii_text if ch.isalnum())


def _exact_text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise CurrentSportyBetAccumulatorExecutionError(f"{label} must be exact non-empty text")
    return value


def _odds(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise CurrentSportyBetAccumulatorExecutionError(f"{label} odds are missing")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CurrentSportyBetAccumulatorExecutionError(f"{label} odds are invalid") from exc
    if not result.is_finite() or result <= Decimal("1"):
        raise CurrentSportyBetAccumulatorExecutionError(f"{label} odds are invalid")
    return result


@dataclasses.dataclass(frozen=True)
class CurrentSemanticIntent:
    leg_id: str
    fixture_id: str
    router_decision_sha256: str
    optimizer_id: str
    event_id: str
    home_team_name: str
    away_team_name: str
    market_name: str
    outcome_name: str
    specifier: str | None
    quote_sha256: str
    expected_decimal_odds: float
    expected_provider_market_id: str
    expected_provider_outcome_id: str
    current_inventory_sha256: str
    source_raw_sha256: str
    current_mapping_rebind_sha256: str
    current_reconciliation_sha256: str

    def to_bridge_intent(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "homeTeamName": self.home_team_name,
            "awayTeamName": self.away_team_name,
            "marketName": self.market_name,
            "outcomeName": self.outcome_name,
            "specifier": self.specifier,
        }

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["bridge_intent"] = self.to_bridge_intent()
        return value


def _selected_input_by_leg(
    optimization: portfolio_v3.CurrentProviderPortfolioOptimization,
) -> dict[str, portfolio_v3.CurrentProviderPortfolioRouterInput]:
    by_router = {item.router_decision_sha256: item for item in optimization._router_inputs}
    if len(by_router) != len(optimization._router_inputs):
        raise CurrentSportyBetAccumulatorExecutionError("duplicate Router input identity")
    result = {}
    for leg in optimization.selected_legs:
        source = by_router.get(leg.router_decision_sha256)
        if source is None:
            raise CurrentSportyBetAccumulatorExecutionError("selected leg Router source is absent")
        result[leg.leg_id] = source
    return result


def _replay_final_sources(
    optimization: portfolio_v3.CurrentProviderPortfolioOptimization,
    *, now: datetime,
) -> tuple[portfolio_v3.CurrentProviderPortfolioOptimization, dict[str, portfolio_v3.CurrentProviderPortfolioRouterInput]]:
    try:
        rebuilt = portfolio_v3.verify_current_provider_portfolio_optimization(optimization)
    except portfolio_v3.PortfolioOptimizerV3CurrentProviderError as exc:
        raise CurrentSportyBetAccumulatorExecutionError("Portfolio v3 final source replay failed") from exc
    if rebuilt.evaluation_time > now:
        raise CurrentSportyBetAccumulatorExecutionError(
            "execution evaluation_time predates Portfolio v3"
        )
    sources = _selected_input_by_leg(rebuilt)
    seen_events = set()
    for leg in rebuilt.selected_legs:
        source = sources[leg.leg_id]
        try:
            replayed = portfolio_v3.verify_current_provider_portfolio_router_input(source)
        except portfolio_v3.PortfolioOptimizerV3CurrentProviderError as exc:
            raise CurrentSportyBetAccumulatorExecutionError("selected leg current source replay failed") from exc
        if leg.event_id in seen_events:
            raise CurrentSportyBetAccumulatorExecutionError("duplicate selected provider event")
        seen_events.add(leg.event_id)
        decision = replayed.router_decision
        opportunity = decision.selected_opportunity
        if opportunity is None:
            raise CurrentSportyBetAccumulatorExecutionError("selected leg Router opportunity is absent")
        if (
            leg.fixture_id != decision.fixture_id
            or leg.event_id != decision.event_id
            or leg.selected_opportunity_id != opportunity.opportunity_id
            or leg.market_id is not opportunity.market_id
            or leg.outcome_id is not opportunity.outcome_id
            or leg.line != opportunity.line
            or leg.quote_sha256 != opportunity.quote_sha256
            or leg.current_inventory_sha256 != opportunity.current_inventory_sha256
            or leg.source_raw_sha256 != opportunity.source_raw_sha256
            or leg.current_mapping_rebind_sha256 != opportunity.current_mapping_rebind_sha256
            or leg.current_reconciliation_sha256 != opportunity.source_current_reconciliation_sha256
        ):
            raise CurrentSportyBetAccumulatorExecutionError("selected leg ancestry differs from Router/current source")
        age = (now - decision.source_observed_at).total_seconds()
        lead = (decision.kickoff_utc - now).total_seconds()
        if not math.isfinite(age) or age < 0 or age > decision.price_all_evaluation.max_quote_age_seconds:
            raise CurrentSportyBetAccumulatorExecutionError("selected current quote evidence is stale")
        if not math.isfinite(lead) or lead <= max(MINIMUM_LEAD_SECONDS, decision.price_all_evaluation.minimum_lead_seconds):
            raise CurrentSportyBetAccumulatorExecutionError("selected fixture is live or too close to kickoff")
    return rebuilt, sources


def adapt_current_portfolio_to_semantic_intents(
    optimization: portfolio_v3.CurrentProviderPortfolioOptimization,
) -> tuple[CurrentSemanticIntent, ...]:
    if type(optimization) is not portfolio_v3.CurrentProviderPortfolioOptimization:
        raise CurrentSportyBetAccumulatorExecutionError("exact Portfolio v3 optimization is required")
    sources = _selected_input_by_leg(optimization)
    records = []
    for leg in optimization.selected_legs:
        source = sources[leg.leg_id]
        opportunity = source.router_decision.selected_opportunity
        if opportunity is None:
            raise CurrentSportyBetAccumulatorExecutionError("selected opportunity is absent")
        results = tuple(
            result for result in source.router_decision.price_all_evaluation.results
            if result.candidate.candidate_id in {variant.candidate_id for variant in opportunity.variants}
        )
        if not results or any(result.quote is None for result in results):
            raise CurrentSportyBetAccumulatorExecutionError("selected source quote is absent")
        quote = results[0].quote
        if any(_sha(result.quote.to_dict()) != leg.quote_sha256 for result in results):
            raise CurrentSportyBetAccumulatorExecutionError("selected variants differ from exact quote")
        if (
            quote.provider_market_name != leg.provider_market_name
            or quote.provider_outcome_name != leg.provider_outcome_name
            or quote.provider_specifier != leg.provider_specifier
            or quote.provider_market_id != leg.provider_market_id
            or quote.provider_outcome_id != leg.provider_outcome_id
            or not math.isclose(quote.decimal_odds, leg.decimal_odds, rel_tol=0, abs_tol=1e-12)
        ):
            raise CurrentSportyBetAccumulatorExecutionError("portfolio leg differs from source quote semantics")
        records.append(CurrentSemanticIntent(
            leg_id=leg.leg_id,
            fixture_id=leg.fixture_id,
            router_decision_sha256=leg.router_decision_sha256,
            optimizer_id=optimization.optimization_id,
            event_id=leg.event_id,
            home_team_name=source.home_team,
            away_team_name=source.away_team,
            market_name=quote.provider_market_name,
            outcome_name=quote.provider_outcome_name,
            specifier=quote.provider_specifier,
            quote_sha256=leg.quote_sha256,
            expected_decimal_odds=quote.decimal_odds,
            expected_provider_market_id=quote.provider_market_id,
            expected_provider_outcome_id=quote.provider_outcome_id,
            current_inventory_sha256=quote.current_inventory_sha256,
            source_raw_sha256=quote.source_raw_sha256,
            current_mapping_rebind_sha256=quote.current_mapping_rebind_sha256,
            current_reconciliation_sha256=quote.source_current_reconciliation_sha256,
        ))
    return tuple(sorted(records, key=lambda item: (item.fixture_id, item.leg_id)))


def _accepted_row(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CurrentSportyBetAccumulatorExecutionError(f"{label} accepted event is invalid")
    event_id = _exact_text(value.get("eventId"), f"{label} eventId")
    home = _exact_text(value.get("homeTeamName"), f"{label} home")
    away = _exact_text(value.get("awayTeamName"), f"{label} away")
    markets = value.get("markets")
    if type(markets) is not list or len(markets) != 1 or type(markets[0]) is not dict:
        raise CurrentSportyBetAccumulatorExecutionError(f"{label} must have one market")
    market = markets[0]
    outcomes = market.get("outcomes")
    if type(outcomes) is not list or len(outcomes) != 1 or type(outcomes[0]) is not dict:
        raise CurrentSportyBetAccumulatorExecutionError(f"{label} must have one outcome")
    outcome = outcomes[0]
    market_id = market.get("id", market.get("marketId")); outcome_id = outcome.get("id", outcome.get("outcomeId"))
    if market_id is None or outcome_id is None:
        raise CurrentSportyBetAccumulatorExecutionError(f"{label} native IDs are absent")
    market_name = _exact_text(semantic_bridge._market_text(market), f"{label} market")
    outcome_name = _exact_text(semantic_bridge._outcome_text(outcome), f"{label} outcome")
    specifier = market.get("specifier")
    if specifier is not None: specifier = _exact_text(specifier, f"{label} specifier")
    return {
        "eventId": event_id, "homeTeamName": home, "awayTeamName": away,
        "marketId": str(market_id), "marketName": market_name,
        "specifier": specifier, "outcomeId": str(outcome_id),
        "outcomeName": outcome_name, "odds": format(_odds(outcome.get("odds"), label), "f"),
    }


def _verify_resolution(
    intents: Sequence[CurrentSemanticIntent],
    selections: Sequence[Mapping[str, str]],
    semantic_receipt: Mapping[str, Any],
) -> None:
    for field in (
        "sportybet_login_used",
        "sportybet_cookie_used",
        "sportybet_wallet_used",
        "stake_submitted",
        "wager_placed",
    ):
        if semantic_receipt.get(field) is not False:
            raise CurrentSportyBetAccumulatorExecutionError(
                f"semantic resolution safety field {field} must remain false"
            )
    audits = semantic_receipt.get("resolved")
    if type(audits) is not list or len(audits) != len(intents) or len(selections) != len(intents):
        raise CurrentSportyBetAccumulatorExecutionError("semantic resolution count drifted")
    audit_by_event = {row.get("eventId"): row for row in audits if type(row) is dict}
    selection_by_event = {row.get("eventId"): row for row in selections if type(row) is dict}
    if len(audit_by_event) != len(intents) or len(selection_by_event) != len(intents):
        raise CurrentSportyBetAccumulatorExecutionError("semantic resolution event identity drifted")
    for intent in intents:
        audit = audit_by_event.get(intent.event_id); selection = selection_by_event.get(intent.event_id)
        if audit is None or selection is None:
            raise CurrentSportyBetAccumulatorExecutionError("semantic resolution omitted intended event")
        if (
            selection.get("marketId") != intent.expected_provider_market_id
            or selection.get("outcomeId") != intent.expected_provider_outcome_id
            or selection.get("specifier") != intent.specifier
            or audit.get("observed_market_name", "").casefold() != intent.market_name.casefold()
            or audit.get("observed_outcome_name", "").casefold() != intent.outcome_name.casefold()
            or audit.get("observed_specifier") != intent.specifier
            or _odds(audit.get("odds"), "semantic resolution") != Decimal(str(intent.expected_decimal_odds))
        ):
            raise CurrentSportyBetAccumulatorExecutionError("live semantic resolution differs from selected source quote")


def _verify_transport(
    intents: Sequence[CurrentSemanticIntent],
    transport_receipt: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    for field in (
        "sportybet_login_used",
        "sportybet_cookie_used",
        "sportybet_wallet_used",
        "stake_submitted",
        "wager_placed",
    ):
        if transport_receipt.get(field) is not False:
            raise CurrentSportyBetAccumulatorExecutionError(
                f"provider transport safety field {field} must remain false"
            )
    if transport_receipt.get("create_unavailable_outcomes") != 0 or transport_receipt.get("load_unavailable_outcomes") != 0:
        raise CurrentSportyBetAccumulatorExecutionError(
            "provider create/reload contains unavailable outcomes"
        )
    if transport_receipt.get("exact_roundtrip_selection_identity_verified") is not True:
        raise CurrentSportyBetAccumulatorExecutionError("native create/reload round-trip failed")
    create_rows = transport_receipt.get("create_accepted_outcomes"); reload_rows = transport_receipt.get("load_accepted_outcomes")
    if type(create_rows) is not list or type(reload_rows) is not list or len(create_rows) != len(intents) or len(reload_rows) != len(intents):
        raise CurrentSportyBetAccumulatorExecutionError("provider create/reload count drifted")
    if transport_receipt.get("create_accepted_selection_count") != len(intents) or transport_receipt.get("load_accepted_selection_count") != len(intents):
        raise CurrentSportyBetAccumulatorExecutionError("provider accepted count drifted")
    create = {_accepted_row(row, "create")["eventId"]: _accepted_row(row, "create") for row in create_rows}
    reload = {_accepted_row(row, "reload")["eventId"]: _accepted_row(row, "reload") for row in reload_rows}
    if len(create) != len(intents) or len(reload) != len(intents):
        raise CurrentSportyBetAccumulatorExecutionError("provider create/reload duplicate event")
    verified = []
    for intent in intents:
        expected = {
            "eventId": intent.event_id,
            "homeTeamName": intent.home_team_name,
            "awayTeamName": intent.away_team_name,
            "marketId": intent.expected_provider_market_id,
            "marketName": intent.market_name,
            "specifier": intent.specifier,
            "outcomeId": intent.expected_provider_outcome_id,
            "outcomeName": intent.outcome_name,
            "odds": format(Decimal(str(intent.expected_decimal_odds)), "f"),
        }
        create_row = create.get(intent.event_id); reload_row = reload.get(intent.event_id)
        if create_row is None or reload_row is None:
            raise CurrentSportyBetAccumulatorExecutionError("provider round-trip omitted intended event")
        for row in (create_row, reload_row):
            if (
                row["eventId"] != expected["eventId"]
                or _name_key(row["homeTeamName"]) != _name_key(expected["homeTeamName"])
                or _name_key(row["awayTeamName"]) != _name_key(expected["awayTeamName"])
                or row["marketId"] != expected["marketId"]
                or row["marketName"].casefold() != expected["marketName"].casefold()
                or row["specifier"] != expected["specifier"]
                or row["outcomeId"] != expected["outcomeId"]
                or row["outcomeName"].casefold() != expected["outcomeName"].casefold()
                or Decimal(row["odds"]) != Decimal(expected["odds"])
            ):
                raise CurrentSportyBetAccumulatorExecutionError("provider semantic/native/odds round-trip differs from selected intent")
        if create_row != reload_row:
            raise CurrentSportyBetAccumulatorExecutionError("provider create and reload rows differ")
        verified.append(types.MappingProxyType({"eventId": intent.event_id, "expected": expected, "create": create_row, "reload": reload_row, "exact_semantic_native_odds_match": True}))
    return tuple(verified)


@dataclasses.dataclass(frozen=True)
class CurrentSportyBetAccumulatorExecution:
    contract_sha256: str
    evaluation_time: datetime
    requested_fold_count: int
    final_qualified_fold_count: int
    status: str
    shortfall: int
    router_selected_leg_count: int
    router_selection_pool_count: int
    optimizer_qualified_leg_count: int
    semantic_intent_count: int
    semantic_resolution_count: int
    provider_create_selection_count: int
    provider_reload_selection_count: int
    selected_legs: tuple[Mapping[str, Any], ...]
    router_decision_ids: tuple[str, ...]
    optimizer_id: str
    semantic_resolution_receipt: Mapping[str, Any] | None
    provider_transport_receipt: Mapping[str, Any] | None
    exact_roundtrip_verification: tuple[Mapping[str, Any], ...]
    share_code: str | None
    share_url: str | None
    combined_odds: str | float | None
    wager_placed: bool = False

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DATASET_NAME,
            "contract_sha256": self.contract_sha256,
            "evaluation_time": self.evaluation_time.isoformat().replace("+00:00", "Z"),
            "requested_fold_count": self.requested_fold_count,
            "final_qualified_fold_count": self.final_qualified_fold_count,
            "status": self.status, "shortfall": self.shortfall,
            "router_selected_leg_count": self.router_selected_leg_count,
            "router_selection_pool_count": self.router_selection_pool_count,
            "optimizer_qualified_leg_count": self.optimizer_qualified_leg_count,
            "semantic_intent_count": self.semantic_intent_count,
            "semantic_resolution_count": self.semantic_resolution_count,
            "provider_create_selection_count": self.provider_create_selection_count,
            "provider_reload_selection_count": self.provider_reload_selection_count,
            "selected_legs": [dict(item) for item in self.selected_legs],
            "router_decision_ids": list(self.router_decision_ids),
            "optimizer_id": self.optimizer_id,
            "semantic_resolution_receipt": None if self.semantic_resolution_receipt is None else dict(self.semantic_resolution_receipt),
            "provider_transport_receipt": None if self.provider_transport_receipt is None else dict(self.provider_transport_receipt),
            "exact_roundtrip_verification": [dict(item) for item in self.exact_roundtrip_verification],
            "shareCode": self.share_code, "shareURL": self.share_url,
            "combined_odds": self.combined_odds,
            "authority": dict(AUTHORITY), "wager_placed": False,
        }


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_canonical_bytes(dict(payload)) + b"\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _execute(
    optimization: portfolio_v3.CurrentProviderPortfolioOptimization,
    *, output_dir: Path, evaluation_time: datetime, require_live_current: bool,
    delay_seconds: float,
) -> CurrentSportyBetAccumulatorExecution:
    identities = validate_current_execution_contract(); now = _utc(evaluation_time, "evaluation_time")
    if not isinstance(output_dir, Path):
        raise CurrentSportyBetAccumulatorExecutionError("output_dir must be Path")
    if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float)) or not math.isfinite(delay_seconds) or delay_seconds < 0:
        raise CurrentSportyBetAccumulatorExecutionError("delay_seconds must be finite non-negative")
    rebuilt, _ = _replay_final_sources(optimization, now=now)
    if require_live_current and (
        rebuilt.proof_mode != portfolio_v3.router_v3.price_v3.LIVE_CURRENT
        or rebuilt.status != portfolio_v3.STATUS_LIVE
    ):
        raise CurrentSportyBetAccumulatorExecutionError("production execution requires live current ancestry")
    target = rebuilt.requested_target_size; selected_count = len(rebuilt.selected_legs)
    router_count = selected_count
    router_pool_count = sum(1 for audit in rebuilt.route_audits if audit.admitted)
    if rebuilt.shortfall != target - selected_count:
        raise CurrentSportyBetAccumulatorExecutionError("Optimizer shortfall identity drifted")
    router_ids = tuple(sorted(leg.router_decision_sha256 for leg in rebuilt.selected_legs))
    if selected_count < target:
        result = CurrentSportyBetAccumulatorExecution(
            contract_sha256=identities["current_execution_contract_sha256"], evaluation_time=now,
            requested_fold_count=target, final_qualified_fold_count=selected_count,
            status="NO_CODE_SHORTFALL", shortfall=target-selected_count,
            router_selected_leg_count=router_count, router_selection_pool_count=router_pool_count,
            optimizer_qualified_leg_count=selected_count,
            semantic_intent_count=0, semantic_resolution_count=0,
            provider_create_selection_count=0, provider_reload_selection_count=0,
            selected_legs=tuple({"optimizer_leg": leg.to_dict()} for leg in rebuilt.selected_legs),
            router_decision_ids=router_ids, optimizer_id=rebuilt.optimization_id,
            semantic_resolution_receipt=None, provider_transport_receipt=None,
            exact_roundtrip_verification=(), share_code=None, share_url=None, combined_odds=None,
        )
        _atomic_write(output_dir / "current-sportybet-accumulator-execution.json", result.to_dict())
        return result
    intents = adapt_current_portfolio_to_semantic_intents(rebuilt)
    if len(intents) != selected_count:
        raise CurrentSportyBetAccumulatorExecutionError("Optimizer/semantic intent count drifted")
    bridge_intents = tuple(intent.to_bridge_intent() for intent in intents)
    try:
        selections, semantic_receipt = semantic_bridge.resolve_live_intents(
            intents=bridge_intents,
            output_dir=output_dir / "semantic-resolution",
            minimum_lead_seconds=MINIMUM_LEAD_SECONDS,
            delay_seconds=float(delay_seconds),
        )
        _verify_resolution(intents, selections, semantic_receipt)
        transport_receipt = direct_bridge.create_and_roundtrip(
            selections=selections,
            output_dir=output_dir / "transport-roundtrip",
        )
    except (semantic_bridge.SportyBetSemanticShareError, direct_bridge.SportyBetDirectShareError) as exc:
        raise CurrentSportyBetAccumulatorExecutionError("direct SportyBet semantic create/reload failed closed") from exc
    roundtrip = _verify_transport(intents, transport_receipt)
    expected = len(intents)
    if semantic_receipt.get("resolved_count") != expected:
        raise CurrentSportyBetAccumulatorExecutionError("semantic resolution count drifted")
    if transport_receipt.get("selection_count") != expected:
        raise CurrentSportyBetAccumulatorExecutionError("transport selection count drifted")
    share_code = transport_receipt.get("shareCode"); share_url = transport_receipt.get("shareURL")
    if type(share_code) is not str or not share_code or type(share_url) is not str or not share_url:
        raise CurrentSportyBetAccumulatorExecutionError("verified share code/URL is absent")
    by_leg = {intent.leg_id: intent for intent in intents}
    selected_payload = tuple({"optimizer_leg": leg.to_dict(), "semantic_intent": by_leg[leg.leg_id].to_dict()} for leg in rebuilt.selected_legs)
    result = CurrentSportyBetAccumulatorExecution(
        contract_sha256=identities["current_execution_contract_sha256"], evaluation_time=now,
        requested_fold_count=target, final_qualified_fold_count=selected_count,
        status="CODE_VERIFIED", shortfall=0,
        router_selected_leg_count=router_count, router_selection_pool_count=router_pool_count,
        optimizer_qualified_leg_count=selected_count,
        semantic_intent_count=expected, semantic_resolution_count=expected,
        provider_create_selection_count=expected, provider_reload_selection_count=expected,
        selected_legs=selected_payload, router_decision_ids=router_ids,
        optimizer_id=rebuilt.optimization_id,
        semantic_resolution_receipt=semantic_receipt,
        provider_transport_receipt=transport_receipt,
        exact_roundtrip_verification=roundtrip,
        share_code=share_code, share_url=share_url,
        combined_odds=transport_receipt.get("combined_odds"),
    )
    _atomic_write(output_dir / "current-sportybet-accumulator-execution.json", result.to_dict())
    return result


def execute_current_sportybet_accumulator_as_of(
    optimization: portfolio_v3.CurrentProviderPortfolioOptimization,
    *, output_dir: Path, evaluation_time: datetime, delay_seconds: float = 0.0,
) -> CurrentSportyBetAccumulatorExecution:
    return _execute(optimization, output_dir=output_dir, evaluation_time=evaluation_time, require_live_current=False, delay_seconds=delay_seconds)


def execute_current_sportybet_accumulator(
    optimization: portfolio_v3.CurrentProviderPortfolioOptimization,
    *, output_dir: Path, delay_seconds: float = 0.25,
) -> CurrentSportyBetAccumulatorExecution:
    return _execute(optimization, output_dir=output_dir, evaluation_time=_now_utc(), require_live_current=True, delay_seconds=delay_seconds)


__all__ = [name for name in globals() if not name.startswith("_")]
