from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import current_shadow_history_artifact_verification_reuse as reuse
from scripts import execute_current_shadow_daily as daily


ZIP_BYTES = b"exact-actions-artifact-zip"
ARCHIVE_BYTES = b"exact-durable-archive"
RECEIPT_BYTES = b"exact-canonical-receipt"
RUN_ID = 991
ARTIFACT_NAME = f"success-20260905T000700Z-run-{RUN_ID}.tar.gz"


def _bundle(run_id: int, artifact_name: str, zip_bytes: bytes):
    return {
        "run_id": run_id,
        "artifact_name": artifact_name,
        "archive_bytes": ARCHIVE_BYTES + zip_bytes[:1],
        "archive_sha256": hashlib.sha256(ARCHIVE_BYTES + zip_bytes[:1]).hexdigest(),
        "receipt_bytes": RECEIPT_BYTES,
        "extra": {"marker": "original"},
    }


def test_exact_successful_artifact_verification_is_reused_by_full_identity() -> None:
    calls = {"digest": 0, "bundle": 0}

    def digest(zip_bytes, metadata_digest):
        calls["digest"] += 1
        expected = "sha256:" + hashlib.sha256(zip_bytes).hexdigest()
        if metadata_digest != expected:
            raise ValueError("digest mismatch")
        return expected.removeprefix("sha256:")

    def bundle(*, run_id, artifact_name, zip_bytes):
        calls["bundle"] += 1
        return _bundle(run_id, artifact_name, zip_bytes)

    mirror = SimpleNamespace(
        verify_actions_artifact_zip_digest=digest,
        verify_actions_artifact_bundle=bundle,
    )
    latest = SimpleNamespace(mirror=mirror)
    hooks = reuse.install(latest)
    metadata = "sha256:" + hashlib.sha256(ZIP_BYTES).hexdigest()
    try:
        assert mirror.verify_actions_artifact_zip_digest(ZIP_BYTES, metadata) == metadata[7:]
        assert mirror.verify_actions_artifact_zip_digest(ZIP_BYTES, metadata) == metadata[7:]

        first = mirror.verify_actions_artifact_bundle(
            run_id=RUN_ID,
            artifact_name=ARTIFACT_NAME,
            zip_bytes=ZIP_BYTES,
        )
        first["extra"]["marker"] = "caller-mutated"
        second = mirror.verify_actions_artifact_bundle(
            run_id=RUN_ID,
            artifact_name=ARTIFACT_NAME,
            zip_bytes=ZIP_BYTES,
        )
    finally:
        reuse.restore(latest, hooks)

    assert calls == {"digest": 1, "bundle": 1}
    assert second["extra"] == {"marker": "original"}
    assert hooks.stats.to_dict() == {
        "digest_verified": 1,
        "digest_reused": 1,
        "bundle_verified": 1,
        "bundle_reused": 1,
    }
    assert mirror.verify_actions_artifact_zip_digest is digest
    assert mirror.verify_actions_artifact_bundle is bundle


def test_changed_bytes_run_name_or_digest_never_reuse_verification() -> None:
    calls = {"digest": 0, "bundle": 0}

    def digest(zip_bytes, metadata_digest):
        calls["digest"] += 1
        expected = "sha256:" + hashlib.sha256(zip_bytes).hexdigest()
        if metadata_digest != expected:
            raise ValueError("digest mismatch")
        return expected[7:]

    def bundle(*, run_id, artifact_name, zip_bytes):
        calls["bundle"] += 1
        return _bundle(run_id, artifact_name, zip_bytes)

    mirror = SimpleNamespace(
        verify_actions_artifact_zip_digest=digest,
        verify_actions_artifact_bundle=bundle,
    )
    latest = SimpleNamespace(mirror=mirror)
    hooks = reuse.install(latest)
    changed = ZIP_BYTES + b"-changed"
    try:
        for payload in (ZIP_BYTES, changed):
            metadata = "sha256:" + hashlib.sha256(payload).hexdigest()
            mirror.verify_actions_artifact_zip_digest(payload, metadata)
        with pytest.raises(ValueError, match="digest mismatch"):
            mirror.verify_actions_artifact_zip_digest(
                ZIP_BYTES,
                "sha256:" + "0" * 64,
            )

        mirror.verify_actions_artifact_bundle(
            run_id=RUN_ID,
            artifact_name=ARTIFACT_NAME,
            zip_bytes=ZIP_BYTES,
        )
        mirror.verify_actions_artifact_bundle(
            run_id=RUN_ID,
            artifact_name=ARTIFACT_NAME,
            zip_bytes=changed,
        )
        mirror.verify_actions_artifact_bundle(
            run_id=RUN_ID + 1,
            artifact_name=ARTIFACT_NAME,
            zip_bytes=ZIP_BYTES,
        )
        mirror.verify_actions_artifact_bundle(
            run_id=RUN_ID,
            artifact_name=ARTIFACT_NAME + ".changed",
            zip_bytes=ZIP_BYTES,
        )
    finally:
        reuse.restore(latest, hooks)

    assert calls == {"digest": 3, "bundle": 4}
    assert hooks.stats.to_dict()["digest_reused"] == 0
    assert hooks.stats.to_dict()["bundle_reused"] == 0


def test_failed_or_malformed_verification_is_never_cached() -> None:
    bundle_calls = 0
    fail_first = True

    def bundle(*, run_id, artifact_name, zip_bytes):
        nonlocal bundle_calls, fail_first
        bundle_calls += 1
        if fail_first:
            fail_first = False
            raise RuntimeError("verification failed")
        if bundle_calls == 2:
            return {
                "run_id": run_id,
                "artifact_name": artifact_name,
                "archive_bytes": ARCHIVE_BYTES,
                "archive_sha256": hashlib.sha256(ARCHIVE_BYTES).hexdigest(),
                # deliberately no receipt_bytes => not cacheable
            }
        return _bundle(run_id, artifact_name, zip_bytes)

    mirror = SimpleNamespace(
        verify_actions_artifact_zip_digest=lambda payload, _digest: hashlib.sha256(
            payload
        ).hexdigest(),
        verify_actions_artifact_bundle=bundle,
    )
    latest = SimpleNamespace(mirror=mirror)
    hooks = reuse.install(latest)
    try:
        with pytest.raises(RuntimeError, match="verification failed"):
            mirror.verify_actions_artifact_bundle(
                run_id=RUN_ID,
                artifact_name=ARTIFACT_NAME,
                zip_bytes=ZIP_BYTES,
            )
        malformed = mirror.verify_actions_artifact_bundle(
            run_id=RUN_ID,
            artifact_name=ARTIFACT_NAME,
            zip_bytes=ZIP_BYTES,
        )
        assert "receipt_bytes" not in malformed
        good = mirror.verify_actions_artifact_bundle(
            run_id=RUN_ID,
            artifact_name=ARTIFACT_NAME,
            zip_bytes=ZIP_BYTES,
        )
        reused = mirror.verify_actions_artifact_bundle(
            run_id=RUN_ID,
            artifact_name=ARTIFACT_NAME,
            zip_bytes=ZIP_BYTES,
        )
    finally:
        reuse.restore(latest, hooks)

    assert good == reused
    assert bundle_calls == 3
    assert hooks.stats.to_dict()["bundle_verified"] == 1
    assert hooks.stats.to_dict()["bundle_reused"] == 1


def test_diagnostic_is_non_authoritative_and_final_restore_is_durable(tmp_path: Path) -> None:
    diagnostic = tmp_path / "history-verification.json"

    def digest(payload, metadata):
        expected = "sha256:" + hashlib.sha256(payload).hexdigest()
        assert metadata == expected
        return expected[7:]

    mirror = SimpleNamespace(
        verify_actions_artifact_zip_digest=digest,
        verify_actions_artifact_bundle=lambda **kwargs: _bundle(
            kwargs["run_id"], kwargs["artifact_name"], kwargs["zip_bytes"]
        ),
    )
    latest = SimpleNamespace(mirror=mirror)
    hooks = reuse.install(latest, diagnostic_path=diagnostic)
    metadata = "sha256:" + hashlib.sha256(ZIP_BYTES).hexdigest()
    mirror.verify_actions_artifact_zip_digest(ZIP_BYTES, metadata)
    mirror.verify_actions_artifact_bundle(
        run_id=RUN_ID,
        artifact_name=ARTIFACT_NAME,
        zip_bytes=ZIP_BYTES,
    )
    reuse.restore(latest, hooks)

    import json

    value = json.loads(diagnostic.read_text(encoding="utf-8"))
    assert value["last_operation"] == "RESTORED"
    assert value["stats"] == {
        "digest_verified": 1,
        "digest_reused": 0,
        "bundle_verified": 1,
        "bundle_reused": 0,
    }
    for key in (
        "evidence_authority",
        "model_authority",
        "pricing_authority",
        "selection_authority",
        "execution_authority",
        "bet_authority",
        "wager_placed",
    ):
        assert value[key] is False


def test_daily_worker_installs_and_restores_verification_reuse(monkeypatch, tmp_path: Path) -> None:
    order: list[str] = []
    hook = object()

    def install(latest, *, diagnostic_path):
        assert latest is daily.runner.latest_history
        assert diagnostic_path == tmp_path / daily.HISTORY_VERIFICATION_DIAGNOSTIC_FILENAME
        order.append("install")
        return hook

    def restore(latest, actual_hook):
        assert latest is daily.runner.latest_history
        assert actual_hook is hook
        order.append("restore")

    def execute(_args):
        assert order == ["install"]
        assert daily.os.environ[daily.all_market_cli.WORKER_ENV] == "1"
        order.append("execute")
        return 0

    monkeypatch.setattr(daily.verification_reuse, "install", install)
    monkeypatch.setattr(daily.verification_reuse, "restore", restore)
    monkeypatch.setattr(daily.bound, "_execute_worker", execute)
    monkeypatch.delenv(daily.all_market_cli.WORKER_ENV, raising=False)
    args = argparse.Namespace(
        target_size=15,
        fixture_scope=daily.SCOPE_THREE_DAY,
        output_dir=tmp_path,
    )

    assert daily._execute_worker(args) == 0
    assert order == ["install", "execute", "restore"]
    assert daily.all_market_cli.WORKER_ENV not in daily.os.environ


def test_daily_worker_restores_verification_reuse_when_nested_worker_raises(
    monkeypatch,
    tmp_path: Path,
) -> None:
    order: list[str] = []
    hook = object()
    monkeypatch.setattr(
        daily.verification_reuse,
        "install",
        lambda *_args, **_kwargs: order.append("install") or hook,
    )
    monkeypatch.setattr(
        daily.verification_reuse,
        "restore",
        lambda _latest, actual: order.append("restore")
        if actual is hook
        else (_ for _ in ()).throw(AssertionError("wrong hook")),
    )

    def explode(_args):
        order.append("execute")
        raise RuntimeError("nested failure")

    monkeypatch.setattr(daily.bound, "_execute_worker", explode)
    monkeypatch.setenv(daily.all_market_cli.WORKER_ENV, "preexisting")
    args = argparse.Namespace(
        target_size=15,
        fixture_scope=daily.SCOPE_THREE_DAY,
        output_dir=tmp_path,
    )

    with pytest.raises(RuntimeError, match="nested failure"):
        daily._execute_worker(args)
    assert order == ["install", "execute", "restore"]
    assert daily.os.environ[daily.all_market_cli.WORKER_ENV] == "preexisting"
