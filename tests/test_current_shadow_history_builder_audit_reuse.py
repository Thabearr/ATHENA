from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import current_shadow_history_builder_audit_reuse as reuse
from scripts import execute_current_shadow_daily as daily


MAIN_SHA = "a" * 40
OTHER_MAIN_SHA = "b" * 40


class _Snapshot:
    def __init__(
        self,
        key: str,
        payload: bytes,
        *,
        payload_kind: str = "binary",
        succeeded: bool = True,
    ) -> None:
        self.key = key
        self.payload = payload
        self.payload_kind = payload_kind
        self.succeeded = succeeded


class _Recorder:
    def __init__(self, reads=()) -> None:
        self.reads = tuple(reads)

    def freeze(self):
        return self.reads


def _canonical(value) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _parse_object(raw: bytes, _label: str):
    return json.loads(raw)


def _fake_latest(*, payload: bytes, fail_live: bool = False):
    state = {"live": 0, "fallback": 0}
    fake = SimpleNamespace()
    fake.GitHubReadSnapshot = _Snapshot
    fake._ReadRecorder = _Recorder
    fake._canonical = _canonical
    fake._parse_object = _parse_object

    def run_projected_audit(*, expected_main_sha, **_kwargs):
        state["live"] += 1
        if fail_live:
            raise RuntimeError("live audit failed")
        return {
            "expected_main_sha": expected_main_sha,
            "marker": state["live"],
        }

    def replay_audit(*, expected_main_sha, reads):
        state["fallback"] += 1
        return (
            {
                "expected_main_sha": expected_main_sha,
                "fallback": state["fallback"],
            },
            {item.key for item in reads},
        )

    def build_with_readers(*, expected_main_sha, **_kwargs):
        audit = fake._run_reviewed_projected_audit(
            expected_main_sha=expected_main_sha
        )
        recorder = fake._ReadRecorder(
            (
                _Snapshot("artifact_zip:7", payload),
                _Snapshot("main_ref", b'{"sha":"main"}\n', payload_kind="json"),
            )
        )
        reads = recorder.freeze()
        # GitHubActionsLineageEvidenceBundle.__post_init__ clones each snapshot
        # with dataclasses.replace, preserving the exact immutable payload bytes.
        cloned = tuple(
            _Snapshot(
                item.key,
                item.payload,
                payload_kind=item.payload_kind,
                succeeded=item.succeeded,
            )
            for item in reads
        )
        replayed, used = fake._replay_audit_from_evidence(
            expected_main_sha=expected_main_sha,
            reads=cloned,
        )
        assert replayed == audit
        assert used == {"artifact_zip:7", "main_ref"}
        return cloned

    fake._run_reviewed_projected_audit = run_projected_audit
    fake._replay_audit_from_evidence = replay_audit
    fake._build_with_readers = build_with_readers
    return fake, state


def test_builder_issued_reads_reuse_live_audit_without_second_projected_replay(tmp_path):
    payload = bytes(bytearray(b"exact-actions-artifact"))
    fake, state = _fake_latest(payload=payload)
    diagnostic = tmp_path / "builder-audit.json"
    hooks = reuse.install(fake, diagnostic_path=diagnostic)
    try:
        cloned = fake._build_with_readers(expected_main_sha=MAIN_SHA)
    finally:
        reuse.restore(fake, hooks)

    assert state == {"live": 1, "fallback": 0}
    assert hooks.stats.to_dict() == {
        "live_audits_captured": 1,
        "builder_replays_reused": 1,
        "fallback_replays_executed": 0,
    }
    assert all(item.payload is payload for item in cloned[:1])
    recorded = json.loads(diagnostic.read_text(encoding="utf-8"))
    assert recorded["last_operation"] == "BUILDER_REPLAY_REUSED"
    assert recorded["stats"] == hooks.stats.to_dict()
    assert recorded["evidence_authority"] is False
    assert recorded["model_authority"] is False
    assert recorded["pricing_authority"] is False
    assert recorded["selection_authority"] is False
    assert recorded["execution_authority"] is False
    assert recorded["bet_authority"] is False
    assert recorded["wager_placed"] is False


def test_same_bytes_in_new_payload_object_do_not_reuse_builder_authority():
    payload = bytes(bytearray(b"exact-actions-artifact"))
    fake, state = _fake_latest(payload=payload)
    hooks = reuse.install(fake)
    try:
        fake._build_with_readers(expected_main_sha=MAIN_SHA)
        copied_payload = bytes(bytearray(payload))
        assert copied_payload == payload
        assert copied_payload is not payload
        result = fake._replay_audit_from_evidence(
            expected_main_sha=MAIN_SHA,
            reads=(
                _Snapshot("artifact_zip:7", copied_payload),
                _Snapshot("main_ref", b'{"sha":"main"}\n', payload_kind="json"),
            ),
        )
    finally:
        reuse.restore(fake, hooks)

    assert result[0]["fallback"] == 1
    assert state == {"live": 1, "fallback": 1}
    assert hooks.stats.fallback_replays_executed == 1


def test_builder_reuse_never_crosses_expected_main_identity():
    payload = bytes(bytearray(b"exact-actions-artifact"))
    fake, state = _fake_latest(payload=payload)
    hooks = reuse.install(fake)
    try:
        issued_reads = fake._build_with_readers(expected_main_sha=MAIN_SHA)
        result = fake._replay_audit_from_evidence(
            expected_main_sha=OTHER_MAIN_SHA,
            reads=issued_reads,
        )
    finally:
        reuse.restore(fake, hooks)

    assert result[0]["expected_main_sha"] == OTHER_MAIN_SHA
    assert result[0]["fallback"] == 1
    assert state == {"live": 1, "fallback": 1}


def test_changed_read_key_with_same_payload_refs_falls_back():
    payload = bytes(bytearray(b"exact-actions-artifact"))
    fake, state = _fake_latest(payload=payload)
    hooks = reuse.install(fake)
    try:
        issued_reads = fake._build_with_readers(expected_main_sha=MAIN_SHA)
        changed = (
            _Snapshot("artifact_zip:changed", issued_reads[0].payload),
            _Snapshot(
                issued_reads[1].key,
                issued_reads[1].payload,
                payload_kind=issued_reads[1].payload_kind,
            ),
        )
        result = fake._replay_audit_from_evidence(
            expected_main_sha=MAIN_SHA,
            reads=changed,
        )
    finally:
        reuse.restore(fake, hooks)

    assert result[0]["fallback"] == 1
    assert state == {"live": 1, "fallback": 1}


def test_failed_live_audit_is_never_cached():
    payload = bytes(bytearray(b"exact-actions-artifact"))
    fake, state = _fake_latest(payload=payload, fail_live=True)
    hooks = reuse.install(fake)
    try:
        with pytest.raises(RuntimeError, match="live audit failed"):
            fake._build_with_readers(expected_main_sha=MAIN_SHA)
        result = fake._replay_audit_from_evidence(
            expected_main_sha=MAIN_SHA,
            reads=(_Snapshot("artifact_zip:7", payload),),
        )
    finally:
        reuse.restore(fake, hooks)

    assert result[0]["fallback"] == 1
    assert state == {"live": 1, "fallback": 1}
    assert hooks.stats.live_audits_captured == 0
    assert hooks.stats.builder_replays_reused == 0


def test_restore_returns_every_patched_surface_to_original():
    payload = bytes(bytearray(b"exact-actions-artifact"))
    fake, _state = _fake_latest(payload=payload)
    originals = (
        fake._build_with_readers,
        fake._run_reviewed_projected_audit,
        fake._ReadRecorder.freeze,
        fake._replay_audit_from_evidence,
    )
    hooks = reuse.install(fake)
    reuse.restore(fake, hooks)

    assert fake._build_with_readers is originals[0]
    assert fake._run_reviewed_projected_audit is originals[1]
    assert fake._ReadRecorder.freeze is originals[2]
    assert fake._replay_audit_from_evidence is originals[3]


def test_daily_worker_activates_and_restores_builder_audit_layer(monkeypatch, tmp_path):
    events = []
    verification_hooks = object()
    builder_hooks = object()

    def verification_install(_latest, *, diagnostic_path):
        events.append(("verification_install", diagnostic_path))
        return verification_hooks

    def verification_restore(_latest, hooks):
        assert hooks is verification_hooks
        events.append(("verification_restore", None))

    def builder_install(_latest, *, diagnostic_path):
        events.append(("builder_install", diagnostic_path))
        return builder_hooks

    def builder_restore(_latest, hooks):
        assert hooks is builder_hooks
        events.append(("builder_restore", None))

    def nested_worker(_args):
        events.append(("nested_worker", None))
        return 0

    monkeypatch.setattr(daily.verification_reuse, "install", verification_install)
    monkeypatch.setattr(daily.verification_reuse, "restore", verification_restore)
    monkeypatch.setattr(daily.builder_audit_reuse, "install", builder_install)
    monkeypatch.setattr(daily.builder_audit_reuse, "restore", builder_restore)
    monkeypatch.setattr(daily.bound, "_execute_worker", nested_worker)
    monkeypatch.delenv(daily.all_market_cli.WORKER_ENV, raising=False)

    args = argparse.Namespace(
        target_size=15,
        fixture_scope=daily.SCOPE_THREE_DAY,
        output_dir=Path(tmp_path),
    )
    result = daily._execute_worker(args)

    assert result == 0
    assert events == [
        (
            "verification_install",
            Path(tmp_path) / daily.HISTORY_VERIFICATION_DIAGNOSTIC_FILENAME,
        ),
        (
            "builder_install",
            Path(tmp_path) / daily.HISTORY_BUILDER_AUDIT_DIAGNOSTIC_FILENAME,
        ),
        ("nested_worker", None),
        ("builder_restore", None),
        ("verification_restore", None),
    ]
    assert daily.all_market_cli.WORKER_ENV not in __import__("os").environ
