"""Focused E1 forward-successor authentication tests for PR #457."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import audit_run_01a_durable_admission as e1
from scripts import audit_core_01d_ci_offline_transport_boundary as boundary


@pytest.fixture(scope="module")
def shallow_authenticated_a2_inventory():
    """Authenticate current A2 while forcing its no-ancestor fallback path."""
    original = boundary.historical_objects_available
    boundary.historical_objects_available = lambda *args, **kwargs: False
    try:
        return boundary.authenticate_inventory()
    finally:
        boundary.historical_objects_available = original


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _lf(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n")


def _frozen_identities():
    receipt = e1.build_receipt()
    return {row["path"]: row["lf_sha256"] for row in receipt["source_identities"]}


def _a2_identities(latest):
    return {row["path"]: row["lf_source_sha256"] for row in latest["source_identities"]}


def _copy_sources_and_fixtures(destination: Path):
    for source in e1.SOURCES:
        target = destination / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((e1.ROOT / source).read_bytes())
    for entry in e1.FORWARD_EVOLVED_SOURCES.values():
        fixture = entry["predecessor_fixture"]
        target = destination / fixture
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((e1.ROOT / fixture).read_bytes())


def test_e1_receipt_is_immutable_and_reconstructed_from_predecessor_bytes():
    raw = (e1.ROOT / e1.RECEIPT).read_bytes()
    value = json.loads(raw)
    seal = value.pop("canonical_sha256")

    assert raw == e1.canonical({**value, "canonical_sha256": seal})
    assert raw == e1.canonical(e1.build_receipt())
    assert seal == e1.E1_RECEIPT_SHA256
    assert _sha(e1.canonical(value)) == e1.E1_RECEIPT_SHA256


def test_e1_receipt_mutation_is_rejected(monkeypatch):
    receipt_path = e1.ROOT / e1.RECEIPT
    original_read_bytes = Path.read_bytes
    original = original_read_bytes(receipt_path)
    tampered = original.replace(b'"merge_authorized":false', b'"merge_authorized":true', 1)
    assert tampered != original

    def read_tampered_receipt(path):
        if path == receipt_path:
            return tampered
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_tampered_receipt)
    with pytest.raises(AssertionError, match="E1 immutable receipt identity drift"):
        e1._verify_immutable_receipt()


def test_all_exact_predecessor_fixtures_match_frozen_e1_source_identities():
    frozen = _frozen_identities()
    assert set(e1.FORWARD_EVOLVED_SOURCES) == e1.FORWARD_EVOLVED_SOURCE_PATHS
    assert set(e1.FORWARD_EVOLVED_SOURCES) == {
        "scripts/audit_checkpoint_e_workflows.py",
        "scripts/audit_data_01c_app_store_complete.py",
        "tests/test_core_01d_exact_pr_trigger_disposition_b1.py",
        "scripts/audit_run_01a_durable_admission.py",
        "services/athena_job_service.py",
        "database/run_repository.py",
        "scripts/audit_data_01b_durable_run_state.py",
        "scripts/audit_data_01c_restore_portability.py",
    }

    for source, entry in e1.FORWARD_EVOLVED_SOURCES.items():
        raw = _lf((e1.ROOT / entry["predecessor_fixture"]).read_bytes())
        digest = _sha(raw)
        assert digest == entry["predecessor_lf_sha256"] == frozen[source]


def test_current_successors_match_a2_and_all_other_e1_sources_remain_unchanged(
        monkeypatch, shallow_authenticated_a2_inventory):
    latest = shallow_authenticated_a2_inventory
    current_a2 = _a2_identities(latest)
    assert latest["generation"] >= 119
    assert set(e1.FORWARD_EVOLVED_SOURCES) <= set(current_a2)

    calls = []
    monkeypatch.setattr(
        boundary,
        "authenticate_inventory",
        lambda: calls.append("authenticated A2") or latest,
    )
    successor_paths = e1.authenticate_successor()
    assert calls == ["authenticated A2"]
    assert e1.FORWARD_SUCCESSOR_PATHS <= successor_paths

    frozen = _frozen_identities()
    for path in e1.SOURCES:
        current = _sha(_lf((e1.ROOT / path).read_bytes()))
        if path in e1.FORWARD_EVOLVED_SOURCE_PATHS:
            assert current == current_a2[path]
        else:
            assert current == frozen[path]


def test_unlisted_e1_source_drift_is_rejected(shallow_authenticated_a2_inventory, tmp_path):
    _copy_sources_and_fixtures(tmp_path)
    unlisted = next(path for path in e1.SOURCES if path not in e1.FORWARD_EVOLVED_SOURCE_PATHS)
    changed = tmp_path / unlisted
    changed.write_bytes(changed.read_bytes() + b"\n# unlisted drift\n")

    with pytest.raises(AssertionError, match="unlisted source evidence drift"):
        e1._authenticate_current_sources(
            _frozen_identities(),
            shallow_authenticated_a2_inventory["source_identities"],
            root=tmp_path,
            tracked_paths=e1.FORWARD_EVOLVED_SOURCE_PATHS,
        )


def test_predecessor_fixture_tampering_is_rejected(shallow_authenticated_a2_inventory, tmp_path):
    _copy_sources_and_fixtures(tmp_path)
    fixture = next(iter(e1.FORWARD_EVOLVED_SOURCES.values()))["predecessor_fixture"]
    target = tmp_path / fixture
    target.write_bytes(target.read_bytes() + b"tamper")

    with pytest.raises(AssertionError, match="predecessor fixture identity drift"):
        e1._authenticate_current_sources(
            _frozen_identities(),
            shallow_authenticated_a2_inventory["source_identities"],
            root=tmp_path,
            tracked_paths=e1.FORWARD_EVOLVED_SOURCE_PATHS,
        )


def test_current_source_must_match_its_exact_a2_identity(shallow_authenticated_a2_inventory):
    rows = [dict(row) for row in shallow_authenticated_a2_inventory["source_identities"]]
    path = next(iter(e1.FORWARD_EVOLVED_SOURCES))
    row = next(row for row in rows if row["path"] == path)
    row["lf_source_sha256"] = "0" * 64

    with pytest.raises(AssertionError, match="differs from authenticated A2 bytes"):
        e1._authenticate_current_sources(
            _frozen_identities(),
            rows,
            tracked_paths=e1.FORWARD_EVOLVED_SOURCE_PATHS,
        )


def test_arbitrary_fifth_evolved_source_is_rejected(
        monkeypatch, shallow_authenticated_a2_inventory):
    fifth = next(path for path in e1.SOURCES if path not in e1.FORWARD_EVOLVED_SOURCE_PATHS)
    entry = {
        "predecessor_lf_sha256": _frozen_identities()[fifth],
        "predecessor_fixture": "tests/unreviewed-fifth-predecessor.py.txt",
    }
    monkeypatch.setitem(e1.FORWARD_EVOLVED_SOURCES, fifth, entry)

    with pytest.raises(AssertionError, match="forward source allowlist drift"):
        e1._authenticate_current_sources(
            _frozen_identities(),
            shallow_authenticated_a2_inventory["source_identities"],
            tracked_paths=e1.FORWARD_EVOLVED_SOURCE_PATHS,
        )


def test_missing_a2_row_and_untracked_successor_path_fail_closed(
        shallow_authenticated_a2_inventory):
    latest_rows = [dict(row) for row in shallow_authenticated_a2_inventory["source_identities"]]
    path = next(iter(e1.FORWARD_EVOLVED_SOURCES))
    without_row = [row for row in latest_rows if row["path"] != path]
    with pytest.raises(AssertionError, match="absent from A2 inventory"):
        e1._authenticate_current_sources(
            _frozen_identities(), without_row,
            tracked_paths=e1.FORWARD_EVOLVED_SOURCE_PATHS,
        )

    with pytest.raises(AssertionError, match="is not tracked"):
        e1._authenticate_current_sources(
            _frozen_identities(), latest_rows,
            tracked_paths=e1.FORWARD_EVOLVED_SOURCE_PATHS - {path},
        )


def test_shallow_head_authentication_needs_no_ancestor_objects(
        monkeypatch, shallow_authenticated_a2_inventory):
    latest = shallow_authenticated_a2_inventory
    calls = []
    original_git = boundary.git

    def shallow_git(*args, data=None):
        calls.append(args)
        if args[0] != "ls-files":
            raise AssertionError("E1 successor attempted ancestor Git access: " + repr(args))
        return original_git(*args, data=data)

    monkeypatch.setattr(boundary, "authenticate_inventory", lambda: latest)
    monkeypatch.setattr(boundary, "git", shallow_git)
    assert latest["generation"] >= 119
    e1.authenticate_successor()
    assert calls == [("ls-files", "--", *sorted(e1.FORWARD_EVOLVED_SOURCE_PATHS))]
