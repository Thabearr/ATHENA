from contextlib import contextmanager
import os
from types import SimpleNamespace

import pytest

from domain import current_shadow_fixture_identity_aliases as aliases
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
        # V3 delegates its team-display compatibility to the same explicit,
        # evidence-pinned V2 registry used by the run-16 reconciliation replay.
        assert aliases.team_identity_matches(
            competition="Premier League",
            fotmob_name="Okzhetpes Kokshetau",
            sportybet_name="FC Okzhetpes",
        )

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


def test_run16_recovered_fixtures_reach_nonempty_router_input_with_frozen_quote_seam(
    monkeypatch, tmp_path
):
    """Exercise the complete supported pre-Router seam without acquisition.

    The three fixture/event identities are those admitted from run-16 retained
    evidence.  Every source, history, and quote boundary below is a frozen test
    double; this proves only local wiring, never live quote availability.
    """

    runner = current_daily.runner
    recovered = (
        ("sr:match:69343126", "5204254"),
        ("sr:match:69456602", "5207231"),
        ("sr:match:69456604", "5207232"),
    )
    matched_rows = tuple(
        SimpleNamespace(
            event_id=event_id,
            matched_fotmob_fixture_id=fixture_id,
            disposition=SimpleNamespace(value="MATCHED"),
        )
        for event_id, fixture_id in recovered
    )
    frozen_events = SimpleNamespace(
        rows=matched_rows,
        matched_rows=matched_rows,
        canonical_sha256="a" * 64,
        contract_sha256=reconciliation.EXPECTED_CONTRACT_SHA256,
        fanout_snapshot_sha256="b" * 64,
    )
    execution = SimpleNamespace(
        bootstrap=SimpleNamespace(
            verified_artifact=SimpleNamespace(admission=object()),
            fixtures=(object(), object(), object()),
        ),
        summary=lambda: {"fixture_source": "frozen-run16"},
    )
    snapshot = SimpleNamespace(
        canonical_sha256="c" * 64,
        tournaments=(),
        observations=(),
    )
    frozen_quote = object()
    built_contexts = []

    monkeypatch.setattr(
        runner,
        "_issue_current_fixture_sources",
        lambda **_kwargs: ([(execution, "20260918")], ("20260918",)),
    )
    monkeypatch.setattr(runner, "_source_capture", lambda *_args: (b"{}", {}))
    monkeypatch.setattr(
        runner.reconciliation,
        "capture_current_catalog_fanout_discovery",
        lambda **_kwargs: (tmp_path, snapshot),
    )
    monkeypatch.setattr(
        runner.reconciliation,
        "reconcile_current_events_from_catalog_fanout",
        lambda **_kwargs: frozen_events,
    )
    monkeypatch.setattr(runner, "_legacy_bootstrap_bytes", lambda: b"{}")
    monkeypatch.setattr(
        runner.latest_history,
        "build_current_fotmob_latest_durable_fresh_history_handoff",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        runner.latest_history,
        "sha256_current_fotmob_latest_durable_fresh_history_handoff",
        lambda _history: "d" * 64,
    )

    def build_context(**kwargs):
        built_contexts.append(kwargs)
        return SimpleNamespace(**kwargs, quote_snapshot=frozen_quote)

    def price(context):
        assert context.quote_snapshot is frozen_quote
        return SimpleNamespace(_context=context)

    monkeypatch.setattr(
        runner.price_module,
        "build_current_shadow_price_context_from_reconciliation",
        build_context,
    )
    monkeypatch.setattr(runner.price_module, "price_all_shadow_fixture", price)
    monkeypatch.setattr(
        runner.router_module,
        "route_shadow_price_results",
        lambda priced: SimpleNamespace(
            status=SimpleNamespace(value="NO_BET"),
            priced=priced,
        ),
    )
    monkeypatch.setattr(
        runner.portfolio_module,
        "build_shadow_portfolio_router_input",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(runner, "_runtime_progress_diagnostics", lambda _inputs: {})

    with compat.scoped_current_request_pre_router_compatibility():
        sources = runner._acquire_router_inputs(
            repository_root=tmp_path,
            lineage_main_sha="e" * 40,
        )

    assert sources.reconciled_fixture_count == 3
    assert sources.priced_fixture_count == 3
    assert len(sources.router_inputs) == 3
    assert [
        (context["provider_event_id"], context["fixture_identity"])
        for context in built_contexts
    ] == [
        (event_id, f"FOTMOB:{fixture_id}")
        for event_id, fixture_id in recovered
    ]
