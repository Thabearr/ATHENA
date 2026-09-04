from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from domain import current_shadow_all_market_runner as runner
from domain._current_shadow_price_core import (
    ShadowOpportunityEligibility,
    ShadowPriceDisposition,
)
from domain.markets import MARKET_REGISTRY, MarketId


UTC = timezone.utc
NOW = datetime(2026, 9, 5, 0, 0, tzinfo=UTC)
SHA = "a" * 40


def _completed_router_input():
    market_id = MarketId.BTTS
    outcome_id = MARKET_REGISTRY[market_id].supported_outcomes[0]
    price_result = SimpleNamespace(
        market_id=market_id,
        outcome_id=outcome_id,
        line=None,
        quote_identity_sha256="b" * 64,
        disposition=ShadowPriceDisposition.PRICED,
        decimal_odds=1.20,
    )
    opportunity = SimpleNamespace(
        opportunity_id="c" * 64,
        price_result=price_result,
        prediction_confidence=0.80,
        prediction_confidence_method="SCALAR_MODEL_PROBABILITY_V1",
        prediction_first_rank=1,
        robust_net_expected_value=-0.10,
        robust_edge=-0.05,
        eligibility=ShadowOpportunityEligibility.ELIGIBLE,
        rejection_reasons=(),
    )
    return SimpleNamespace(
        fixture_identity="FOTMOB:30601",
        provider_event_id="sr:match:30601",
        router_decision=SimpleNamespace(opportunities=(opportunity,)),
    )


def _counts():
    return runner._progress_counts(
        reviewed_fixture_count=4,
        reconciled_fixture_count=2,
        provider_event_count=9,
        priced_fixture_count=1,
        router_selected_count=1,
        router_no_bet_count=0,
    )


def _write_progress(tmp_path, diagnostics):
    runner._write_progress_checkpoint(
        output_dir=tmp_path,
        stage=runner.STAGE_PRICE_ALL_ROUTER,
        progress_status="IN_PROGRESS",
        exact_commit_sha=SHA,
        target_size=15,
        counts=_counts(),
        source_summary={
            "known_source_stage": runner.STAGE_PRICE_ALL_ROUTER,
            runner._PROGRESS_DIAGNOSTICS_KEY: diagnostics,
            "wager_placed": False,
        },
    )


def test_runtime_snapshot_uses_exact_router_diagnostics_without_portfolio_selection():
    snapshot = runner._runtime_progress_diagnostics((_completed_router_input(),))
    assert [row["market_id"] for row in snapshot["market_diagnostics"]] == [
        item.value for item in MarketId
    ]
    btts = next(
        row for row in snapshot["market_diagnostics"]
        if row["market_id"] == MarketId.BTTS.value
    )
    assert btts["priced_count"] == 1
    assert btts["prediction_qualified_count"] == 1
    assert btts["odds_qualified_count"] == 1
    assert btts["portfolio_selected_count"] == 0
    assert snapshot["fixture_funnel"]["priced"] == 1
    assert snapshot["fixture_funnel"]["portfolio_selected"] == 0
    assert snapshot["opportunity_funnel"]["priced"] == 1
    assert snapshot["opportunity_funnel"]["portfolio_selected"] == 0


def test_timeout_receipt_retains_completed_market_and_funnel_diagnostics(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(runner, "_git_head", lambda _root: SHA)
    monkeypatch.setattr(runner, "_now", lambda: NOW)
    _write_progress(
        tmp_path,
        runner._runtime_progress_diagnostics((_completed_router_input(),)),
    )

    result = runner.write_current_shadow_timeout_receipt(
        target_size=15,
        output_dir=tmp_path,
    )
    payload = result.to_dict()
    assert result.priced_fixture_count == 1
    assert result.router_selected_count == 1
    assert payload["portfolio"] is None
    assert payload["selected_leg_count"] == 0
    assert payload["shareCode"] is None
    assert payload["fixture_funnel"] == {
        "unit": "fixture",
        "policy_approved": 4,
        "provider_present": 2,
        "identity_reconciled": 2,
        "model_ready": 1,
        "priced": 1,
        "prediction_qualified": 1,
        "odds_qualified": 1,
        "portfolio_selected": 0,
    }
    assert payload["opportunity_funnel"]["priced"] == 1
    btts = next(
        row for row in payload["market_diagnostics"]
        if row["market_id"] == MarketId.BTTS.value
    )
    assert btts["priced_count"] == 1
    assert btts["portfolio_selected_count"] == 0
    assert payload["final_selected_legs"] == []
    assert payload["wager_placed"] is False


def test_mismatched_runtime_snapshot_is_rejected_before_checkpoint_write(tmp_path):
    snapshot = runner._runtime_progress_diagnostics((_completed_router_input(),))
    snapshot["fixture_funnel"]["policy_approved"] = 0
    with pytest.raises(
        runner.CurrentShadowAllMarketRunnerError,
        match="do not match completed Router progress",
    ):
        _write_progress(tmp_path, snapshot)


def test_canonical_checkpoint_with_fabricated_portfolio_state_is_ignored(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(runner, "_git_head", lambda _root: SHA)
    monkeypatch.setattr(runner, "_now", lambda: NOW)
    _write_progress(
        tmp_path,
        runner._runtime_progress_diagnostics((_completed_router_input(),)),
    )
    path = tmp_path / runner.RUN_PROGRESS_FILENAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["source_summary"][runner._PROGRESS_DIAGNOSTICS_KEY][
        "fixture_funnel"
    ]["portfolio_selected"] = 1
    path.write_bytes(runner._canonical(payload))

    result = runner.write_current_shadow_timeout_receipt(
        target_size=15,
        output_dir=tmp_path,
    )
    assert result.priced_fixture_count == 0
    assert result.router_selected_count == 0
    assert result.source_summary["timeout_stage"] == "UNKNOWN"
    assert result.to_dict()["fixture_funnel"]["priced"] == 0
