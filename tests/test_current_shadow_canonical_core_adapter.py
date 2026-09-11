from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_canonical_core_adapter as adapter


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "domain/current_shadow_all_market_runner.py"


def test_shadow_adapter_resolves_exact_source_controlled_five_component_core() -> None:
    adapter.clear_shadow_canonical_core_cache()
    bindings = adapter.resolve_shadow_canonical_core()

    assert bindings.authority_profile == "SHADOW"
    assert bindings.share_code_generation is True
    assert {
        record.responsibility_id: record.component_id for record in bindings.records
    } == dict(adapter.EXPECTED_COMPONENTS)
    assert all(
        record.allowed_profiles == ("SHADOW",) and record.main_authority is False
        for record in bindings.records
    )

    summary = adapter.canonical_core_summary()
    assert summary["authority_profile"] == "SHADOW"
    assert summary["component_ids"] == dict(adapter.EXPECTED_COMPONENTS)
    assert summary["main_authority"] is False
    assert summary["wager_placed"] is False


def test_runner_imports_one_p2_1_adapter_not_direct_shadow_stage_wrappers() -> None:
    tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
    domain_members: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "domain":
            domain_members.update(alias.name for alias in node.names)

    assert "current_shadow_canonical_core_adapter" in domain_members
    assert "current_shadow_all_market_price_all" not in domain_members
    assert "current_shadow_all_market_router" not in domain_members
    assert "current_shadow_all_market_portfolio" not in domain_members
    assert runner.price_module is adapter
    assert runner.router_module is adapter
    assert runner.portfolio_module is adapter


def test_stage_compatibility_calls_are_guarded_by_exact_canonical_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    class FakeBindings:
        authority_profile = "SHADOW"
        share_code_generation = True

        def record_for(self, responsibility_id: str):
            seen.append(responsibility_id)
            return SimpleNamespace(
                component_id=adapter.EXPECTED_COMPONENTS[responsibility_id],
                allowed_profiles=("SHADOW",),
                main_authority=False,
            )

    monkeypatch.setattr(adapter, "resolve_shadow_canonical_core", lambda: FakeBindings())

    price_result = object()
    route_result = object()
    portfolio_input = object()
    portfolio_result = object()

    monkeypatch.setattr(
        adapter._legacy_price, "price_all_shadow_fixture", lambda value: price_result
    )
    monkeypatch.setattr(
        adapter._legacy_router, "route_shadow_price_results", lambda value: route_result
    )
    monkeypatch.setattr(
        adapter._legacy_portfolio,
        "build_shadow_portfolio_router_input",
        lambda **kwargs: portfolio_input,
    )
    monkeypatch.setattr(
        adapter._legacy_portfolio,
        "optimize_shadow_portfolio",
        lambda values, **kwargs: portfolio_result,
    )

    assert adapter.price_all_shadow_fixture(object()) is price_result
    assert adapter.route_shadow_price_results(object()) is route_result
    assert (
        adapter.build_shadow_portfolio_router_input(
            price_all_bundle=object(), router_decision=object()
        )
        is portfolio_input
    )
    assert (
        adapter.optimize_shadow_portfolio((), target_size=25, evaluation_time=object())
        is portfolio_result
    )
    assert seen == [
        "price_all_and_de_vig",
        "market_router",
        "portfolio_optimizer",
        "portfolio_optimizer",
    ]


def test_portfolio_reconciliation_monkeypatch_seam_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = adapter._legacy_portfolio.reconciliation
    replacement = object()
    observed: list[object] = []

    class FakeBindings:
        def record_for(self, responsibility_id: str):
            return SimpleNamespace(
                component_id=adapter.EXPECTED_COMPONENTS[responsibility_id],
                allowed_profiles=("SHADOW",),
                main_authority=False,
            )

    monkeypatch.setattr(adapter, "resolve_shadow_canonical_core", lambda: FakeBindings())
    monkeypatch.setattr(adapter, "reconciliation", replacement)

    def legacy(**kwargs):
        observed.append(adapter._legacy_portfolio.reconciliation)
        return "ok"

    monkeypatch.setattr(
        adapter._legacy_portfolio, "build_shadow_portfolio_router_input", legacy
    )
    assert (
        adapter.build_shadow_portfolio_router_input(
            price_all_bundle=object(), router_decision=object()
        )
        == "ok"
    )
    assert observed == [replacement]
    assert adapter._legacy_portfolio.reconciliation is original


def test_core_resolution_failure_blocks_provider_acquisition_and_writes_fail_closed_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    called = {"acquire": 0}

    monkeypatch.setattr(runner, "_git_head", lambda _root: "1" * 40)
    monkeypatch.setattr(runner, "_expected_lineage_main_sha", lambda: "2" * 40)

    def fail_core():
        raise adapter.CurrentShadowCanonicalCoreAdapterError("synthetic drift")

    def acquire(**_kwargs):
        called["acquire"] += 1
        raise AssertionError("provider acquisition must not run after core failure")

    monkeypatch.setattr(adapter, "resolve_shadow_canonical_core", fail_core)
    monkeypatch.setattr(runner, "_acquire_router_inputs", acquire)

    receipt = runner.execute_current_shadow_all_market(
        target_size=25, output_dir=tmp_path
    )
    assert called["acquire"] == 0
    assert receipt.status == runner.STATUS_SOURCE_INCOMPLETE
    assert receipt.share_code is None
    assert receipt.share_url is None
    assert receipt.shortfall == 25
    assert receipt.to_dict()["wager_placed"] is False
    assert any(
        "CurrentShadowCanonicalCoreAdapterError" in reason
        for reason in receipt.reasons
    )


def test_adapter_has_no_main_or_sensitive_authority() -> None:
    assert adapter.AUTHORITY["main_authority"] is False
    assert adapter.AUTHORITY["automatic_promotion"] is False
    for key in ("login", "cookies", "wallet", "staking", "bet", "wager_placed"):
        assert adapter.AUTHORITY[key] is False
