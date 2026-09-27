from __future__ import annotations

import importlib.util
import socket
import sys
import urllib.request
from pathlib import Path
from types import ModuleType

import pytest

from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_canonical_core_adapter as adapter
from domain import _current_shadow_quote_binding as quote_binding
from domain.current_shadow_runtime_bindings import (
    default_current_shadow_runtime_bindings,
    runtime_bindings_for_context,
)
from scripts import audit_p4_4s_canonical_adapter_bound_context_builder as audit


ROOT = Path(__file__).resolve().parents[1]
P4_4R_FIXTURE_HELPERS = ROOT / "tests/test_p4_4r_shadow_runtime_composition_stabilization.py"
NETWORK_ATTEMPTS: list[str] = []


def _deny_network(*_args, **_kwargs):
    NETWORK_ATTEMPTS.append("socket/http")
    raise AssertionError("P4.4S adapter regression attempted outbound network")


def _p4_4r_helpers() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "p4_4s_p4_4r_retained_fixture_helpers", P4_4R_FIXTURE_HELPERS
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runner_adapter_direct_context_builder_preserves_explicit_binding_and_old_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    NETWORK_ATTEMPTS.clear()
    helpers = _p4_4r_helpers()
    helpers.NETWORK_ATTEMPTS.clear()
    helpers._install_network_sentinel(monkeypatch)
    monkeypatch.setattr(socket.socket, "connect", _deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _deny_network)
    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(urllib.request, "urlopen", _deny_network)

    repo_root, _paths, reconciliation_bundle, reconciled, prior_context, _fresh = (
        helpers._offline_composition(monkeypatch, tmp_path)
    )

    # This is the exact module boundary the runner uses at its direct-context
    # call site; the inputs/evidence fixture itself is offline and synthetic
    # reconciliation/history around retained provider response bytes.
    assert runner.price_module is adapter
    binding = default_current_shadow_runtime_bindings()
    context = runner.price_module.build_current_shadow_price_context_from_reconciliation(
        complete_current_history=prior_context._complete_current_history,
        fixture_identity=prior_context.fixture_identity,
        provider_event_id=prior_context.provider_event_id,
        current_reconciliation_bundle=reconciliation_bundle,
        runtime_bindings=binding,
    )

    assert type(context) is quote_binding.CurrentShadowPriceContext
    assert context.source_context_mode == quote_binding.CURRENT_RECONCILIATION_DIRECT
    assert context._runtime_bindings is binding
    assert context.fixture_identity == prior_context.fixture_identity
    assert context.provider_event_id == prior_context.provider_event_id
    assert context.fixture_reconciliation_sha256 == reconciled.canonical_sha256
    assert context.source_raw_sha256 == prior_context.source_raw_sha256
    assert context.source_manifest_sha256 == prior_context.source_manifest_sha256
    assert context._current_reconciliation_bundle is reconciliation_bundle
    assert adapter.verify_current_shadow_price_context(context).to_dict() == context.to_dict()

    # The old public call shape remains supported and selects the same standard
    # binding semantics when the caller omits the optional binding.
    legacy_call_shape = adapter.build_current_shadow_price_context_from_reconciliation(
        complete_current_history=prior_context._complete_current_history,
        fixture_identity=prior_context.fixture_identity,
        provider_event_id=prior_context.provider_event_id,
        current_reconciliation_bundle=reconciliation_bundle,
    )
    assert legacy_call_shape._runtime_bindings is binding
    assert legacy_call_shape.to_dict() == context.to_dict()
    assert runtime_bindings_for_context(legacy_call_shape) is binding
    assert adapter.verify_current_shadow_price_context(legacy_call_shape).to_dict() == (
        legacy_call_shape.to_dict()
    )

    # Exercise the canonical adapter's actual Price-all and exact bundle replay
    # seams using the same supplied execution binding.
    price_all = runner.price_module.price_all_shadow_fixture(context)
    replayed = runner.price_module.verify_shadow_price_all_bundle(price_all)
    assert replayed.to_dict() == price_all.to_dict()
    assert replayed._context._runtime_bindings is binding
    assert replayed.fixture_reconciliation_sha256 == reconciled.canonical_sha256
    assert repo_root.is_dir()
    assert NETWORK_ATTEMPTS == []
    assert helpers.NETWORK_ATTEMPTS == []


def test_p4_4s_audit_binds_exact_trigger_supersession_and_current_sources() -> None:
    result = audit.audit(ROOT)

    assert result["status"] == "PASS"
    assert result["receipt_sha256"] == audit._verify_self_hash(
        audit._read_json(ROOT, audit.RECEIPT_PATH), "P4.4S receipt"
    )
    assert result["historical_p4_4r_receipt_sha256"] == audit.P4_4R_RECEIPT_SHA256
    assert result["network_provider_share_wager_actions"] == 0
