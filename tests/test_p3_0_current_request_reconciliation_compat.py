from contextlib import contextmanager

import pytest

from domain import current_shadow_sportybet_catalog_fanout_reconciliation as reconciliation
from scripts import capture_p3_0_paired_evidence as collector
from scripts import execute_current_shadow_request as current_request
from scripts import p3_0_current_request_reconciliation_compat as compat


def test_scope_uses_exact_supported_current_request_reconciliation_hooks_and_restores():
    proxy = reconciliation.legacy.reviewed
    before = dict(getattr(proxy, "__dict__", {}))

    with compat.scoped_current_request_reconciliation_compatibility():
        assert proxy._match_event is current_request.run199_identity.match_event
        assert proxy._detail_inventory_from_directory is current_request._detail_inventory

    assert dict(getattr(proxy, "__dict__", {})) == before


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
        "scoped_current_request_reconciliation_compatibility",
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
        "scoped_current_request_reconciliation_compatibility",
        scope,
    )
    monkeypatch.setattr(collector, "_unscoped_main", fail)

    with pytest.raises(RuntimeError, match="capture failed"):
        collector.main([])
    assert events == ["enter", "main", "exit"]
