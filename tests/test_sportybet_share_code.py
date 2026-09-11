from __future__ import annotations

import ast
import dataclasses
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain import current_shadow_all_market_share_code as legacy_shadow
from domain import portfolio_optimizer
from domain import sportybet_share_code as share
from tests.test_current_direct_provider_live_quote_mapping_consumption import EVALUATION
from tests.test_portfolio_optimizer import _canonical_input


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "domain/sportybet_share_code.py"
RUNNER_PATH = ROOT / "domain/current_shadow_all_market_runner.py"


def _portfolio(monkeypatch, *, target_legs: int = 1):
    _source, decision = _canonical_input(monkeypatch)
    return portfolio_optimizer.optimize_portfolio_as_of(
        (decision,),
        target_legs=target_legs,
        evaluation_time=EVALUATION + timedelta(seconds=20),
    )


def _provider_event_row(binding: share.SportyBetProviderBinding) -> dict:
    return {
        "eventId": binding.event_id,
        "homeTeamName": binding.home_team_name,
        "awayTeamName": binding.away_team_name,
        "markets": [{
            "id": binding.provider_market_id,
            "name": binding.provider_market_name,
            "specifier": binding.provider_specifier,
            "outcomes": [{
                "id": binding.provider_outcome_id,
                "name": binding.provider_outcome_name,
                "odds": str(binding.expected_decimal_odds),
            }],
        }],
    }


def _install_success(monkeypatch, bindings, *, transport_mutator=None):
    bindings = tuple(bindings)
    by_event = {item.event_id: item for item in bindings}
    observed = {"semantic_calls": 0, "transport_calls": 0, "bridge_intents": None}

    def resolve_live_intents(*, intents, output_dir, minimum_lead_seconds, delay_seconds):
        observed["semantic_calls"] += 1
        observed["bridge_intents"] = tuple(intents)
        selections = []
        audits = []
        for intent in intents:
            binding = by_event[intent["eventId"]]
            selection = {
                "eventId": binding.event_id,
                "marketId": binding.provider_market_id,
                "outcomeId": binding.provider_outcome_id,
            }
            if binding.provider_specifier is not None:
                selection["specifier"] = binding.provider_specifier
            selections.append(selection)
            audits.append({
                "eventId": binding.event_id,
                "observed_market_name": binding.provider_market_name,
                "observed_outcome_name": binding.provider_outcome_name,
                "observed_specifier": binding.provider_specifier,
                "odds": str(binding.expected_decimal_odds),
            })
        return tuple(selections), {
            "resolved_count": len(bindings),
            "resolved": audits,
            "caller_supplied_market_outcome_ids_accepted": False,
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        }

    def create_and_roundtrip(*, selections, output_dir):
        observed["transport_calls"] += 1
        create = [_provider_event_row(by_event[item["eventId"]]) for item in selections]
        reload = [_provider_event_row(by_event[item["eventId"]]) for item in selections]
        receipt = {
            "selection_count": len(bindings),
            "create_accepted_selection_count": len(bindings),
            "load_accepted_selection_count": len(bindings),
            "create_accepted_outcomes": create,
            "load_accepted_outcomes": reload,
            "create_unavailable_outcomes": 0,
            "load_unavailable_outcomes": 0,
            "exact_roundtrip_selection_identity_verified": True,
            "shareCode": "SYNTHETIC231",
            "shareURL": "https://www.sportybet.com/ng/share/SYNTHETIC231",
            "combined_odds": "17.25",
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        }
        if transport_mutator is not None:
            transport_mutator(receipt)
        return receipt

    monkeypatch.setattr(share.semantic_bridge, "resolve_live_intents", resolve_live_intents)
    monkeypatch.setattr(share.direct_bridge, "create_and_roundtrip", create_and_roundtrip)
    return observed


def test_contract_pins_selected_portfolio_and_non_wager_authority() -> None:
    identities = share.validate_share_code_contract()
    assert identities["canonical_share_code_contract_sha256"] == share.EXPECTED_CONTRACT_SHA256
    assert identities["canonical_portfolio_contract_sha256"] == portfolio_optimizer.EXPECTED_CONTRACT_SHA256
    assert share.AUTHORITY["selected_portfolio_consumption"] is True
    assert share.AUTHORITY["provider_semantic_verification"] is True
    assert share.AUTHORITY["anonymous_share_code_generation"] is True
    assert share.AUTHORITY["provider_create_reload_verification"] is True
    for key in ("source_acquisition", "browser_automation", "login", "cookies", "wallet", "staking", "bet", "wager_placed"):
        assert share.AUTHORITY[key] is False


def test_verified_and_failure_receipts_are_builder_only() -> None:
    with pytest.raises(share.SportyBetShareCodeError, match="builder-only"):
        share.VerifiedShareCode()
    with pytest.raises(share.SportyBetShareCodeError, match="builder-only"):
        share.ShareCodeFailure()


def test_selected_portfolio_exact_binding_and_create_reload_returns_verified_code(monkeypatch, tmp_path) -> None:
    portfolio = _portfolio(monkeypatch)
    bindings = share.build_provider_bindings(portfolio)
    assert len(bindings) == 1
    leg = portfolio.selected_legs[0]
    binding = bindings[0]
    assert binding.selected_portfolio_id == portfolio.selected_portfolio_id
    assert binding.leg_id == leg.leg_id
    assert binding.event_id == leg.event_id
    assert binding.provider_market_id == leg.provider_market_id
    assert binding.provider_outcome_id == leg.provider_outcome_id
    assert binding.provider_specifier == leg.provider_specifier
    assert binding.quote_sha256 == leg.quote_sha256
    assert binding.source_raw_sha256 == leg.source_raw_sha256
    assert binding.current_reconciliation_sha256 == leg.current_reconciliation_sha256

    observed = _install_success(monkeypatch, bindings)
    result = share.create_verified_share_code_as_of(
        portfolio,
        bindings,
        output_dir=tmp_path,
        evaluation_time=EVALUATION + timedelta(seconds=30),
    )
    assert type(result) is share.VerifiedShareCode
    assert result.verified is True
    assert result.share_code == "SYNTHETIC231"
    assert result.selected_leg_count == 1
    assert result.shortfall == 0
    assert result.to_dict()["exact_create_reload_equality"] is True
    assert result.to_dict()["wager_placed"] is False
    assert observed["semantic_calls"] == observed["transport_calls"] == 1
    assert not ({"marketId", "outcomeId", "odds", "selections", "slip"} & set(observed["bridge_intents"][0]))
    assert (tmp_path / share.RECEIPT_FILENAME).is_file()


def test_tampered_provider_binding_fails_before_any_provider_bridge(monkeypatch, tmp_path) -> None:
    portfolio = _portfolio(monkeypatch)
    binding = share.build_provider_bindings(portfolio)[0]
    tampered = dataclasses.replace(binding, provider_market_id="tampered")
    monkeypatch.setattr(share.semantic_bridge, "resolve_live_intents", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("provider semantic bridge must not run")))
    monkeypatch.setattr(share.direct_bridge, "create_and_roundtrip", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("provider transport must not run")))
    with pytest.raises(share.SportyBetShareCodeError, match="provider bindings differ"):
        share.create_verified_share_code_as_of(
            portfolio,
            (tampered,),
            output_dir=tmp_path,
            evaluation_time=EVALUATION + timedelta(seconds=30),
        )


def test_stale_selected_portfolio_returns_typed_reprice_before_provider_bridge(monkeypatch, tmp_path) -> None:
    portfolio = _portfolio(monkeypatch)
    bindings = share.build_provider_bindings(portfolio)
    monkeypatch.setattr(share.semantic_bridge, "resolve_live_intents", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("provider semantic bridge must not run")))
    monkeypatch.setattr(share.direct_bridge, "create_and_roundtrip", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("provider transport must not run")))
    result = share.create_verified_share_code_as_of(
        portfolio,
        bindings,
        output_dir=tmp_path,
        evaluation_time=EVALUATION + timedelta(seconds=1000),
    )
    assert type(result) is share.ShareCodeFailure
    assert result.failure_code is share.ShareCodeFailureCode.REPRICE_REQUIRED
    assert result.verified is False
    assert result.share_code is None
    assert any("STALE" in reason or "KICKOFF" in reason for reason in result.reasons)


def test_semantic_mismatch_is_typed_provider_changed_and_never_creates_code(monkeypatch, tmp_path) -> None:
    portfolio = _portfolio(monkeypatch)
    bindings = share.build_provider_bindings(portfolio)
    binding = bindings[0]

    def bad_semantics(**_kwargs):
        selection = {"eventId": binding.event_id, "marketId": binding.provider_market_id, "outcomeId": binding.provider_outcome_id}
        return (selection,), {
            "resolved_count": 1,
            "resolved": [{
                "eventId": binding.event_id,
                "observed_market_name": binding.provider_market_name,
                "observed_outcome_name": "DIFFERENT OUTCOME",
                "observed_specifier": binding.provider_specifier,
                "odds": str(binding.expected_decimal_odds),
            }],
            "caller_supplied_market_outcome_ids_accepted": False,
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        }

    monkeypatch.setattr(share.semantic_bridge, "resolve_live_intents", bad_semantics)
    monkeypatch.setattr(share.direct_bridge, "create_and_roundtrip", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("create must not run after semantic mismatch")))
    result = share.create_verified_share_code_as_of(
        portfolio,
        bindings,
        output_dir=tmp_path,
        evaluation_time=EVALUATION + timedelta(seconds=30),
    )
    assert type(result) is share.ShareCodeFailure
    assert result.failure_code is share.ShareCodeFailureCode.PROVIDER_CHANGED
    assert result.stage == "SEMANTIC_RESOLUTION"
    assert result.share_code is None


def test_create_reload_mismatch_is_typed_failure_with_no_code(monkeypatch, tmp_path) -> None:
    portfolio = _portfolio(monkeypatch)
    bindings = share.build_provider_bindings(portfolio)

    def mutate(receipt):
        receipt["load_accepted_outcomes"][0]["markets"][0]["outcomes"][0]["id"] = "different"

    _install_success(monkeypatch, bindings, transport_mutator=mutate)
    result = share.create_verified_share_code_as_of(
        portfolio,
        bindings,
        output_dir=tmp_path,
        evaluation_time=EVALUATION + timedelta(seconds=30),
    )
    assert type(result) is share.ShareCodeFailure
    assert result.failure_code is share.ShareCodeFailureCode.PROVIDER_CHANGED
    assert result.stage == "CREATE_RELOAD_VERIFICATION"
    assert result.share_code is None
    assert result.to_dict()["exact_create_reload_equality"] is False


def _synthetic_portfolio_231() -> SimpleNamespace:
    selected = []
    portfolio_id = "a" * 64
    for index in range(14):
        selected.append(SimpleNamespace(
            leg_id=f"{index + 1:064x}",
            canonical_router_decision_sha256=f"{1000 + index:064x}",
            source_router_v3_decision_sha256=f"{2000 + index:064x}",
            fixture_id=f"fixture-{index + 1}",
            event_id=f"event-{index + 1}",
            home_team=f"Home {index + 1}",
            away_team=f"Away {index + 1}",
            provider_market_id=f"market-{index + 1}",
            provider_market_name=f"Market {index + 1}",
            provider_specifier=None,
            provider_outcome_id=f"outcome-{index + 1}",
            provider_outcome_name=f"Outcome {index + 1}",
            decimal_odds=1.20 + index / 100,
            quote_sha256=f"{3000 + index:064x}",
            current_inventory_sha256=f"{4000 + index:064x}",
            source_raw_sha256=f"{5000 + index:064x}",
            current_mapping_rebind_sha256=f"{6000 + index:064x}",
            current_mapping_contract_sha256=f"{7000 + index:064x}",
            current_reconciliation_sha256=f"{8000 + index:064x}",
        ))
    return SimpleNamespace(
        selected_portfolio_id=portfolio_id,
        selected_legs=tuple(selected),
        target_legs=25,
        selected_count=14,
        shortfall=11,
        evaluation_time=EVALUATION,
        proof_mode=portfolio_optimizer.AS_OF_REPLAY,
        _require_live_current=False,
        _router_inputs=(),
    )


def test_run_231_equivalent_synthetic_14_of_25_verifies_exact_code_with_shortfall(monkeypatch, tmp_path) -> None:
    portfolio = _synthetic_portfolio_231()
    monkeypatch.setattr(portfolio_optimizer, "verify_selected_portfolio", lambda value: value)
    monkeypatch.setattr(share, "validate_share_code_contract", lambda: {"canonical_share_code_contract_sha256": share.EXPECTED_CONTRACT_SHA256})
    monkeypatch.setattr(share, "_freshness_reasons", lambda _portfolio, _now: ((), share.MINIMUM_LEAD_SECONDS))
    bindings = share.build_provider_bindings(portfolio)
    assert len(bindings) == 14
    observed = _install_success(monkeypatch, bindings)
    result = share.create_verified_share_code_as_of(
        portfolio,
        bindings,
        output_dir=tmp_path,
        evaluation_time=EVALUATION + timedelta(seconds=30),
    )
    assert type(result) is share.VerifiedShareCode
    assert result.status == "VERIFIED_SHARE_CODE_WITH_SHORTFALL"
    assert result.target_legs == 25
    assert result.selected_leg_count == 14
    assert result.shortfall == 11
    assert len(result.exact_roundtrip_verification) == 14
    assert all(item["exact_semantic_native_odds_match"] is True for item in result.exact_roundtrip_verification)
    assert result.share_code == "SYNTHETIC231"
    assert observed["semantic_calls"] == observed["transport_calls"] == 1
    assert result.to_dict()["wager_placed"] is False


def test_current_shadow_compatibility_entrypoint_delegates_existing_reviewed_path(monkeypatch, tmp_path) -> None:
    receipt = SimpleNamespace(
        status=share.STATUS_CODE_VERIFIED_WITH_SHORTFALL,
        to_dict=lambda: {
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        },
    )
    called = {}

    def legacy(**kwargs):
        called.update(kwargs)
        return receipt

    monkeypatch.setattr(legacy_shadow, "create_verified_shadow_all_market_share_code", legacy)
    result = share.create_verified_shadow_all_market_share_code(
        portfolio="legacy-shadow-portfolio",
        output_dir=tmp_path,
        delay_seconds=0.0,
    )
    assert result is receipt
    assert called["portfolio"] == "legacy-shadow-portfolio"
    assert called["output_dir"] == tmp_path
    assert called["delay_seconds"] == 0.0


def test_canonical_service_has_no_browser_login_wallet_stake_or_wager_imports() -> None:
    tree = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            imports.update(f"{node.module}.{alias.name}" for alias in node.names)
    assert "domain.portfolio_optimizer" in imports
    assert "domain.current_sportybet_accumulator_execution" in imports
    assert "scripts.sportybet_direct_share_bridge" in imports
    assert "scripts.sportybet_semantic_share_bridge" in imports
    forbidden = ("bookie_automator", "selenium", "playwright", "login", "wallet", "staking", "wager")
    assert not any(token in module.casefold() for module in imports for token in forbidden)


def test_current_shadow_runner_routes_delivery_through_canonical_service_module() -> None:
    text = RUNNER_PATH.read_text(encoding="utf-8")
    assert "from domain import sportybet_share_code as share_module" in text
    assert "from domain import current_shadow_all_market_share_code as share_module" not in text
    assert "share_module.create_verified_shadow_all_market_share_code(" in text
