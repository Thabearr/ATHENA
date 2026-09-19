from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts import _p3_0_paired_capture_part2 as capture


def _summary(*, dispositions=None):
    if dispositions is None:
        dispositions = {
            "NO_EXACT_FIXTURE_MATCH": 5,
            "PROVIDER_ONLY": 2,
        }
    return {
        "provider_event_count": 7,
        "provider_prematch_bookable_count": 0,
        "provider_inplay_count": 7,
        "provider_future_lead_eligible_count": 0,
        "provider_too_close_count": 7,
        "provider_discovery_source_method": "PUBLIC_ANONYMOUS_FACTS_CENTER_LIVE_OR_PREMATCH_EVENTS_GET",
        "provider_discovery_strategy_id": "ATHENA_CURRENT_SHADOW_PAGINATED_GLOBAL_DISCOVERY_V1",
        "provider_discovery_observed_at": "2026-09-19T11:49:46.016668Z",
        "source_viability": "PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS",
        "current_reconciliation_by_request_date": {
            "20260917": {
                "provider_event_count": 4,
                "provider_prematch_bookable_count": 0,
                "provider_inplay_count": 4,
                "provider_future_lead_eligible_count": 0,
                "provider_too_close_count": 4,
                "reconciled_fixture_count": 0,
                "disposition_counts": dispositions,
            },
            "20260918": {
                "provider_event_count": 3,
                "provider_prematch_bookable_count": 0,
                "provider_inplay_count": 3,
                "provider_future_lead_eligible_count": 0,
                "provider_too_close_count": 3,
                "reconciled_fixture_count": 0,
                "disposition_counts": {
                    "NO_EXACT_FIXTURE_MATCH": 1,
                    "PROVIDER_ONLY": 1,
                },
            },
        }
    }


def _bundle(*, router_inputs=(), source_summary=None):
    return SimpleNamespace(
        router_inputs=router_inputs,
        reviewed_fixture_count=6,
        reconciled_fixture_count=0,
        provider_event_count=7,
        priced_fixture_count=0,
        source_summary=_summary() if source_summary is None else source_summary,
    )


def _mark_source_prematch_bookable(summary):
    summary["provider_prematch_bookable_count"] = 7
    summary["provider_inplay_count"] = 0
    summary["provider_future_lead_eligible_count"] = 7
    summary["provider_too_close_count"] = 0
    summary["source_viability"] = "PROSPECTIVE_DISCOVERY_ELIGIBLE"
    for row in summary["current_reconciliation_by_request_date"].values():
        row["provider_prematch_bookable_count"] = row["provider_event_count"]
        row["provider_inplay_count"] = 0
        row["provider_future_lead_eligible_count"] = row["provider_event_count"]
        row["provider_too_close_count"] = 0
    return summary


def _diagnostic_from_error(exc: BaseException):
    message = str(exc)
    assert message.startswith(capture._ZERO_ROUTER_DIAGNOSTIC_PREFIX)
    return json.loads(message.removeprefix(capture._ZERO_ROUTER_DIAGNOSTIC_PREFIX))


def test_nonempty_router_inputs_pass_without_diagnostic_failure():
    assert capture._require_nonempty_router_inputs(
        _bundle(router_inputs=(object(),))
    ) is None


def test_zero_router_inputs_raise_with_deterministic_reconciliation_diagnostic():
    with pytest.raises(capture.P30PairedCaptureError) as caught:
        capture._require_nonempty_router_inputs(_bundle())

    diagnostic = _diagnostic_from_error(caught.value)
    assert diagnostic == {
        "failure_code": "PROVIDER_DISCOVERY_NO_PREMATCH_EVENTS",
        "reviewed_fixture_count": 6,
        "reconciled_fixture_count": 0,
        "provider_event_count": 7,
        "priced_fixture_count": 0,
        "provider_prematch_bookable_count": 0,
        "provider_inplay_count": 7,
        "provider_future_lead_eligible_count": 0,
        "provider_too_close_count": 7,
        "provider_discovery_source_method": "PUBLIC_ANONYMOUS_FACTS_CENTER_LIVE_OR_PREMATCH_EVENTS_GET",
        "provider_discovery_strategy_id": "ATHENA_CURRENT_SHADOW_PAGINATED_GLOBAL_DISCOVERY_V1",
        "provider_discovery_observed_at": "2026-09-19T11:49:46.016668Z",
        "source_viability": "PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS",
        "request_date_counts": {
            "20260917": {
                "provider_event_count": 4,
                "provider_prematch_bookable_count": 0,
                "provider_inplay_count": 4,
                "provider_future_lead_eligible_count": 0,
                "provider_too_close_count": 4,
                "reconciled_fixture_count": 0,
            },
            "20260918": {
                "provider_event_count": 3,
                "provider_prematch_bookable_count": 0,
                "provider_inplay_count": 3,
                "provider_future_lead_eligible_count": 0,
                "provider_too_close_count": 3,
                "reconciled_fixture_count": 0,
            },
        },
        "disposition_totals": {
            "NO_EXACT_FIXTURE_MATCH": 6,
            "PROVIDER_ONLY": 3,
        },
    }
    assert len(str(caught.value)) <= capture.FAILURE_MESSAGE_MAX_CHARS


def test_zero_router_inputs_taxonomy_codes():
    # NO_RECONCILED_PROVIDER_EVENTS_DISCOVERED
    b0 = _bundle()
    b0.provider_event_count = 0
    with pytest.raises(capture.P30PairedCaptureError) as c0:
        capture._require_nonempty_router_inputs(b0)
    assert _diagnostic_from_error(c0.value)["failure_code"] == "NO_RECONCILED_PROVIDER_EVENTS_DISCOVERED"

    # NO_MARKETS_RECONCILED_FOR_ROUTER
    b1 = _bundle()
    b1.reconciled_fixture_count = 2
    b1.priced_fixture_count = 0
    b1.source_summary = _mark_source_prematch_bookable(_summary())
    with pytest.raises(capture.P30PairedCaptureError) as c1:
        capture._require_nonempty_router_inputs(b1)
    assert _diagnostic_from_error(c1.value)["failure_code"] == "NO_MARKETS_RECONCILED_FOR_ROUTER"

    # ZERO_ROUTER_INPUTS_POST_PRICING
    b2 = _bundle()
    b2.reconciled_fixture_count = 2
    b2.priced_fixture_count = 2
    b2.source_summary = _mark_source_prematch_bookable(_summary())
    with pytest.raises(capture.P30PairedCaptureError) as c2:
        capture._require_nonempty_router_inputs(b2)
    assert _diagnostic_from_error(c2.value)["failure_code"] == "ZERO_ROUTER_INPUTS_POST_PRICING"



def test_zero_router_diagnostic_rejects_malformed_source_summary_fail_closed():
    malformed = _summary()
    malformed["current_reconciliation_by_request_date"]["20260917"][
        "disposition_counts"
    ]["NO_EXACT_FIXTURE_MATCH"] = True

    with pytest.raises(
        capture.P30PairedCaptureError,
        match="zero Router input diagnostic is malformed: disposition_row",
    ):
        capture._require_nonempty_router_inputs(
            _bundle(source_summary=malformed)
        )


def test_zero_router_diagnostic_remains_bounded_with_large_disposition_vocabulary():
    many = {
        f"REVIEWED_DIAGNOSTIC_DISPOSITION_{index:03d}_WITH_LONG_NAME": index
        for index in range(100)
    }
    summary = {
        "provider_event_count": 100,
        "provider_prematch_bookable_count": 100,
        "provider_inplay_count": 0,
        "provider_future_lead_eligible_count": 100,
        "provider_too_close_count": 0,
        "provider_discovery_source_method": "PUBLIC_ANONYMOUS_FACTS_CENTER_WAP_CONFIGURABLE_UPCOMING_EVENTS_GET",
        "provider_discovery_strategy_id": "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1",
        "provider_discovery_observed_at": "2026-09-19T11:49:46.016668Z",
        "source_viability": "PROSPECTIVE_DISCOVERY_ELIGIBLE",
        "current_reconciliation_by_request_date": {
            "20260917": {
                "provider_event_count": 100,
                "provider_prematch_bookable_count": 100,
                "provider_inplay_count": 0,
                "provider_future_lead_eligible_count": 100,
                "provider_too_close_count": 0,
                "reconciled_fixture_count": 0,
                "disposition_counts": many,
            }
        }
    }
    with pytest.raises(capture.P30PairedCaptureError) as caught:
        capture._require_nonempty_router_inputs(
            _bundle(source_summary=summary)
        )

    message = str(caught.value)
    assert message.startswith(capture._ZERO_ROUTER_DIAGNOSTIC_PREFIX)
    assert len(message) <= capture.FAILURE_MESSAGE_MAX_CHARS
    diagnostic = _diagnostic_from_error(caught.value)
    assert diagnostic["reviewed_fixture_count"] == 6
    assert diagnostic["reconciled_fixture_count"] == 0
    assert diagnostic["provider_event_count"] == 7
    assert diagnostic["priced_fixture_count"] == 0


def test_execute_capture_fails_before_legacy_when_router_input_set_is_empty(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(capture, "_git_head", lambda _root: "a" * 40)
    monkeypatch.setattr(capture, "_lineage_main_sha", lambda: "b" * 40)
    monkeypatch.setattr(
        capture.shadow_core_adapter,
        "resolve_shadow_canonical_core",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(capture, "_authority_projection", lambda _bindings: {})
    monkeypatch.setattr(capture, "_collect_sources", lambda **_kwargs: _bundle())

    legacy_called = False

    def legacy_must_not_run(_sources):
        nonlocal legacy_called
        legacy_called = True
        raise AssertionError("legacy execution must not run without Router inputs")

    monkeypatch.setattr(capture, "_legacy_observations", legacy_must_not_run)

    with pytest.raises(
        capture.P30PairedCaptureError,
        match="source acquisition produced zero Router inputs",
    ):
        capture.execute_capture(
            request_dates=("20260917",),
            fixture_cap=50,
            output_dir=tmp_path / "capture",
            repository_root=tmp_path,
        )

    assert legacy_called is False
