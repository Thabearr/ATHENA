from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime
from scripts import audit_inc_20261010_pc_upcoming_bounded_epoch_stabilization as audit

UTC = timezone.utc


def _event(number: int) -> dict:
    return {
        "eventId": f"sr:match:{99000000000 + number}",
        "homeTeamId": f"sr:competitor:{88000000000 + number * 2}",
        "homeTeamName": f"Synthetic Home {number}",
        "awayTeamId": f"sr:competitor:{88000000001 + number * 2}",
        "awayTeamName": f"Synthetic Away {number}",
        "estimateStartTime": int(datetime(2026, 10, 10, 12, tzinfo=UTC).timestamp() * 1000),
        "status": 0,
        "matchStatus": "Not start",
        "bookingStatus": "Booked",
    }


def _raw(total: int, numbers: range) -> bytes:
    return json.dumps({
        "bizCode": 10000,
        "data": {
            "totalNum": total,
            "tournaments": [{
                "id": "sr:tournament:242",
                "name": "Synthetic League",
                "categoryId": "sr:category:26",
                "categoryName": "Synthetic",
                "events": [_event(number) for number in numbers],
            }],
        },
    }, separators=(",", ":")).encode("utf-8")


def _install_pages(monkeypatch: pytest.MonkeyPatch, pages):
    requested: list[int] = []

    def fetch(page_num: int, nonce: int):
        index = len(requested)
        requested.append(page_num)
        if index >= len(pages):
            raise AssertionError("unexpected extra epoch or per-page retry")
        item = pages[index]
        if isinstance(item, Exception):
            raise item
        observed_at = datetime.fromtimestamp(nonce / 1000, tz=UTC) + timedelta(seconds=1)
        expected_page, total, numbers = item
        assert page_num == expected_page
        return _raw(total, numbers), observed_at

    monkeypatch.setattr(source, "_fetch_page", fetch)
    return requested


def _drift(start: int):
    return [
        (1, 1053, range(start, start + 100)),
        (2, 1052, range(start + 100, start + 200)),
    ]


def _stable(start: int):
    return [
        (1, 101, range(start, start + 100)),
        (2, 101, range(start + 100, start + 101)),
    ]


def test_contract_is_four_independent_epochs_with_finite_request_bound():
    runtime.validate_contract()
    assert runtime.calculate_policy_sha256() == runtime.PINNED_POLICY_SHA256 == (
        "9dc0cfb362cf7008d28bcf029755b7361481b683e41155528f9607047773ceba"
    )
    assert runtime.MAX_CAPTURE_EPOCHS == 4
    assert runtime.MAX_PAGES_PER_EPOCH == 20
    assert runtime.MAX_SUCCESSFUL_PAGE_RESPONSES == 80
    assert runtime.INTER_EPOCH_BACKOFF_SECONDS == 3
    policy = runtime._policy_payload()["capture_stabilization"]
    assert policy["no_per_page_http_retry"] is True
    assert policy["no_capture_epoch_beyond_bound"] is True
    assert policy["cross_epoch_event_merge"] is False
    assert policy["provider_request_upper_bound"] == 80


def test_two_drift_epochs_then_third_stable_epoch_is_accepted(monkeypatch, tmp_path):
    requested = _install_pages(monkeypatch, [*_drift(1), *_drift(1000), *_stable(2000)])
    sleeps: list[int] = []
    monkeypatch.setattr(runtime.time, "sleep", sleeps.append)

    root, manifest = runtime.capture_current_pc_upcoming_discovery(
        repository_root=tmp_path, execute_live_network=True
    )

    assert requested == [1, 2, 1, 2, 1, 2]
    assert sleeps == [3, 3]
    assert manifest.captured_event_count == manifest.provider_total_num == 101
    assert {event.event_id for event in manifest.events} == {
        f"sr:match:{99000000000 + number}" for number in range(2000, 2101)
    }
    state = runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)
    assert state["attempt_count"] == 3
    assert state["accepted_attempt_index"] == 3
    assert state["failed_attempt_indices"] == [1, 2]
    assert state["final_state"] == "ACCEPTED_ATTEMPT_3"
    assert (root / "manifest.json").is_file()


def test_three_drift_epochs_then_fourth_stable_epoch_is_accepted(monkeypatch, tmp_path):
    requested = _install_pages(
        monkeypatch,
        [*_drift(1), *_drift(1000), *_drift(2000), *_stable(3000)],
    )
    sleeps: list[int] = []
    monkeypatch.setattr(runtime.time, "sleep", sleeps.append)

    _root, manifest = runtime.capture_current_pc_upcoming_discovery(
        repository_root=tmp_path, execute_live_network=True
    )

    assert requested == [1, 2, 1, 2, 1, 2, 1, 2]
    assert sleeps == [3, 3, 3]
    assert manifest.captured_event_count == 101
    state = runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)
    assert state["attempt_count"] == 4
    assert state["accepted_attempt_index"] == 4
    assert state["failed_attempt_indices"] == [1, 2, 3]


def test_four_drift_epochs_fail_closed_without_fifth_epoch(monkeypatch, tmp_path):
    requested = _install_pages(
        monkeypatch,
        [*_drift(1), *_drift(1000), *_drift(2000), *_drift(3000)],
    )
    sleeps: list[int] = []
    monkeypatch.setattr(runtime.time, "sleep", sleeps.append)

    with pytest.raises(
        runtime.PcUpcomingRuntimeReconciliationError,
        match=r"all 4 allowed capture epochs failed",
    ):
        runtime.capture_current_pc_upcoming_discovery(
            repository_root=tmp_path, execute_live_network=True
        )

    assert requested == [1, 2, 1, 2, 1, 2, 1, 2]
    assert sleeps == [3, 3, 3]
    evidence_root = tmp_path / source.EVIDENCE_ROOT
    assert not (evidence_root / "manifest.json").exists()
    state = runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)
    assert state["attempt_count"] == 4
    assert state["accepted_attempt_index"] is None
    assert state["failed_attempt_indices"] == [1, 2, 3, 4]
    assert state["final_state"] == "FAILED_AFTER_EXACT_TOTALNUM_DRIFT"


def test_non_drift_failure_never_consumes_extra_epochs(monkeypatch, tmp_path):
    requested = _install_pages(
        monkeypatch,
        [*_drift(1), source.PcUpcomingDiscoveryError("provider returned HTTP 503")],
    )
    sleeps: list[int] = []
    monkeypatch.setattr(runtime.time, "sleep", sleeps.append)

    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="HTTP 503"):
        runtime.capture_current_pc_upcoming_discovery(
            repository_root=tmp_path, execute_live_network=True
        )

    assert requested == [1, 2, 1]
    assert sleeps == [3]
    state = runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)
    assert state["attempt_count"] == 2
    assert state["accepted_attempt_index"] is None
    assert state["failed_attempt_indices"] == [1, 2]


def test_successor_architecture_receipt_and_current_contract_audit():
    result = audit.audit()
    assert result["status"] == "PASSED"
    assert result["policy_id"] == audit.POLICY_ID
    assert result["receipt_sha256"] == (
        "ff6688223bf9502b2e90015e30266cad555286d0ff8bd34c44d5a515762ac755"
    )
    assert result["runtime_policy_sha256"] == runtime.PINNED_POLICY_SHA256
    assert result["max_capture_epochs"] == 4
    assert result["max_successful_page_responses"] == 80
    assert result["inter_epoch_backoff_seconds"] == 3
