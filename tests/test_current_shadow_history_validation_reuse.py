from __future__ import annotations

from types import SimpleNamespace

import pytest

from domain import current_shadow_all_market_runner as runner
from scripts import execute_current_shadow_all_market as cli


MAIN_SHA = "a" * 40


class _Snapshot:
    def __init__(self, key: str, payload: bytes):
        self.key = key
        self.payload_kind = "binary"
        self.succeeded = True
        self.payload = payload


class _Evidence:
    def __init__(self, reads, audit_result_bytes):
        self.expected_main_sha = MAIN_SHA
        self.reads = reads
        self.audit_result_bytes = audit_result_bytes


class _PrefixSource:
    def __init__(
        self,
        *,
        current_bootstrap,
        source_manifest,
        source_raw_json,
        legacy_bootstrap_projection_raw,
        artifact_zip_bytes,
    ):
        self.current_bootstrap = current_bootstrap
        self.source_manifest = source_manifest
        self.source_raw_json = source_raw_json
        self.legacy_bootstrap_projection_raw = legacy_bootstrap_projection_raw
        self.workflow_run_id = 7
        self.artifact_name = "success-20260831T210700Z-run-7.tar.gz"
        self.artifact_zip_bytes = artifact_zip_bytes
        self.artifact_zip_metadata_digest = "sha256:reviewed"


def _restore(originals):
    original_replay, original_success, original_derive = originals
    runner.latest_history._replay_audit_from_evidence = original_replay
    runner.latest_history._success_materials = original_success
    runner.latest_history.prefix._derive = original_derive


def test_worker_reuses_only_successful_exact_lineage_replay(monkeypatch):
    calls = []

    def exact_replay(*, expected_main_sha, reads):
        calls.append((expected_main_sha, reads))
        return {"marker": len(calls)}, {item.key for item in reads}

    monkeypatch.setattr(runner.latest_history, "GitHubReadSnapshot", _Snapshot)
    monkeypatch.setattr(
        runner.latest_history,
        "_replay_audit_from_evidence",
        exact_replay,
    )

    originals = cli._install_history_validation_reuse()
    try:
        reads = (_Snapshot("one", b"same"),)
        first = runner.latest_history._replay_audit_from_evidence(
            expected_main_sha=MAIN_SHA,
            reads=reads,
        )
        second = runner.latest_history._replay_audit_from_evidence(
            expected_main_sha=MAIN_SHA,
            reads=(_Snapshot("one", b"same"),),
        )
        changed = runner.latest_history._replay_audit_from_evidence(
            expected_main_sha=MAIN_SHA,
            reads=(_Snapshot("one", b"changed"),),
        )
    finally:
        _restore(originals)

    assert first == ({"marker": 1}, {"one"})
    assert second == ({"marker": 1}, {"one"})
    assert changed == ({"marker": 2}, {"one"})
    assert len(calls) == 2


def test_worker_does_not_cache_failed_lineage_replay(monkeypatch):
    attempts = 0

    def flaky(*, expected_main_sha, reads):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("first replay failed")
        return {"marker": "verified"}, {item.key for item in reads}

    monkeypatch.setattr(runner.latest_history, "GitHubReadSnapshot", _Snapshot)
    monkeypatch.setattr(runner.latest_history, "_replay_audit_from_evidence", flaky)

    originals = cli._install_history_validation_reuse()
    try:
        reads = (_Snapshot("one", b"same"),)
        with pytest.raises(RuntimeError, match="first replay failed"):
            runner.latest_history._replay_audit_from_evidence(
                expected_main_sha=MAIN_SHA,
                reads=reads,
            )
        result = runner.latest_history._replay_audit_from_evidence(
            expected_main_sha=MAIN_SHA,
            reads=reads,
        )
    finally:
        _restore(originals)

    assert result == ({"marker": "verified"}, {"one"})
    assert attempts == 2


def test_worker_reuses_success_materials_only_for_exact_evidence(monkeypatch):
    calls = []

    def exact_success(evidence):
        calls.append(evidence)
        return (SimpleNamespace(marker=len(calls)),)

    monkeypatch.setattr(runner.latest_history, "GitHubReadSnapshot", _Snapshot)
    monkeypatch.setattr(runner.latest_history, "GitHubActionsLineageEvidenceBundle", _Evidence)
    monkeypatch.setattr(runner.latest_history, "_success_materials", exact_success)

    originals = cli._install_history_validation_reuse()
    try:
        first_evidence = _Evidence(
            (_Snapshot("one", b"same"),),
            b'{"audit":1}\n',
        )
        same_evidence = _Evidence(
            (_Snapshot("one", b"same"),),
            b'{"audit":1}\n',
        )
        changed_evidence = _Evidence(
            (_Snapshot("one", b"same"),),
            b'{"audit":2}\n',
        )
        first = runner.latest_history._success_materials(first_evidence)
        second = runner.latest_history._success_materials(same_evidence)
        changed = runner.latest_history._success_materials(changed_evidence)
    finally:
        _restore(originals)

    assert first is second
    assert first[0].marker == 1
    assert changed[0].marker == 2
    assert len(calls) == 2


def test_worker_reuses_prefix_derive_only_for_same_exact_source_objects(monkeypatch):
    calls = []

    def exact_derive(source):
        calls.append(source)
        return SimpleNamespace(marker=len(calls))

    monkeypatch.setattr(
        runner.latest_history.prefix,
        "CurrentDurableFreshHistoryPrefixSourceBundle",
        _PrefixSource,
    )
    monkeypatch.setattr(runner.latest_history.prefix, "_derive", exact_derive)

    originals = cli._install_history_validation_reuse()
    try:
        bootstrap = object()
        manifest = object()
        raw = bytes(bytearray(b"raw"))
        legacy = bytes(bytearray(b"legacy"))
        artifact = bytes(bytearray(b"artifact"))
        source = _PrefixSource(
            current_bootstrap=bootstrap,
            source_manifest=manifest,
            source_raw_json=raw,
            legacy_bootstrap_projection_raw=legacy,
            artifact_zip_bytes=artifact,
        )
        same = _PrefixSource(
            current_bootstrap=bootstrap,
            source_manifest=manifest,
            source_raw_json=raw,
            legacy_bootstrap_projection_raw=legacy,
            artifact_zip_bytes=artifact,
        )
        changed = _PrefixSource(
            current_bootstrap=bootstrap,
            source_manifest=object(),
            source_raw_json=raw,
            legacy_bootstrap_projection_raw=legacy,
            artifact_zip_bytes=artifact,
        )

        first = runner.latest_history.prefix._derive(source)
        second = runner.latest_history.prefix._derive(same)
        third = runner.latest_history.prefix._derive(changed)
    finally:
        _restore(originals)

    assert first is second
    assert first.marker == 1
    assert third.marker == 2
    assert len(calls) == 2


def test_worker_does_not_cache_failed_prefix_derive(monkeypatch):
    attempts = 0

    def flaky(source):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("first derive failed")
        return SimpleNamespace(marker="verified")

    monkeypatch.setattr(
        runner.latest_history.prefix,
        "CurrentDurableFreshHistoryPrefixSourceBundle",
        _PrefixSource,
    )
    monkeypatch.setattr(runner.latest_history.prefix, "_derive", flaky)

    originals = cli._install_history_validation_reuse()
    try:
        source = _PrefixSource(
            current_bootstrap=object(),
            source_manifest=object(),
            source_raw_json=bytes(bytearray(b"raw")),
            legacy_bootstrap_projection_raw=bytes(bytearray(b"legacy")),
            artifact_zip_bytes=bytes(bytearray(b"artifact")),
        )
        with pytest.raises(RuntimeError, match="first derive failed"):
            runner.latest_history.prefix._derive(source)
        result = runner.latest_history.prefix._derive(source)
    finally:
        _restore(originals)

    assert result.marker == "verified"
    assert attempts == 2
