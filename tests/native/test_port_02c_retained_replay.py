"""Qualifier-only source/time/authority regression tests (no provider transport)."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from scripts import port_02c_offline_composed_replay as replay
from scripts.port_02c_git_free_launch import sanitized_git_free_path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / replay.FIXTURE_PREFIX
MANIFEST = json.loads((FIXTURES / "fixture-manifest.json").read_bytes())


def test_exact_fixture_manifest():
    assert replay.verify_fixture_manifest(FIXTURES) == MANIFEST


@pytest.mark.parametrize("record", MANIFEST["files"], ids=lambda r: r["staged_path"])
@pytest.mark.parametrize("mutation", ["missing", "one-byte"])
def test_every_retained_member_fails_closed(tmp_path, record, mutation):
    copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, copy)
    path = copy / record["staged_path"]
    if mutation == "missing":
        path.unlink()
    else:
        raw = path.read_bytes()
        path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    with pytest.raises((replay.ReplayError, OSError)):
        replay.verify_fixture_manifest(copy)


def test_manifest_ancestry_mutation_and_extra_file(tmp_path):
    copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, copy)
    (copy / "extra.json").write_bytes(b"{}")
    with pytest.raises(replay.ReplayError):
        replay.verify_fixture_manifest(copy)
    (copy / "extra.json").unlink()
    value = dict(MANIFEST, source_run_head_sha="0" * 40)
    (copy / "fixture-manifest.json").write_bytes(replay.canonical(value))
    with pytest.raises(replay.ReplayError):
        replay.verify_fixture_manifest(copy)


def test_initial_clock_derived_from_verified_initial_metadata():
    from domain import sportybet_live_event_quote_evidence as live
    discovery_value = json.loads((FIXTURES / "source-evidence/current-shadow-sportybet-pc-upcoming-discovery/manifest.json").read_bytes())
    # Real capture manifest parser; actual source replay separately verifies pages.
    initial = {event: live._manifest_from_mapping(json.loads((FIXTURES /
        f"source-evidence/sportybet-live-event-quote-evidence/{cid}/manifest.json").read_bytes()))
        for event, cid in replay.INITIAL_CAPTURES.items()}
    discovery = SimpleNamespace(last_observed_at=datetime.fromisoformat(discovery_value["last_observed_at"].replace("Z", "+00:00")))
    issuance = datetime.fromisoformat(replay.ISSUED_AT.replace("Z", "+00:00"))
    assert replay.derive_initial_evaluation_time(issuance=issuance, discovery=discovery,
        initial_manifests=initial).isoformat() == "2026-09-27T19:48:52.628430+00:00"
    missing = dict(initial)
    missing.pop("sr:match:74297872")
    with pytest.raises(replay.ReplayError):
        replay.derive_initial_evaluation_time(issuance=issuance, discovery=discovery, initial_manifests=missing)
    swapped = dict(initial)
    swapped[replay.EVENT] = live._manifest_from_mapping(json.loads((FIXTURES /
        f"source-evidence/sportybet-live-event-quote-evidence/{replay.FRESH_CAPTURE}/manifest.json").read_bytes()))
    with pytest.raises(replay.ReplayError):
        replay.derive_initial_evaluation_time(issuance=issuance, discovery=discovery, initial_manifests=swapped)
    with pytest.raises(TypeError):
        replay.derive_initial_evaluation_time(issuance=issuance, discovery=discovery,
            initial_manifests=initial, evaluation_time=datetime.now())


def test_network_guard_denies_and_restores_on_exception():
    import socket
    original = socket.create_connection
    with pytest.raises(replay.ReplayError):
        with replay.network_guard() as counters:
            socket.create_connection(("127.0.0.1", 9))
    assert counters["network_attempts"] == 1
    assert socket.create_connection is original


def test_qualifier_rejects_git_before_launch(tmp_path, monkeypatch):
    from scripts import qualify_port_02_native_runtime as qualifier
    monkeypatch.setattr(qualifier.shutil, "which", lambda *a, **k: "git.exe")
    with pytest.raises(qualifier.QualificationError, match="Git"):
        qualifier.qualify(release_root=tmp_path, trusted_manifest_sha256="a" * 64,
            worker_executable=tmp_path / "unused", worker_sha256="b" * 64,
            output_dir=tmp_path / "out", variant="standard")


def test_source_verifier_substitution_rejected(tmp_path, monkeypatch):
    from domain import current_shadow_sportybet_pc_upcoming_reconciliation as pc
    monkeypatch.setattr(pc, "verify_current_pc_upcoming_reconciliation_bundle", lambda v: v)
    with pytest.raises(replay.ReplayError, match="verifier substitution"):
        replay.run_replay(fixture_root=FIXTURES, writable_root=tmp_path)


def test_model_scan_restored_even_on_exception(tmp_path):
    from domain import current_all_market_shadow_probability_settlement as prc
    original = prc.scan_current_fixture_all_markets
    diagnostic = tmp_path / "model-diagnostic/current-shadow-current-asof-xg-diagnostic.json"
    diagnostic.parent.mkdir()
    diagnostic.write_bytes((FIXTURES / "model-diagnostic/current-shadow-current-asof-xg-diagnostic.json").read_bytes())
    with pytest.raises(RuntimeError, match="harness failure"):
        with replay.qualification_model_scan(tmp_path, SimpleNamespace()) as (sentinel, _):
            assert prc.scan_current_fixture_all_markets is not original
            raise RuntimeError("harness failure")
    assert prc.scan_current_fixture_all_markets is original
    with pytest.raises(prc.AllMarketShadowError):
        original(complete_current_history=sentinel, fixture_identity=replay.FIXTURE)


def _qualification_receipt():
    return {
        "replay_scope": replay.REPLAY_SCOPE, "source_run_id": 36345657852,
        "source_artifact_id": 10940728036, "source_artifact_zip_sha256": replay.ZIP_SHA,
        "fixture_manifest_sha256": replay.FIXTURE_MANIFEST_SHA256,
        "qualification_evaluation_time_policy_id": replay.TIME_POLICY_ID,
        "qualification_initial_evaluation_time": "2026-09-27T19:48:52.628430Z",
        "qualification_reconciliation_sha256": replay.QUALIFICATION_SHA,
        "historical_run_reconciliation_sha256": replay.HISTORICAL_SHA,
        "historical_evaluation_time_retained": False,
        "historical_reconciliation_sha_reproduction_required": False,
        "complete_current_history_reconstructed": False,
        "production_model_authority": False, "production_probability_authority": False,
        "source_reconciliation_verifier_mode": "CANONICAL_UNPATCHED",
        "runtime_binding_verifier_mode": "CANONICAL_UNPATCHED",
        "fresh_evaluation_time": "2026-09-27T20:04:20.651079Z",
        "canonical_adapter_source_mode": "INSTALLED_RELEASE",
        "canonical_adapter_registry_resolution": "RESOURCE_RESOLVER_AUTHORITY_REGISTRY",
        "canonical_adapter_registry_sha256": "74e79e216497c2e7f31a51e278251a5c62645e1085d04ebb8712022658f8f109",
        "canonical_adapter_bindings_sha256": "6d39a2721ec482ce92050fa5a4a863ec4f2047c1cea645f2d2e870dc180d52a1",
        "canonical_adapter_owner_ids": {
            "provider_market_semantics": "domain.provider_market_semantics",
            "price_all_and_de_vig": "domain.price_all", "market_router": "domain.market_router",
            "portfolio_optimizer": "domain.portfolio_optimizer",
            "delivery_share_code_transport": "domain.sportybet_share_code",
        },
        "module_relative_registry_required": False,
        "release_managed_registry_present": True,
        "pyinstaller_internal_registry_present": False,
        **{k: "a" * 64 for k in ("direct_context_sha256", "direct_price_all_sha256", "direct_router_sha256",
            "fresh_context_sha256", "fresh_price_all_sha256", "fresh_router_sha256",
            "portfolio_input_sha256", "portfolio_result_sha256")},
    }


@pytest.mark.parametrize("field,value", [
    ("replay_scope", "BINDINGS_SEMANTIC_CHECK"),
    ("qualification_initial_evaluation_time", "2026-09-30T00:00:00Z"),
    ("qualification_initial_evaluation_time", "2026-09-27T19:48:52.628429Z"),
    ("qualification_initial_evaluation_time", "2026-09-27T20:04:20.651079Z"),
    ("qualification_reconciliation_sha256", replay.HISTORICAL_SHA),
    ("qualification_evaluation_time_policy_id", "ARBITRARY_FIXED_TIME"),
    ("complete_current_history_reconstructed", True),
    ("runtime_binding_verifier_mode", "PATCHED"),
    ("canonical_adapter_source_mode", "DEVELOPMENT_CHECKOUT"),
    ("canonical_adapter_registry_resolution", "MODULE_RELATIVE"),
    ("pyinstaller_internal_registry_present", True),
])
def test_receipt_clock_authority_roles_fail_closed(field, value):
    from scripts import audit_port_02_native_runtime as audit
    good = _qualification_receipt()
    audit._check_qualification(good)
    good[field] = value
    with pytest.raises(audit.AuditError):
        audit._check_qualification(good)


@pytest.mark.parametrize("filename", ["git", "git.exe", "git.cmd", "git.bat"])
def test_git_sanitizer_examines_actual_files(tmp_path, filename):
    import os
    bad = tmp_path / "innocent-directory-name"
    good = tmp_path / "contains-git-in-name-but-no-executable"
    bad.mkdir(); good.mkdir()
    (bad / filename).write_bytes(b"not executed")
    result = sanitized_git_free_path(os.pathsep.join([str(bad), str(good)]))
    assert result == str(good)
    assert shutil.which("git", path=result) is None


def test_no_normal_runtime_reachability():
    for directory in ("runtime", "services", "api", "ui"):
        for path in (ROOT / directory).rglob("*.py"):
            assert "port_02c_offline_composed_replay" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("installed_mode", [False, True])
def test_real_composed_replay(tmp_path, monkeypatch, installed_mode):
    class HostClockMustNotBeRead(datetime):
        @classmethod
        def now(cls, *args, **kwargs):
            raise AssertionError("qualification must not consult the host clock")

    # Local qualifier dependency only; no production clock/verifier substitution.
    monkeypatch.setattr(replay, "datetime", HostClockMustNotBeRead)
    pair = {}
    forwarded = []
    if installed_mode:
        import sys
        from scripts import build_dev_bundle
        from runtime.release_identity import verify_installed_release
        from runtime.resources import ResourceResolver
        from domain import current_shadow_canonical_core_adapter as adapter
        root = tmp_path / "installed"
        metadata = build_dev_bundle.build(repo=ROOT, platform_tag="windows" if sys.platform == "win32" else "linux", output=root, freeze=False)
        identity = verify_installed_release(root, metadata["trusted_manifest_sha256"])
        pair = {"release_identity": identity, "resources": ResourceResolver.for_installed(identity)}
        def forbidden(*a, **k):
            raise AssertionError("installed replay used development canonical authority")
        monkeypatch.setattr(adapter._registry, "load_default_registry", forbidden)
        monkeypatch.setattr(adapter._core, "read_tracked_head_blob", forbidden)
        for name in ("price_all_shadow_fixture", "route_shadow_price_results",
                     "build_shadow_portfolio_router_input", "verify_shadow_portfolio_router_input",
                     "optimize_shadow_portfolio"):
            original = getattr(adapter, name)
            def observed(*args, _name=name, _original=original, **kwargs):
                assert kwargs["release_identity"] is identity
                assert kwargs["resources"] is pair["resources"]
                forwarded.append(_name)
                return _original(*args, **kwargs)
            monkeypatch.setattr(adapter, name, observed)
    value = replay.run_replay(fixture_root=FIXTURES, writable_root=tmp_path, **pair)
    assert value["canonical_adapter_source_mode"] == ("INSTALLED_RELEASE" if installed_mode else "DEVELOPMENT_CHECKOUT")
    if installed_mode:
        assert forwarded.count("price_all_shadow_fixture") == 2
        assert forwarded.count("route_shadow_price_results") == 2
        assert "build_shadow_portfolio_router_input" in forwarded
        assert "verify_shadow_portfolio_router_input" in forwarded
        assert "optimize_shadow_portfolio" in forwarded
    assert value["qualification_reconciliation_sha256"] == replay.QUALIFICATION_SHA
    assert value["historical_run_reconciliation_sha256"] == replay.HISTORICAL_SHA
    assert replay.QUALIFICATION_SHA != replay.HISTORICAL_SHA
    assert value["complete_current_history_reconstructed"] is False
    assert value["direct_router_status"] == value["fresh_router_status"] == "SELECTED"
    assert value["fresh_context"]["evaluation_time"] == "2026-09-27T20:04:20.651079Z"
    for field in ("direct_price_all_sha256", "fresh_price_all_sha256", "portfolio_result_sha256"):
        assert len(value[field]) == 64
    assert value["network_attempts"] == value["provider_acquisition_calls"] == value["delivery_calls"] == 0
