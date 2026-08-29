from __future__ import annotations

import datetime as dt

import pytest

from domain import current_shadow_sportybet_field_trial as field_trial
from domain import current_shadow_sportybet_share_code as share
from tests.test_current_shadow_sportybet_share_code import (
    _portfolio,
    _semantic_success,
)


def test_semantic_resolution_cannot_age_quote_past_freshness_before_create(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision, portfolio, evaluation = _portfolio(tmp_path, monkeypatch)
    leg = portfolio.selected_legs[0]
    semantic = _semantic_success(leg)
    calls = {"semantic": 0, "direct": 0}

    first_now = evaluation + dt.timedelta(seconds=30)
    stale_precreate = leg.quote_observed_at + dt.timedelta(
        seconds=field_trial.MAX_SOURCE_AGE_SECONDS + 1
    )
    assert stale_precreate >= first_now
    times = iter((first_now, stale_precreate))
    monkeypatch.setattr(share, "_now_utc", lambda: next(times))

    def semantic_success(**_kwargs):
        calls["semantic"] += 1
        return semantic

    def direct_must_not_run(**_kwargs):
        calls["direct"] += 1
        raise AssertionError(
            "direct create must not run after quote ages stale during semantic resolution"
        )

    monkeypatch.setattr(
        share.semantic_bridge,
        "resolve_live_intents",
        semantic_success,
    )
    monkeypatch.setattr(
        share.direct_bridge,
        "create_and_roundtrip",
        direct_must_not_run,
    )

    result = share.create_current_shadow_sportybet_share_code(
        portfolio=portfolio,
        source_decisions=(decision,),
        output_dir=tmp_path / "share",
        delay_seconds=0,
    )

    assert result.status == share.STATUS_REPRICE_REQUIRED
    assert result.share_code is None
    assert result.semantic_resolution_receipt_sha256 is not None
    assert result.transport_receipt_sha256 is None
    assert result.observed_at == stale_precreate
    assert calls == {"semantic": 1, "direct": 0}
    assert any(
        "CURRENT_PROVIDER_QUOTE_STALE" in reason
        for reason in result.reasons
    )
    assert result.to_dict()["wager_placed"] is False
