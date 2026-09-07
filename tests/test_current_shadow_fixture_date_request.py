from __future__ import annotations

import datetime as dt

import pytest

from domain import current_shadow_fixture_date_request as request


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def test_explicit_dates_are_canonical_sorted_and_can_be_non_contiguous():
    parsed = request.parse_fixture_dates_text("20260910,20260908,20260909")
    assert parsed == ("20260908", "20260909", "20260910")
    assert request.validate_fixture_dates(parsed, current_utc=NOW) == parsed


def test_any_one_through_seven_dates_inside_rolling_window_are_allowed():
    all_dates = tuple(
        (NOW.date() + dt.timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range(7)
    )
    assert request.validate_fixture_dates(all_dates, current_utc=NOW) == all_dates
    assert request.validate_fixture_dates((all_dates[-1],), current_utc=NOW) == (
        all_dates[-1],
    )


def test_selected_tuesday_wednesday_thursday_are_valid_while_today_is_sunday():
    assert request.validate_fixture_dates(
        ("20260908", "20260909", "20260910"), current_utc=NOW
    ) == ("20260908", "20260909", "20260910")


@pytest.mark.parametrize(
    "value",
    (
        "20260907,20260907",
        "2026-09-07",
        "20260931",
        "20260907,",
        " 20260907",
        "20260907, 20260908",
        "20260907,20260908 ",
        "20260907,20260908,20260909,20260910,20260911,20260912,20260913,20260914",
    ),
)
def test_malformed_duplicate_or_overlong_date_requests_fail_closed(value):
    with pytest.raises(request.CurrentShadowFixtureDateRequestError):
        request.parse_fixture_dates_text(value)


@pytest.mark.parametrize("value", (("20260905",), ("20260913",)))
def test_dates_outside_today_through_today_plus_six_fail_closed(value):
    with pytest.raises(
        request.CurrentShadowFixtureDateRequestError,
        match="outside the rolling",
    ):
        request.validate_fixture_dates(value, current_utc=NOW)


def test_request_policy_has_no_downstream_or_wager_authority():
    summary = request.policy_summary()
    assert summary["maximum_selected_dates"] == 7
    assert summary["maximum_forward_days"] == 6
    assert summary["wager_placed"] is False
    authority = summary["authority"]
    assert authority["research_shadow_fixture_date_request"] is True
    assert authority["source_acquisition"] is False
    assert authority["production_model"] is False
    assert authority["pricing"] is False
    assert authority["selection"] is False
    assert authority["sportybet_execution"] is False
    assert authority["bet"] is False
    assert authority["wager_placed"] is False
