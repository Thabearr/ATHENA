from contextlib import contextmanager
import os

import pytest

from domain import current_shadow_fixture_identity_v2 as stable_identity
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as reconciliation
from scripts import capture_p3_0_paired_evidence as collector
from scripts import execute_current_shadow_all_market as all_market_cli
from scripts import execute_current_shadow_daily as current_daily
from scripts import execute_current_shadow_request as current_request
from scripts import p3_0_current_request_reconciliation_compat as compat


def _restore_worker_env(value):
    if value is None:
        os.environ.pop(all_market_cli.WORKER_ENV, None)
    else:
        os.environ[all_market_cli.WORKER_ENV] = value


def test_scope_uses_full_supported_request_and_daily_pre_router_stack_and_restores():
    proxy = reconciliation.legacy.reviewed
    proxy_before = dict(getattr(proxy, "__dict__", {}))
    stable_match_before = stable_identity.match_event
    quote_builder_before = current_daily.quote_replay.live.build_live_event_quote_inventory
    xg_before = current_request.xg_fallback.binding._research_xg_from_validated_current_history
    worker_before = os.environ.get(all_market_cli.WORKER_ENV)

    with compat.scoped_current_request_pre_router_compatibility():
        # Request-wrapper compatibility.
        assert proxy._match_event is current_request.run199_identity.match_event
        assert proxy._detail_inventory_from_directory is current_request._detail_inventory
        assert (
            current_request.xg_fallback.binding._research_xg_from_validated_current_history
            is not xg_before
        )

        # Daily-worker compatibility that PR #369 had not installed.
        assert stable_identity.match_event is current_daily.identity_recovery.match_event
        assert (
            current_daily.quote_replay.live.build_live_event_quote_inventory
            is current_daily.quote_replay.tolerant.build_shadow_live_event_quote_inventory
        )
        assert os.environ.get(all_market_cli.WORKER_ENV) == "1"

    assert dict(getattr(proxy, "__dict__", {})) == proxy_before
    assert stable_identity.match_event is stable_match_before
    assert current_daily.quote_replay.live.build_live_event_quote_inventory is quote_builder_before
    assert (
        current_request.xg_fallback.binding._research_xg_from_validated_current_history
        is xg_before
    )
    assert os.environ.get(all_market_cli.WORKER_ENV) == worker_before


def test_scope_restores_every_layer_when_body_raises():
    proxy = reconciliation.legacy.reviewed
    proxy_before = dict(getattr(proxy, "__dict__", {}))
    stable_match_before = stable_identity.match_event
    quote_builder_before = current_daily.quote_replay.live.build_live_event_quote_inventory
    xg_before = current_request.xg_fallback.binding._research_xg_from_validated_current_history
    worker_before = os.environ.get(all_market_cli.WORKER_ENV)

    with pytest.raises(RuntimeError, match="stop inside scope"):
        with compat.scoped_current_request_pre_router_compatibility():
            raise RuntimeError("stop inside scope")

    assert dict(getattr(proxy, "__dict__", {})) == proxy_before
    assert stable_identity.match_event is stable_match_before
    assert current_daily.quote_replay.live.build_live_event_quote_inventory is quote_builder_before
    assert (
        current_request.xg_fallback.binding._research_xg_from_validated_current_history
        is xg_before
    )
    assert os.environ.get(all_market_cli.WORKER_ENV) == worker_before


def test_scope_delegates_to_existing_reviewed_installers_in_supported_order(monkeypatch):
    events = []
    sentinel_proxy = object()
    sentinel_previous = {"before": object()}
    sentinel_xg = object()
    sentinel_identity = object()
    sentinel_quote = object()

    monkeypatch.setattr(
        current_request,
        "_install_reconciliation_compatibility",
        lambda: events.append("request-reconciliation-install") or (
            sentinel_proxy,
            sentinel_previous,
        ),
    )
    monkeypatch.setattr(
        current_request,
        "_restore_reconciliation_compatibility",
        lambda proxy, previous: events.append(
            ("request-reconciliation-restore", proxy, previous)
        ),
    )
    monkeypatch.setattr(
        current_request.xg_fallback,
        "install",
        lambda: events.append("xg-install") or sentinel_xg,
    )
    monkeypatch.setattr(
        current_request.xg_fallback,
        "restore",
        lambda hooks: events.append(("xg-restore", hooks)),
    )
    monkeypatch.setattr(
        current_daily.identity_recovery,
        "install",
        lambda module: events.append(("identity-install", module)) or sentinel_identity,
    )
    monkeypatch.setattr(
        current_daily.identity_recovery,
        "restore",
        lambda module, hooks: events.append(("identity-restore", module, hooks)),
    )
    monkeypatch.setattr(
        current_daily.quote_replay,
        "install",
        lambda: events.append("quote-install") or sentinel_quote,
    )
    monkeypatch.setattr(
        current_daily.quote_replay,
        "restore",
        lambda original: events.append(("quote-restore", original)),
    )
    worker_before = os.environ.get(all_market_cli.WORKER_ENV)
    try:
        with compat.scoped_current_request_pre_router_compatibility():
            events.append("body")
    finally:
        _restore_worker_env(worker_before)

    assert events == [
        "request-reconciliation-install",
        "xg-install",
        ("identity-install", current_daily.runner.reconciliation),
        "quote-install",
        "body",
        ("quote-restore", sentinel_quote),
        ("identity-restore", current_daily.runner.reconciliation, sentinel_identity),
        ("xg-restore", sentinel_xg),
        ("request-reconciliation-restore", sentinel_proxy, sentinel_previous),
    ]


def test_collector_main_enters_and_restores_scope_on_success(monkeypatch):
    events = []

    @contextmanager
    def scope():
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    monkeypatch.setattr(
        collector._request_reconciliation,
        "scoped_current_request_pre_router_compatibility",
        scope,
    )
    monkeypatch.setattr(
        collector,
        "_unscoped_main",
        lambda argv=None: events.append(("main", argv)) or 0,
    )

    assert collector.main(["--fixture-dates", "20260917"]) == 0
    assert events == ["enter", ("main", ["--fixture-dates", "20260917"]), "exit"]


def test_collector_main_restores_scope_when_unscoped_collector_fails(monkeypatch):
    events = []

    @contextmanager
    def scope():
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    def fail(_argv=None):
        events.append("main")
        raise RuntimeError("capture failed")

    monkeypatch.setattr(
        collector._request_reconciliation,
        "scoped_current_request_pre_router_compatibility",
        scope,
    )
    monkeypatch.setattr(collector, "_unscoped_main", fail)

    with pytest.raises(RuntimeError, match="capture failed"):
        collector.main([])
    assert events == ["enter", "main", "exit"]
