from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import current_shadow_history_artifact_verification_reuse as reuse
from scripts import execute_current_shadow_daily as daily


def test_verifier_surfaces_restore_even_if_final_diagnostic_write_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    original_digest = lambda *_args: "digest"
    original_bundle = lambda **_kwargs: {"bundle": True}
    mirror = SimpleNamespace(
        verify_actions_artifact_zip_digest=lambda *_args: "patched-digest",
        verify_actions_artifact_bundle=lambda **_kwargs: {"patched": True},
    )
    latest = SimpleNamespace(mirror=mirror)
    hooks = reuse.ArtifactVerificationReuseHooks(
        original_digest_verifier=original_digest,
        original_bundle_verifier=original_bundle,
        stats=reuse.ArtifactVerificationReuseStats(),
        diagnostic_path=tmp_path / "diagnostic.json",
    )

    monkeypatch.setattr(
        reuse,
        "_write_diagnostic",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk failed")),
    )
    with pytest.raises(OSError, match="disk failed"):
        reuse.restore(latest, hooks)

    assert mirror.verify_actions_artifact_zip_digest is original_digest
    assert mirror.verify_actions_artifact_bundle is original_bundle


def test_daily_scope_and_worker_marker_restore_even_if_verifier_cleanup_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    original_day_count = daily.runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT
    hook = object()
    monkeypatch.setattr(
        daily.verification_reuse,
        "install",
        lambda *_args, **_kwargs: hook,
    )
    monkeypatch.setattr(
        daily.verification_reuse,
        "restore",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("cleanup failed")),
    )
    monkeypatch.setattr(daily.bound, "_execute_worker", lambda _args: 0)
    monkeypatch.setenv(daily.all_market_cli.WORKER_ENV, "preexisting")
    args = argparse.Namespace(
        target_size=15,
        fixture_scope=daily.SCOPE_THREE_DAY,
        output_dir=tmp_path,
    )

    with pytest.raises(OSError, match="cleanup failed"):
        daily._execute_worker(args)

    assert daily.runner.CURRENT_FIXTURE_SEARCH_DAY_COUNT == original_day_count
    assert daily.os.environ[daily.all_market_cli.WORKER_ENV] == "preexisting"
