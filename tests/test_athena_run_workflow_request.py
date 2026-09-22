from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from domain.run_contracts import RunRequest, canonical_json_bytes
from services.athena_run_workflow_request import (
    AthenaRunWorkflowRequestError,
    SCHEDULE_DAYS,
    SCHEDULE_TARGET_LEGS,
    WORKFLOW_DISPATCH_DEFAULTS,
    resolve_workflow_request,
)


WAT = ZoneInfo("Africa/Lagos")
DAYTIME = datetime(2026, 9, 22, 12, 30, tzinfo=WAT)
NEAR_MIDNIGHT = datetime(2026, 9, 23, 0, 15, tzinfo=WAT)
DISPATCH_DEFAULTS = dict(WORKFLOW_DISPATCH_DEFAULTS)


def test_schedule_resolves_source_controlled_main_defaults_to_exact_request():
    request = resolve_workflow_request(event_name="schedule", now=DAYTIME)
    assert type(request) is RunRequest
    assert request.dates == (date(2026, 9, 22),)
    assert (request.target_legs, request.target_total_odds) == (20, None)
    assert (request.bookie, request.authority_profile, request.mode) == (
        "sportybet", "MAIN", "main_application"
    )
    assert request.create_share_code is False
    assert request.place_wager is False
    assert SCHEDULE_DAYS == "today"
    assert SCHEDULE_TARGET_LEGS == 20


@pytest.mark.parametrize("now", [DAYTIME, NEAR_MIDNIGHT])
def test_default_manual_and_schedule_resolve_identical_request_bytes_and_sha(now):
    scheduled = resolve_workflow_request(event_name="schedule", now=now)
    manual = resolve_workflow_request(
        event_name="workflow_dispatch",
        dispatch_inputs=DISPATCH_DEFAULTS,
        now=now,
    )
    assert canonical_json_bytes(scheduled) == canonical_json_bytes(manual)
    assert scheduled.canonical_sha256 == manual.canonical_sha256
    assert scheduled == manual


def test_manual_shadow_override_uses_the_p41_parser_semantics():
    request = resolve_workflow_request(
        event_name="workflow_dispatch",
        dispatch_inputs={
            "days": "tomorrow,thursday",
            "target_legs": "25",
            "target_total_odds": "",
            "bookie": "sportybet",
            "profile": "shadow",
        },
        now=DAYTIME,
    )
    assert request.dates == (date(2026, 9, 23), date(2026, 9, 24))
    assert request.target_legs == 25
    assert request.target_total_odds is None
    assert request.authority_profile == "SHADOW"
    assert request.mode == "research_shadow"
    assert request.create_share_code is True
    assert request.place_wager is False


def test_target_total_odds_is_independent_of_leg_count():
    request = resolve_workflow_request(
        event_name="workflow_dispatch",
        dispatch_inputs={
            **DISPATCH_DEFAULTS,
            "target_legs": "25",
            "target_total_odds": "2.75",
        },
        now=DAYTIME,
    )
    assert request.target_legs == 25
    assert request.target_total_odds == Decimal("2.75")


@pytest.mark.parametrize("target", ["0", "51", "020", "20 ", " 20", "20.0", "true", "False", ""])
def test_dispatch_target_legs_requires_canonical_integer_text(target):
    with pytest.raises(AthenaRunWorkflowRequestError, match="canonical decimal text"):
        resolve_workflow_request(
            event_name="workflow_dispatch",
            dispatch_inputs={**DISPATCH_DEFAULTS, "target_legs": target},
            now=DAYTIME,
        )


@pytest.mark.parametrize("target", ["1", "50"])
def test_dispatch_target_bounds_are_inclusive(target):
    request = resolve_workflow_request(
        event_name="workflow_dispatch",
        dispatch_inputs={**DISPATCH_DEFAULTS, "target_legs": target},
        now=DAYTIME,
    )
    assert request.target_legs == int(target)


def test_dispatch_rejects_missing_extra_and_nontext_input_values():
    with pytest.raises(AthenaRunWorkflowRequestError, match="names"):
        resolve_workflow_request(
            event_name="workflow_dispatch",
            dispatch_inputs={key: value for key, value in DISPATCH_DEFAULTS.items() if key != "days"},
            now=DAYTIME,
        )
    with pytest.raises(AthenaRunWorkflowRequestError, match="names"):
        resolve_workflow_request(
            event_name="workflow_dispatch",
            dispatch_inputs={**DISPATCH_DEFAULTS, "unexpected": "x"},
            now=DAYTIME,
        )
    with pytest.raises(AthenaRunWorkflowRequestError, match="exact text"):
        resolve_workflow_request(
            event_name="workflow_dispatch",
            dispatch_inputs={**DISPATCH_DEFAULTS, "target_legs": 20},  # type: ignore[arg-type]
            now=DAYTIME,
        )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("bookie", "Betway"),
        ("bookie", "sportybet "),
        ("profile", "MAIN"),
        ("profile", "shadow "),
        ("days", "today,"),
        ("target_total_odds", " "),
    ],
)
def test_dispatch_rejects_unsupported_or_ambiguous_text(key, value):
    with pytest.raises(AthenaRunWorkflowRequestError):
        resolve_workflow_request(
            event_name="workflow_dispatch",
            dispatch_inputs={**DISPATCH_DEFAULTS, key: value},
            now=DAYTIME,
        )


def test_schedule_rejects_dispatch_values_and_other_events_fail_closed():
    with pytest.raises(AthenaRunWorkflowRequestError, match="cannot supply"):
        resolve_workflow_request(
            event_name="schedule", dispatch_inputs=DISPATCH_DEFAULTS, now=DAYTIME
        )
    with pytest.raises(AthenaRunWorkflowRequestError, match="only schedule"):
        resolve_workflow_request(event_name="push", now=DAYTIME)


def test_near_midnight_wat_resolves_today_without_utc_date_shift():
    assert NEAR_MIDNIGHT.astimezone(timezone.utc).date() == date(2026, 9, 22)
    request = resolve_workflow_request(event_name="schedule", now=NEAR_MIDNIGHT)
    assert request.dates == (date(2026, 9, 23),)
