from __future__ import annotations

import pytest

import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as score_adapter
import domain.fotmob_fresh_holdout_request_date_spillover_adapter as live_adapter
import domain.fotmob_fresh_holdout_request_date_spillover_settlement_adapter as settlement_adapter
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import scripts.run_fotmob_utc_native_xg_fresh_holdout_tick as tick_cli


def test_cli_scopes_request_date_spillover_adapters_and_restores_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_qualifier = fresh.qualify_capture_fixtures
    original_score_pr89 = score_adapter.pr89
    seen = {}

    def fake_execute(**kwargs):
        seen["qualifier"] = fresh.qualify_capture_fixtures
        seen["score_pr89"] = score_adapter.pr89
        seen["kwargs"] = kwargs
        return {"ok": True}

    monkeypatch.setattr(tick_cli.runner, "execute_collection_tick", fake_execute)
    result = tick_cli._execute_collection_tick_with_reviewed_adapter(probe="value")
    assert result == {"ok": True}
    assert seen["qualifier"] is live_adapter.qualify_capture_fixtures
    assert isinstance(
        seen["score_pr89"],
        settlement_adapter.ReviewedPr89RequestDateSpilloverSettlementProxy,
    )
    assert seen["kwargs"] == {"probe": "value"}
    assert fresh.qualify_capture_fixtures is original_qualifier
    assert score_adapter.pr89 is original_score_pr89
