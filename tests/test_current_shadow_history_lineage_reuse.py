from __future__ import annotations

from argparse import Namespace
import hashlib
from types import SimpleNamespace

import pytest

from domain import _all_market_shadow_current_binding as current_binding
from domain import current_shadow_all_market_runner as runner
from scripts import execute_current_shadow_all_market as cli


MAIN_SHA = "a" * 40


class _Evidence:
    expected_main_sha = MAIN_SHA

    def __init__(self):
        self.reads = []

    def json(self, key):
        self.reads.append(("json", key))
        return {"key": key}

    def binary(self, key):
        self.reads.append(("binary", key))
        return key.encode("ascii")


def test_worker_reuses_first_exact_pr151_lineage_snapshot(monkeypatch, tmp_path, capsys):
    evidence = _Evidence()
    first_history = SimpleNamespace(
        source_bundle=SimpleNamespace(github_evidence=evidence)
    )
    second_history = object()
    live_calls = []
    replay_calls = []

    def live_builder(**kwargs):
        live_calls.append(kwargs)
        return first_history

    def replay_builder(**kwargs):
        replay_calls.append(kwargs)
        assert kwargs["get_main_ref"]() == {"key": "main_ref"}
        assert kwargs["get_runs_page"](2, 100) == {"key": "runs:2:100"}
        assert kwargs["get_run_by_id"](7) == {"key": "run:7"}
        assert kwargs["get_run_artifacts"](7) == {"key": "artifacts:7"}
        assert kwargs["download_artifact_zip"](8) == b"artifact_zip:8"
        assert kwargs["get_release"]("tag") == {"key": "release:tag"}
        assert kwargs["download_release_asset"](9) == b"release_asset:9"
        assert kwargs["get_run_jobs"](7) == {"key": "jobs:7"}
        return second_history

    monkeypatch.setattr(
        runner.latest_history,
        "build_current_fotmob_latest_durable_fresh_history_handoff",
        live_builder,
    )
    monkeypatch.setattr(runner.latest_history, "_build_with_readers", replay_builder)

    def execute(*, target_size, output_dir):
        assert target_size == 20
        assert output_dir == tmp_path
        common = {
            "current_bootstrap": object(),
            "source_raw_json": b"source",
            "source_manifest": object(),
            "legacy_bootstrap_projection_raw": b"legacy",
            "expected_main_sha": MAIN_SHA,
            "repository_root": tmp_path,
        }
        first = runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff(
            **common
        )
        second = runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff(
            **common
        )
        assert first is first_history
        assert second is second_history
        return SimpleNamespace(to_dict=lambda: {"status": "test", "wager_placed": False})

    monkeypatch.setattr(runner, "execute_current_shadow_all_market", execute)

    rc = cli._execute_once(Namespace(target_size=20, output_dir=tmp_path))

    assert rc == 0
    assert len(live_calls) == 1
    assert len(replay_calls) == 1
    assert replay_calls[0]["expected_main_sha"] == MAIN_SHA
    assert replay_calls[0]["repository_root"] == tmp_path
    assert runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff is live_builder
    assert capsys.readouterr().out
    assert evidence.reads == [
        ("json", "main_ref"),
        ("json", "runs:2:100"),
        ("json", "run:7"),
        ("json", "artifacts:7"),
        ("binary", "artifact_zip:8"),
        ("json", "release:tag"),
        ("binary", "release_asset:9"),
        ("json", "jobs:7"),
    ]


def test_worker_does_not_reuse_lineage_snapshot_across_main_identity(monkeypatch):
    histories = []

    def live_builder(**kwargs):
        evidence = SimpleNamespace(expected_main_sha=kwargs["expected_main_sha"])
        history = SimpleNamespace(
            source_bundle=SimpleNamespace(github_evidence=evidence)
        )
        histories.append(history)
        return history

    monkeypatch.setattr(
        runner.latest_history,
        "build_current_fotmob_latest_durable_fresh_history_handoff",
        live_builder,
    )
    original = cli._install_history_lineage_reuse()
    try:
        common = {
            "current_bootstrap": object(),
            "source_raw_json": b"source",
            "source_manifest": object(),
            "legacy_bootstrap_projection_raw": b"legacy",
        }
        runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff(
            **common, expected_main_sha="a" * 40
        )
        runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff(
            **common, expected_main_sha="b" * 40
        )
    finally:
        runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff = original

    assert len(histories) == 2


def test_worker_tracks_only_histories_issued_by_installed_builder(monkeypatch):
    issued_history = object()

    def builder(**_kwargs):
        return issued_history

    monkeypatch.setattr(
        runner.latest_history,
        "build_current_fotmob_latest_durable_fresh_history_handoff",
        builder,
    )
    original, issued = cli._install_builder_issued_history_tracking()
    try:
        result = runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff()
    finally:
        runner.latest_history.build_current_fotmob_latest_durable_fresh_history_handoff = original

    assert result is issued_history
    assert issued == {id(issued_history): issued_history}


def test_worker_reuses_builder_issued_history_without_second_deep_replay(monkeypatch):
    class FakeHistory:
        def __init__(self, marker):
            self.marker = marker
            self.to_dict_calls = 0

        def to_dict(self):
            self.to_dict_calls += 1
            return {"marker": self.marker}

    issued_history = FakeHistory("issued")
    unknown_history = FakeHistory("unknown")
    fallback_calls = []
    validated_calls = []

    def fallback(history, fixture_identity):
        fallback_calls.append((history, fixture_identity))
        return ("fallback", fixture_identity)

    def validated(history, fixture_identity, *, history_sha):
        validated_calls.append((history, fixture_identity, history_sha))
        return ("validated", fixture_identity, history_sha)

    monkeypatch.setattr(
        runner.latest_history,
        "CurrentLatestDurableFreshHistoryHandoff",
        FakeHistory,
    )
    monkeypatch.setattr(
        cli.quote_binding.prc,
        "_research_xg_from_complete_current_history",
        fallback,
    )
    monkeypatch.setattr(
        current_binding,
        "_research_xg_from_validated_current_history",
        validated,
    )

    original = cli._install_builder_issued_history_xg_reuse(
        {id(issued_history): issued_history}
    )
    try:
        first = cli.quote_binding.prc._research_xg_from_complete_current_history(
            issued_history,
            "FOTMOB:1",
        )
        second = cli.quote_binding.prc._research_xg_from_complete_current_history(
            issued_history,
            "FOTMOB:2",
        )
        fallback_result = cli.quote_binding.prc._research_xg_from_complete_current_history(
            unknown_history,
            "FOTMOB:3",
        )
    finally:
        cli.quote_binding.prc._research_xg_from_complete_current_history = original

    expected_sha = hashlib.sha256(
        runner.latest_history._canonical({"marker": "issued"})
    ).hexdigest()
    assert first == ("validated", "FOTMOB:1", expected_sha)
    assert second == ("validated", "FOTMOB:2", expected_sha)
    assert fallback_result == ("fallback", "FOTMOB:3")
    assert issued_history.to_dict_calls == 1
    assert unknown_history.to_dict_calls == 0
    assert validated_calls == [
        (issued_history, "FOTMOB:1", expected_sha),
        (issued_history, "FOTMOB:2", expected_sha),
    ]
    assert fallback_calls == [(unknown_history, "FOTMOB:3")]


def test_worker_reuses_only_a_successfully_verified_price_context(monkeypatch):
    calls = []
    source = SimpleNamespace(canonical_sha256="c" * 64)
    verified = SimpleNamespace(canonical_sha256="c" * 64)

    def exact_verify(value):
        calls.append(value)
        return verified

    monkeypatch.setattr(
        runner.price_module,
        "verify_current_shadow_price_context",
        exact_verify,
    )
    monkeypatch.setattr(
        cli.quote_binding,
        "verify_current_shadow_price_context",
        exact_verify,
    )

    original_price, original_quote = cli._install_price_context_verification_reuse()
    try:
        first = runner.price_module.verify_current_shadow_price_context(source)
        second = cli.quote_binding.verify_current_shadow_price_context(source)
        third = runner.price_module.verify_current_shadow_price_context(verified)
    finally:
        runner.price_module.verify_current_shadow_price_context = original_price
        cli.quote_binding.verify_current_shadow_price_context = original_quote

    assert first is verified
    assert second is verified
    assert third is verified
    assert calls == [source]


def test_worker_price_context_reuse_fails_closed_on_identity_drift(monkeypatch):
    source = SimpleNamespace(canonical_sha256="c" * 64)
    changed = SimpleNamespace(canonical_sha256="d" * 64)

    monkeypatch.setattr(
        runner.price_module,
        "verify_current_shadow_price_context",
        lambda _value: changed,
    )
    monkeypatch.setattr(
        cli.quote_binding,
        "verify_current_shadow_price_context",
        lambda _value: changed,
    )

    original_price, original_quote = cli._install_price_context_verification_reuse()
    try:
        with pytest.raises(
            runner.CurrentShadowAllMarketRunnerError,
            match="verified Shadow price context identity drifted",
        ):
            runner.price_module.verify_current_shadow_price_context(source)
    finally:
        runner.price_module.verify_current_shadow_price_context = original_price
        cli.quote_binding.verify_current_shadow_price_context = original_quote
