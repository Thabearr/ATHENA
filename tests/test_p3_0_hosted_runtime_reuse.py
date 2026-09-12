from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from scripts import capture_p3_0_paired_evidence_hosted as hosted


def test_hosted_workflow_uses_runtime_wrapper_and_preserves_cleanup_margin():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / ".github" / "workflows" / "p3-0-comparison-evidence-capture.yml"
    ).read_text(encoding="utf-8")

    assert "timeout-minutes: 120" in text
    assert "python -m scripts.capture_p3_0_paired_evidence_hosted" in text
    assert "GH_TOKEN: ${{ github.token }}" in text
    assert "contents: read" in text
    assert "actions: read" in text
    assert "contents: write" not in text
    assert "actions: write" not in text
    assert hosted.HOSTED_CAPTURE_TIMEOUT_SECONDS == 105 * 60
    assert hosted.WORKFLOW_JOB_TIMEOUT_SECONDS == 120 * 60
    assert hosted.CLEANUP_MARGIN_SECONDS == 15 * 60


def test_hosted_wrapper_is_reuse_only_and_has_no_delivery_or_wager_calls():
    path = Path(hosted.__file__).resolve()
    source = path.read_text(encoding="utf-8")

    for required in (
        "verification_reuse.install",
        "builder_audit_reuse.install",
        "semantic_replay_reuse.install",
        "history_github_cache.install",
        "_install_history_validation_reuse",
        "_install_captured_history_lineage_reuse",
        "_install_builder_issued_history_tracking",
        "_install_builder_issued_history_xg_reuse",
        "_install_builder_issued_history_summary_sha_reuse",
        "_install_price_context_verification_reuse",
        "collector.main",
    ):
        assert required in source

    for forbidden in (
        "execute_current_shadow_all_market(",
        "portfolio_module.optimize",
        "send_current_shadow_email",
        "sportybet_share_code",
        "share_code_generation",
        "login(",
        "wallet",
        "staking",
        "wager(",
    ):
        assert forbidden not in source


def test_history_cache_worker_marker_is_installer_scoped(monkeypatch):
    key = hosted.history_github_cache.CURRENT_SHADOW_WORKER_ENV
    seen: list[str | None] = []
    sentinel = object()

    monkeypatch.setenv(key, "prior-value")

    def install(_latest):
        seen.append(hosted.os.environ.get(key))
        return sentinel

    monkeypatch.setattr(hosted.history_github_cache, "install", install)
    assert hosted._install_history_cache_with_worker_reuse() is sentinel
    assert seen == ["1"]
    assert hosted.os.environ.get(key) == "prior-value"

    monkeypatch.delenv(key, raising=False)
    seen.clear()
    assert hosted._install_history_cache_with_worker_reuse() is sentinel
    assert seen == ["1"]
    assert key not in hosted.os.environ


def test_runtime_reuse_restores_direct_monkeypatches(monkeypatch):
    latest = hosted.runner.latest_history
    quote = hosted.quote_binding
    price = hosted.runner.price_module

    original_replay = latest._replay_audit_from_evidence
    original_success = latest._success_materials
    original_prefix_derive = latest.prefix._derive
    original_builder = latest.build_current_fotmob_latest_durable_fresh_history_handoff
    original_xg = quote.prc._research_xg_from_complete_current_history
    original_history_sha = latest.sha256_current_fotmob_latest_durable_fresh_history_handoff
    original_price_verify = price.verify_current_shadow_price_context
    original_quote_verify = quote.verify_current_shadow_price_context

    patched_replay = object()
    patched_success = object()
    patched_derive = object()
    lineage_builder = object()
    tracking_builder = object()
    patched_xg = object()
    patched_history_sha = object()
    patched_price_verify = object()
    patched_quote_verify = object()
    restore_events: list[str] = []

    monkeypatch.setattr(
        hosted.verification_reuse,
        "install",
        lambda _latest: restore_events.append("verification_install") or object(),
    )
    monkeypatch.setattr(
        hosted.verification_reuse,
        "restore",
        lambda _latest, _hooks: restore_events.append("verification_restore"),
    )
    monkeypatch.setattr(
        hosted.builder_audit_reuse,
        "install",
        lambda _latest: restore_events.append("builder_audit_install") or object(),
    )
    monkeypatch.setattr(
        hosted.builder_audit_reuse,
        "restore",
        lambda _latest, _hooks: restore_events.append("builder_audit_restore"),
    )
    monkeypatch.setattr(
        hosted.semantic_replay_reuse,
        "install",
        lambda _shadow: restore_events.append("semantic_install") or object(),
    )
    monkeypatch.setattr(
        hosted.semantic_replay_reuse,
        "restore",
        lambda _shadow, _hooks: restore_events.append("semantic_restore"),
    )
    monkeypatch.setattr(
        hosted.history_github_cache,
        "install",
        lambda _latest: restore_events.append("cache_install") or object(),
    )
    monkeypatch.setattr(
        hosted.history_github_cache,
        "restore",
        lambda _latest, _hooks: restore_events.append("cache_restore"),
    )

    def install_validation():
        latest._replay_audit_from_evidence = patched_replay
        latest._success_materials = patched_success
        latest.prefix._derive = patched_derive
        return original_replay, original_success, original_prefix_derive

    def install_lineage():
        latest.build_current_fotmob_latest_durable_fresh_history_handoff = lineage_builder
        return original_builder

    def install_tracking():
        latest.build_current_fotmob_latest_durable_fresh_history_handoff = tracking_builder
        return lineage_builder, {}

    def install_xg(_issued):
        quote.prc._research_xg_from_complete_current_history = patched_xg
        return original_xg

    def install_history_sha(_issued):
        latest.sha256_current_fotmob_latest_durable_fresh_history_handoff = (
            patched_history_sha
        )
        return original_history_sha

    def install_price_verification():
        price.verify_current_shadow_price_context = patched_price_verify
        quote.verify_current_shadow_price_context = patched_quote_verify
        return original_price_verify, original_quote_verify

    monkeypatch.setattr(
        hosted.all_market_cli,
        "_install_history_validation_reuse",
        install_validation,
    )
    monkeypatch.setattr(
        hosted.summary_cli,
        "_install_captured_history_lineage_reuse",
        install_lineage,
    )
    monkeypatch.setattr(
        hosted.all_market_cli,
        "_install_builder_issued_history_tracking",
        install_tracking,
    )
    monkeypatch.setattr(
        hosted.all_market_cli,
        "_install_builder_issued_history_xg_reuse",
        install_xg,
    )
    monkeypatch.setattr(
        hosted.summary_cli,
        "_install_builder_issued_history_summary_sha_reuse",
        install_history_sha,
    )
    monkeypatch.setattr(
        hosted.all_market_cli,
        "_install_price_context_verification_reuse",
        install_price_verification,
    )

    with hosted._current_shadow_runtime_reuse():
        assert latest._replay_audit_from_evidence is patched_replay
        assert latest._success_materials is patched_success
        assert latest.prefix._derive is patched_derive
        assert latest.build_current_fotmob_latest_durable_fresh_history_handoff is tracking_builder
        assert quote.prc._research_xg_from_complete_current_history is patched_xg
        assert latest.sha256_current_fotmob_latest_durable_fresh_history_handoff is patched_history_sha
        assert price.verify_current_shadow_price_context is patched_price_verify
        assert quote.verify_current_shadow_price_context is patched_quote_verify

    assert latest._replay_audit_from_evidence is original_replay
    assert latest._success_materials is original_success
    assert latest.prefix._derive is original_prefix_derive
    assert latest.build_current_fotmob_latest_durable_fresh_history_handoff is original_builder
    assert quote.prc._research_xg_from_complete_current_history is original_xg
    assert latest.sha256_current_fotmob_latest_durable_fresh_history_handoff is original_history_sha
    assert price.verify_current_shadow_price_context is original_price_verify
    assert quote.verify_current_shadow_price_context is original_quote_verify
    assert restore_events == [
        "verification_install",
        "builder_audit_install",
        "semantic_install",
        "cache_install",
        "cache_restore",
        "semantic_restore",
        "builder_audit_restore",
        "verification_restore",
    ]


def test_hosted_main_restores_contexts_when_collector_raises(monkeypatch):
    events: list[str] = []

    @contextmanager
    def runtime_reuse():
        events.append("reuse_enter")
        try:
            yield
        finally:
            events.append("reuse_exit")

    @contextmanager
    def deadline():
        events.append("deadline_enter")
        try:
            yield
        finally:
            events.append("deadline_exit")

    monkeypatch.setattr(hosted, "_current_shadow_runtime_reuse", runtime_reuse)
    monkeypatch.setattr(hosted, "_hosted_deadline", deadline)

    def fail(_argv):
        events.append("collector")
        raise RuntimeError("boom")

    monkeypatch.setattr(hosted.collector, "main", fail)

    with pytest.raises(RuntimeError, match="boom"):
        hosted.main(["--fixture-dates", "20260912", "--fixture-cap", "1"])

    assert events == [
        "reuse_enter",
        "deadline_enter",
        "collector",
        "deadline_exit",
        "reuse_exit",
    ]
