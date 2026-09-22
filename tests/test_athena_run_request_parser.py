from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from domain.run_contracts import RunRequest
from services.athena_run_request_parser import (
    AthenaRunRequestParseError,
    CLI_TIMEZONE,
    CLI_TIMEZONE_ID,
    parse_explicit_request,
    parse_shorthand_request,
)


WAT = ZoneInfo("Africa/Lagos")
MONDAY = datetime(2026, 9, 21, 12, 0, tzinfo=WAT)


def _explicit(days="today", *, target_legs=25, bookie="sportybet", profile="main", **kwargs):
    return parse_explicit_request(
        days=days,
        target_legs=target_legs,
        bookie=bookie,
        profile=profile,
        now=MONDAY,
        **kwargs,
    )


def test_parser_timezone_and_today_tomorrow_resolve_lagos_dates():
    assert CLI_TIMEZONE_ID == "Africa/Lagos"
    assert CLI_TIMEZONE == WAT
    assert _explicit("today").dates == (date(2026, 9, 21),)
    assert _explicit("tomorrow").dates == (date(2026, 9, 22),)


@pytest.mark.parametrize(
    ("weekday", "expected"),
    [
        ("monday", date(2026, 9, 21)),
        ("tuesday", date(2026, 9, 22)),
        ("wednesday", date(2026, 9, 23)),
        ("thursday", date(2026, 9, 24)),
        ("friday", date(2026, 9, 25)),
        ("saturday", date(2026, 9, 26)),
        ("sunday", date(2026, 9, 27)),
    ],
)
def test_every_weekday_is_resolved_inclusively_within_horizon(weekday, expected):
    assert _explicit(weekday).dates == (expected,)


def test_iso_date_and_arbitrary_weekday_combination_are_sorted_concrete_dates():
    assert _explicit("2026-09-24").dates == (date(2026, 9, 24),)
    request = _explicit("saturday,monday,wednesday")
    assert request.dates == (date(2026, 9, 21), date(2026, 9, 23), date(2026, 9, 26))
    assert all(type(item) is date for item in request.dates)


def test_explicit_one_and_seven_day_bounds():
    assert len(_explicit("today").dates) == 1
    assert _explicit("monday,tuesday,wednesday,thursday,friday,saturday,sunday").dates == tuple(
        date(2026, 9, 21) + timedelta(days=offset) for offset in range(7)
    )


@pytest.mark.parametrize(
    "days",
    [
        "",
        "today,tomorrow,monday,tuesday,wednesday,thursday,friday,saturday",
        "today,",
        ",today",
    ],
)
def test_explicit_day_count_and_empty_tokens_fail_closed(days):
    with pytest.raises(AthenaRunRequestParseError):
        _explicit(days)


def test_duplicate_tokens_and_distinct_tokens_resolving_to_same_date_fail():
    with pytest.raises(AthenaRunRequestParseError, match="duplicate"):
        _explicit("today,today")
    # Monday is the local current date in the fixed test clock.
    with pytest.raises(AthenaRunRequestParseError, match="same calendar date"):
        _explicit("today,monday")


@pytest.mark.parametrize("days", ["2026-09-20", "2026-09-28", "2026-2-03", "2026-02-30", "nextweek"])
def test_past_out_of_window_and_malformed_dates_fail(days):
    with pytest.raises(AthenaRunRequestParseError):
        _explicit(days)


@pytest.mark.parametrize("target_legs", [1, 50])
def test_target_legs_inclusive_bounds(target_legs):
    assert _explicit(target_legs=target_legs).target_legs == target_legs


@pytest.mark.parametrize("target_legs", [0, 51, True, False, 1.0])
def test_target_legs_reject_out_of_bounds_and_non_exact_integers(target_legs):
    with pytest.raises(AthenaRunRequestParseError):
        _explicit(target_legs=target_legs)


def test_bookie_is_exact_and_only_sportybet_is_supported():
    assert _explicit(bookie="sportybet").bookie == "sportybet"
    for bookie in ("SportyBet", "sportybet ", "betway", ""):
        with pytest.raises(AthenaRunRequestParseError):
            _explicit(bookie=bookie)


def test_profiles_have_fixed_modes_and_share_code_permissions_with_no_wager():
    main = _explicit(profile="main")
    assert (main.authority_profile, main.mode, main.create_share_code, main.place_wager) == (
        "MAIN", "main_application", False, False
    )
    shadow = _explicit(profile="shadow")
    assert (shadow.authority_profile, shadow.mode, shadow.create_share_code, shadow.place_wager) == (
        "SHADOW", "research_shadow", True, False
    )
    with pytest.raises(AthenaRunRequestParseError):
        _explicit(profile="MAIN")


def test_target_total_odds_remains_a_separate_decimal_objective():
    request = _explicit(target_legs=25, target_total_odds="2.75")
    assert request.target_legs == 25
    assert request.target_total_odds == Decimal("2.75")
    with pytest.raises(AthenaRunRequestParseError):
        _explicit(target_total_odds=2.75)


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "", "abc"])
def test_invalid_target_total_odds_fails_closed(value):
    with pytest.raises(AthenaRunRequestParseError):
        _explicit(target_total_odds=value)


def test_explicit_parser_requires_an_aware_injected_clock():
    with pytest.raises(AthenaRunRequestParseError, match="timezone-aware"):
        parse_explicit_request(days="today", target_legs=1, profile="main", now=datetime(2026, 9, 21))


def test_shorthand_25acca_maps_only_to_target_legs_and_uses_shadow_profile():
    request = parse_shorthand_request(
        date_scope="tomorrow",
        acca_token="25acca",
        bookie="sportybet",
        now=MONDAY,
    )
    assert type(request) is RunRequest
    assert request.dates == (date(2026, 9, 22),)
    assert request.target_legs == 25
    assert request.target_total_odds is None
    assert request.authority_profile == "SHADOW"
    assert request.mode == "research_shadow"
    assert request.create_share_code is True
    assert request.place_wager is False


def test_shorthand_range_is_inclusive_contiguous_and_accepts_iso_tokens():
    request = parse_shorthand_request(
        date_scope="tomorrow-thursday",
        acca_token="3acca",
        bookie="sportybet",
        now=MONDAY,
    )
    assert request.dates == (date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24))
    iso_request = parse_shorthand_request(
        date_scope="2026-09-22-2026-09-24",
        acca_token="1acca",
        bookie="sportybet",
        now=MONDAY,
    )
    assert iso_request.dates == request.dates


def test_shorthand_range_rejects_end_before_start_without_week_wrap():
    with pytest.raises(AthenaRunRequestParseError, match="do not wrap"):
        parse_shorthand_request(
            date_scope="sunday-monday",
            acca_token="25acca",
            bookie="sportybet",
            now=MONDAY,
        )


@pytest.mark.parametrize(
    ("date_scope", "acca_token", "bookie"),
    [
        ("tomorrow--thursday", "25acca", "sportybet"),
        ("tomorrow", "0acca", "sportybet"),
        ("tomorrow", "51acca", "sportybet"),
        ("tomorrow", "025acca", "sportybet"),
        ("tomorrow", "25-acca", "sportybet"),
        ("tomorrow", "25acca", "SportyBet"),
    ],
)
def test_malformed_shorthand_and_unsupported_bookie_fail(date_scope, acca_token, bookie):
    with pytest.raises(AthenaRunRequestParseError):
        parse_shorthand_request(
            date_scope=date_scope,
            acca_token=acca_token,
            bookie=bookie,
            now=MONDAY,
        )


def test_wat_near_midnight_preserves_lagos_date_when_utc_is_previous_day():
    now = datetime(2026, 9, 21, 0, 15, tzinfo=WAT)
    assert now.astimezone(timezone.utc).date() == date(2026, 9, 20)
    request = parse_explicit_request(days="today", target_legs=1, profile="main", now=now)
    assert request.dates == (date(2026, 9, 21),)
    shorthand = parse_shorthand_request(
        date_scope="today-tomorrow", acca_token="1acca", bookie="sportybet", now=now
    )
    assert shorthand.dates == (date(2026, 9, 21), date(2026, 9, 22))
