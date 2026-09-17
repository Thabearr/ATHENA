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
        "current_reconciliation_by_request_date": {
            "20260917": {
                "provider_event_count": 4,
                "reconciled_fixture_count": 0,
                "disposition_counts": dispositions,
            },
            "20260918": {
                "provider_event_count": 3,
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
        "reviewed_fixture_count": 6,
        "reconciled_fixture_count": 0,
        "provider_event_count": 7,
        "priced_fixture_count": 0,
        "request_date_counts": {
            "20260917": [4, 0],
            "20260918": [3, 0],
        },
        "disposition_totals": {
            "NO_EXACT_FIXTURE_MATCH": 6,
            "PROVIDER_ONLY": 3,
        },
    }
    assert len(str(caught.value)) <= capture.FAILURE_MESSAGE_MAX_CHARS


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
        "current_reconciliation_by_request_date": {
            "20260917": {
                "provider_event_count": 100,
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
