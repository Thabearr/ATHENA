from __future__ import annotations

import datetime as dt
import hashlib
from types import SimpleNamespace

import pytest

from scripts import execute_current_shadow_all_market_summary_reuse as summary_cli


HEAD_SHA = "a" * 40
RUN_ID = 99
ARTIFACT_NAME = f"success-20260905T000700Z-run-{RUN_ID}.tar.gz"
ZIP_BYTES = b"exact-actions-artifact-zip"


class LatestHistoryError(RuntimeError):
    pass


def _first_history():
    evidence = SimpleNamespace(expected_main_sha=HEAD_SHA)
    return evidence, SimpleNamespace(
        source_bundle=SimpleNamespace(github_evidence=evidence)
    )


def test_later_date_replay_rejects_non_authoritative_observed_at(monkeypatch) -> None:
    evidence, first_history = _first_history()
    live_calls = 0

    def live_builder(**_kwargs):
        nonlocal live_calls
        live_calls += 1
        return first_history

    fake_latest = SimpleNamespace(
        build_current_fotmob_latest_durable_fresh_history_handoff=live_builder,
        CurrentLatestDurableFreshHistoryError=LatestHistoryError,
    )
    monkeypatch.setattr(summary_cli.runner, "latest_history", fake_latest)
    original = summary_cli._install_captured_history_lineage_reuse()
    try:
        fake_latest.build_current_fotmob_latest_durable_fresh_history_handoff(
            expected_main_sha=HEAD_SHA
        )
        with pytest.raises(
            LatestHistoryError,
            match="current source manifest lost observed_at authority",
        ):
            fake_latest.build_current_fotmob_latest_durable_fresh_history_handoff(
                expected_main_sha=HEAD_SHA,
                source_manifest=SimpleNamespace(
                    observed_at=dt.datetime(2026, 9, 6, 17, 30)
                ),
            )
    finally:
        fake_latest.build_current_fotmob_latest_durable_fresh_history_handoff = original

    assert live_calls == 1
    assert evidence.expected_main_sha == HEAD_SHA


def test_later_date_prefix_failure_preserves_latest_history_error_boundary(
    monkeypatch,
) -> None:
    evidence, first_history = _first_history()
    observed = dt.datetime(2026, 9, 6, 17, 30, tzinfo=dt.timezone.utc)
    chosen = SimpleNamespace(run_id=RUN_ID, artifact_name=ARTIFACT_NAME)
    selection_calls = []

    def live_builder(**_kwargs):
        return first_history

    def select_latest_material(*, evidence, source_observed_at):
        selection_calls.append((evidence, source_observed_at))
        return (
            chosen,
            {"name": ARTIFACT_NAME},
            ZIP_BYTES,
            "sha256:" + hashlib.sha256(ZIP_BYTES).hexdigest(),
        )

    def fail_prefix(**_kwargs):
        raise ValueError("exact cumulative archive replay failed")

    fake_latest = SimpleNamespace(
        build_current_fotmob_latest_durable_fresh_history_handoff=live_builder,
        CurrentLatestDurableFreshHistoryError=LatestHistoryError,
        _select_latest_material=select_latest_material,
        prefix=SimpleNamespace(
            build_current_fotmob_durable_fresh_history_prefix_handoff=fail_prefix
        ),
    )
    monkeypatch.setattr(summary_cli.runner, "latest_history", fake_latest)
    original = summary_cli._install_captured_history_lineage_reuse()
    try:
        fake_latest.build_current_fotmob_latest_durable_fresh_history_handoff(
            expected_main_sha=HEAD_SHA
        )
        with pytest.raises(
            LatestHistoryError,
            match="latest applicable success failed exact cumulative prefix replay",
        ):
            fake_latest.build_current_fotmob_latest_durable_fresh_history_handoff(
                expected_main_sha=HEAD_SHA,
                source_manifest=SimpleNamespace(observed_at=observed),
                current_bootstrap=object(),
                source_raw_json=b"raw",
                legacy_bootstrap_projection_raw=b"legacy",
            )
    finally:
        fake_latest.build_current_fotmob_latest_durable_fresh_history_handoff = original

    assert selection_calls == [(evidence, observed)]
