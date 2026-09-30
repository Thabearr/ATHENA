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


def test_real_composed_replay(tmp_path):
    value = replay.run_replay(fixture_root=FIXTURES, writable_root=tmp_path)
    assert value["qualification_reconciliation_sha256"] == replay.QUALIFICATION_SHA
    assert value["historical_run_reconciliation_sha256"] == replay.HISTORICAL_SHA
    assert replay.QUALIFICATION_SHA != replay.HISTORICAL_SHA
    assert value["complete_current_history_reconstructed"] is False
    assert value["direct_router_status"] == value["fresh_router_status"] == "SELECTED"
    assert value["fresh_context"]["evaluation_time"] == "2026-09-27T20:04:20.651079Z"
    for field in ("direct_price_all_sha256", "fresh_price_all_sha256", "portfolio_result_sha256"):
        assert len(value[field]) == 64
    assert value["network_attempts"] == value["provider_acquisition_calls"] == value["delivery_calls"] == 0
