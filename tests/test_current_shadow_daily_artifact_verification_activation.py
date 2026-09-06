from __future__ import annotations

import argparse
import hashlib
import json
from types import SimpleNamespace

from scripts import execute_current_shadow_daily as daily


def test_daily_worker_real_reuse_layer_is_visible_inside_nested_worker(
    monkeypatch,
    tmp_path,
) -> None:
    zip_bytes = b"exact-pr151-actions-zip"
    archive_bytes = b"exact-pr151-archive"
    receipt_bytes = b"exact-pr151-receipt"
    run_id = 7001
    artifact_name = f"success-20260905T000700Z-run-{run_id}.tar.gz"
    metadata_digest = "sha256:" + hashlib.sha256(zip_bytes).hexdigest()
    calls = {"digest": 0, "bundle": 0}

    def digest(payload, metadata):
        calls["digest"] += 1
        actual = hashlib.sha256(payload).hexdigest()
        assert metadata == "sha256:" + actual
        return actual

    def bundle(*, run_id, artifact_name, zip_bytes):
        calls["bundle"] += 1
        return {
            "run_id": run_id,
            "artifact_name": artifact_name,
            "release_tag": "athena-fresh-holdout-evidence-2026-W36",
            "receipt_name": artifact_name + ".receipt.json",
            "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
            "archive_size_bytes": len(archive_bytes),
            "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "receipt_size_bytes": len(receipt_bytes),
            "receipt_bytes": receipt_bytes,
            "archive_bytes": archive_bytes,
        }

    fake_latest = SimpleNamespace(
        mirror=SimpleNamespace(
            verify_actions_artifact_zip_digest=digest,
            verify_actions_artifact_bundle=bundle,
        )
    )
    monkeypatch.setattr(daily.runner, "latest_history", fake_latest)
    monkeypatch.delenv(daily.all_market_cli.WORKER_ENV, raising=False)

    # This regression is intentionally scoped to PR #316's artifact-verifier
    # activation. PR #318 adds a separate builder-audit reuse layer whose real
    # surface requires the complete latest-history module. Keep that orthogonal
    # layer inert here; its own daily-worker activation/restoration test exercises
    # the real install order and fail-closed builder surfaces independently.
    builder_hooks = object()
    builder_calls = []

    def builder_install(_latest, *, diagnostic_path):
        builder_calls.append(("install", diagnostic_path))
        return builder_hooks

    def builder_restore(_latest, hooks):
        assert hooks is builder_hooks
        builder_calls.append(("restore", None))

    monkeypatch.setattr(daily.builder_audit_reuse, "install", builder_install)
    monkeypatch.setattr(daily.builder_audit_reuse, "restore", builder_restore)

    def nested(_args):
        mirror = daily.runner.latest_history.mirror
        assert mirror.verify_actions_artifact_zip_digest(zip_bytes, metadata_digest) == metadata_digest[7:]
        assert mirror.verify_actions_artifact_zip_digest(zip_bytes, metadata_digest) == metadata_digest[7:]
        first = mirror.verify_actions_artifact_bundle(
            run_id=run_id,
            artifact_name=artifact_name,
            zip_bytes=zip_bytes,
        )
        second = mirror.verify_actions_artifact_bundle(
            run_id=run_id,
            artifact_name=artifact_name,
            zip_bytes=zip_bytes,
        )
        assert first == second
        return 0

    monkeypatch.setattr(daily.bound, "_execute_worker", nested)
    args = argparse.Namespace(
        target_size=15,
        fixture_scope=daily.SCOPE_THREE_DAY,
        output_dir=tmp_path,
    )

    assert daily._execute_worker(args) == 0
    assert calls == {"digest": 1, "bundle": 1}
    assert fake_latest.mirror.verify_actions_artifact_zip_digest is digest
    assert fake_latest.mirror.verify_actions_artifact_bundle is bundle
    assert builder_calls == [
        (
            "install",
            tmp_path / daily.HISTORY_BUILDER_AUDIT_DIAGNOSTIC_FILENAME,
        ),
        ("restore", None),
    ]

    diagnostic = json.loads(
        (tmp_path / daily.HISTORY_VERIFICATION_DIAGNOSTIC_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    assert diagnostic["last_operation"] == "RESTORED"
    assert diagnostic["stats"] == {
        "digest_verified": 1,
        "digest_reused": 1,
        "bundle_verified": 1,
        "bundle_reused": 1,
    }
    assert diagnostic["bet_authority"] is False
    assert diagnostic["wager_placed"] is False
