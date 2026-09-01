from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from scripts import execute_current_shadow_all_market as cli


NOW = datetime(2026, 8, 31, 14, 0, tzinfo=timezone.utc)


def _payload(tmp_path):
    return json.loads((tmp_path / cli.PRICE_DIAGNOSTIC_FILENAME).read_text(encoding="utf-8"))


def test_price_stage_diagnostic_tracks_exact_first_fixture_substeps(monkeypatch, tmp_path):
    runner = cli.runner
    context = SimpleNamespace(fixture_identity="FOTMOB:123", provider_event_id="sr:match:456")
    bundle = SimpleNamespace(_context=context)
    decision = object()
    portfolio_input = object()

    monkeypatch.setattr(runner, "_now", lambda: NOW)
    monkeypatch.setattr(
        runner.price_module,
        "build_current_shadow_price_context_from_reconciliation",
        lambda **_kwargs: context,
    )
    monkeypatch.setattr(runner.price_module, "price_all_shadow_fixture", lambda _context: bundle)
    monkeypatch.setattr(runner.router_module, "route_shadow_price_results", lambda _bundle: decision)
    monkeypatch.setattr(
        runner.portfolio_module,
        "build_shadow_portfolio_router_input",
        lambda **_kwargs: portfolio_input,
    )

    originals = cli._install_price_stage_diagnostics(tmp_path)
    try:
        built = runner.price_module.build_current_shadow_price_context_from_reconciliation(
            complete_current_history=object(),
            fixture_identity="FOTMOB:123",
            provider_event_id="sr:match:456",
            current_reconciliation_bundle=object(),
        )
        assert _payload(tmp_path)["stage"] == "CONTEXT_BUILD_COMPLETED"
        priced = runner.price_module.price_all_shadow_fixture(built)
        assert _payload(tmp_path)["stage"] == "PRICE_ALL_COMPLETED"
        routed = runner.router_module.route_shadow_price_results(priced)
        assert routed is decision
        assert _payload(tmp_path)["stage"] == "ROUTER_COMPLETED"
        value = runner.portfolio_module.build_shadow_portfolio_router_input(
            price_all_bundle=priced,
            router_decision=routed,
        )
        assert value is portfolio_input
        payload = _payload(tmp_path)
        assert payload["stage"] == "PORTFOLIO_INPUT_COMPLETED"
        assert payload["fixture_index"] == 1
        assert payload["fixture_identity"] == "FOTMOB:123"
        assert payload["provider_event_id"] == "sr:match:456"
        assert payload["wager_placed"] is False
    finally:
        (
            runner.price_module.build_current_shadow_price_context_from_reconciliation,
            runner.price_module.price_all_shadow_fixture,
            runner.router_module.route_shadow_price_results,
            runner.portfolio_module.build_shadow_portfolio_router_input,
        ) = originals


def test_price_stage_diagnostic_leaves_started_stage_when_operation_does_not_complete(
    monkeypatch, tmp_path
):
    runner = cli.runner
    context = SimpleNamespace(fixture_identity="FOTMOB:123", provider_event_id="sr:match:456")

    monkeypatch.setattr(runner, "_now", lambda: NOW)
    monkeypatch.setattr(
        runner.price_module,
        "build_current_shadow_price_context_from_reconciliation",
        lambda **_kwargs: context,
    )
    monkeypatch.setattr(
        runner.price_module,
        "price_all_shadow_fixture",
        lambda _context: (_ for _ in ()).throw(RuntimeError("synthetic stall boundary")),
    )

    originals = cli._install_price_stage_diagnostics(tmp_path)
    try:
        built = runner.price_module.build_current_shadow_price_context_from_reconciliation(
            complete_current_history=object(),
            fixture_identity="FOTMOB:123",
            provider_event_id="sr:match:456",
            current_reconciliation_bundle=object(),
        )
        with pytest.raises(RuntimeError, match="synthetic stall boundary"):
            runner.price_module.price_all_shadow_fixture(built)
        payload = _payload(tmp_path)
        assert payload["stage"] == "PRICE_ALL_STARTED"
        assert payload["fixture_index"] == 1
        assert payload["wager_placed"] is False
    finally:
        (
            runner.price_module.build_current_shadow_price_context_from_reconciliation,
            runner.price_module.price_all_shadow_fixture,
            runner.router_module.route_shadow_price_results,
            runner.portfolio_module.build_shadow_portfolio_router_input,
        ) = originals
