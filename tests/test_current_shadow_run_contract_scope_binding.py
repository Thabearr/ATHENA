from __future__ import annotations

from datetime import date

import pytest

from domain import current_shadow_run_contract_adapter as adapter


def _request_policy(*, fixture_scope: str, fixture_dates=None):
    return {
        "schema_version": 1,
        "dataset_name": adapter.CURRENT_REQUEST_DATASET,
        "fixture_scope": fixture_scope,
        "fixture_dates": fixture_dates,
        "authority": {
            "research_shadow_request": True,
            "production_model": False,
            "pricing": False,
            "selection": False,
            "sportybet_execution": False,
            "bet": False,
            "wager_placed": False,
        },
        "wager_placed": False,
    }


def test_scope_only_today_requires_exactly_one_resolved_date():
    policy = _request_policy(fixture_scope="today")
    with pytest.raises(
        adapter.CurrentShadowRunContractAdapterError,
        match="fixture_scope cardinality",
    ):
        adapter.adapt_current_shadow_request(
            target_size=20,
            request_policy=policy,
            resolved_dates=(date(2026, 9, 10), date(2026, 9, 11)),
        )


def test_scope_only_three_day_requires_three_consecutive_resolved_dates():
    policy = _request_policy(fixture_scope="three-day")
    with pytest.raises(
        adapter.CurrentShadowRunContractAdapterError,
        match="fixture_scope continuity",
    ):
        adapter.adapt_current_shadow_request(
            target_size=20,
            request_policy=policy,
            resolved_dates=(
                date(2026, 9, 10),
                date(2026, 9, 11),
                date(2026, 9, 13),
            ),
        )

    request = adapter.adapt_current_shadow_request(
        target_size=20,
        request_policy=policy,
        resolved_dates=(
            date(2026, 9, 12),
            date(2026, 9, 10),
            date(2026, 9, 11),
        ),
    )
    assert request.dates == (
        date(2026, 9, 10),
        date(2026, 9, 11),
        date(2026, 9, 12),
    )


def test_scope_only_unknown_scope_fails_closed_without_clock_inference():
    policy = _request_policy(fixture_scope="rolling-five")
    with pytest.raises(
        adapter.CurrentShadowRunContractAdapterError,
        match="reviewed today/three-day vocabulary",
    ):
        adapter.adapt_current_shadow_request(
            target_size=20,
            request_policy=policy,
            resolved_dates=(date(2026, 9, 10),),
        )


def test_explicit_fixture_dates_keep_reviewed_noncontiguous_override_semantics():
    policy = _request_policy(
        fixture_scope="today",
        fixture_dates=["20260910", "20260912", "20260915"],
    )
    request = adapter.adapt_current_shadow_request(
        target_size=20,
        request_policy=policy,
    )
    assert request.dates == (
        date(2026, 9, 10),
        date(2026, 9, 12),
        date(2026, 9, 15),
    )
