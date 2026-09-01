from __future__ import annotations

import hashlib

import pytest

from domain import current_shadow_all_market_runner as runner
from scripts import execute_current_shadow_all_market_summary_reuse as wrapper


class _History:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0
        self.fail = False

    def to_dict(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("canonicalization failed")
        return self.payload


def test_summary_sha_reuses_only_exact_builder_issued_history(monkeypatch):
    original_calls = []

    def original(value):
        original_calls.append(value)
        return "original-sha"

    monkeypatch.setattr(
        runner.latest_history,
        "CurrentLatestDurableFreshHistoryHandoff",
        _History,
    )
    monkeypatch.setattr(
        runner.latest_history,
        "sha256_current_fotmob_latest_durable_fresh_history_handoff",
        original,
    )

    issued = _History({"fixture": "issued"})
    unissued = _History({"fixture": "issued"})
    expected = hashlib.sha256(
        runner.latest_history._canonical({"fixture": "issued"})
    ).hexdigest()

    restored = wrapper._install_builder_issued_history_summary_sha_reuse(
        {id(issued): issued}
    )
    try:
        first = (
            runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff(
                issued
            )
        )
        second = (
            runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff(
                issued
            )
        )
        fallback = (
            runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff(
                unissued
            )
        )
    finally:
        runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff = (
            restored
        )

    assert first == expected
    assert second == expected
    assert issued.calls == 1
    assert fallback == "original-sha"
    assert original_calls == [unissued]


def test_summary_sha_does_not_cache_failed_canonicalization(monkeypatch):
    monkeypatch.setattr(
        runner.latest_history,
        "CurrentLatestDurableFreshHistoryHandoff",
        _History,
    )
    monkeypatch.setattr(
        runner.latest_history,
        "sha256_current_fotmob_latest_durable_fresh_history_handoff",
        lambda value: "original-sha",
    )

    issued = _History({"fixture": "issued"})
    restored = wrapper._install_builder_issued_history_summary_sha_reuse(
        {id(issued): issued}
    )
    try:
        issued.fail = True
        with pytest.raises(
            runner.CurrentShadowAllMarketRunnerError,
            match="summary history canonicalization failed",
        ):
            runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff(
                issued
            )

        issued.fail = False
        expected = hashlib.sha256(
            runner.latest_history._canonical({"fixture": "issued"})
        ).hexdigest()
        recovered = (
            runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff(
                issued
            )
        )
        repeated = (
            runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff(
                issued
            )
        )
    finally:
        runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff = (
            restored
        )

    assert recovered == expected
    assert repeated == expected
    assert issued.calls == 2
