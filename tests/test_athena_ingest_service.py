from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from domain.fotmob_data_matches_capture import CapturedFotMobDataMatchesResponse
from domain.ingest_contracts import (
    AthenaCanonicalStoreUpdate, AthenaIngestRequest, NOT_COMMITTED, READY,
    strict_json_loads,
)
from services.athena_ingest_service import (
    ARTIFACT_RELATIVE, INGEST_SERVICE_BUDGET_SECONDS, RECEIPT_NAME,
    REQUEST_NAME, UPDATE_NAME, AthenaIngestServiceError,
    _safe_directory, execute_ingest_request,
)


OBSERVED = datetime(2026, 9, 23, 10, 7, tzinfo=timezone.utc)
COMMIT_SHA = "a" * 40


def fake_response(date: str) -> CapturedFotMobDataMatchesResponse:
    raw = ('{"date":"' + date + '","opaque":true}\n').encode()
    return CapturedFotMobDataMatchesResponse(
        status=200, content_type="application/json", content_length=len(raw),
        body=raw, observed_at=OBSERVED, network_acquisition_performed=True,
    )


@pytest.mark.parametrize("count", [1, 7])
def test_one_request_per_date_exact_order_and_immutable_sources(tmp_path: Path, count: int) -> None:
    dates = tuple(f"202609{day:02d}" for day in range(1, count + 1))
    calls: list[str] = []
    def acquire(*, request_date: str, timezone: str, ccode3: str):
        assert (timezone, ccode3) == ("UTC", "NGA")
        calls.append(request_date)
        return fake_response(request_date)
    receipt = execute_ingest_request(
        AthenaIngestRequest.for_dates(dates), repository_root=tmp_path,
        exact_commit_sha=COMMIT_SHA,
        acquisition_callable=acquire,
    )
    assert calls == list(dates)
    assert receipt.status == "SUCCESS"
    assert receipt.exact_commit_sha == COMMIT_SHA
    assert receipt.stage == "COMPLETED"
    assert receipt.provider_request_count == count
    assert receipt.canonical_store_update_committed is True
    update = AthenaCanonicalStoreUpdate.from_mapping(strict_json_loads(
        (tmp_path / ARTIFACT_RELATIVE / "canonical-store-update.json").read_bytes()
    ))
    assert update.commit_status == READY
    assert [item.request_date for item in update.source_records] == list(dates)
    for record in update.source_records:
        assert (tmp_path / ARTIFACT_RELATIVE / record.capture_relative_path / "response.json").read_bytes() == fake_response(record.request_date).body


def test_failure_stops_without_retry_and_preserves_partial_evidence(tmp_path: Path) -> None:
    calls: list[str] = []
    def acquire(*, request_date: str, timezone: str, ccode3: str):
        calls.append(request_date)
        if len(calls) == 2:
            raise OSError("offline simulated provider failure")
        return fake_response(request_date)
    receipt = execute_ingest_request(
        AthenaIngestRequest.for_dates(("20260901", "20260902", "20260903")),
        repository_root=tmp_path, exact_commit_sha=COMMIT_SHA, acquisition_callable=acquire,
    )
    assert calls == ["20260901", "20260902"]
    assert receipt.status == "FAILED"
    assert receipt.failure_code == "PROVIDER_ACQUISITION_FAILED"
    assert receipt.exact_commit_sha == COMMIT_SHA
    assert receipt.stage == "SOURCE_ACQUISITION"
    assert receipt.provider_request_count == 2
    assert receipt.source_count == 1
    update = AthenaCanonicalStoreUpdate.from_mapping(strict_json_loads(
        (tmp_path / ARTIFACT_RELATIVE / "canonical-store-update.json").read_bytes()
    ))
    assert update.commit_status == NOT_COMMITTED
    assert len(update.source_records) == 1


def test_unexpected_acquisition_exception_still_emits_fail_closed_receipt(tmp_path: Path) -> None:
    attempts: list[str] = []
    def acquire(*, request_date: str, timezone: str, ccode3: str):
        attempts.append(request_date)
        raise RuntimeError("injected offline fault")
    receipt = execute_ingest_request(
        AthenaIngestRequest.for_dates(("20260901", "20260902")),
        repository_root=tmp_path, exact_commit_sha=COMMIT_SHA, acquisition_callable=acquire,
    )
    assert attempts == ["20260901"]
    assert receipt.failure_code == "PROVIDER_ACQUISITION_FAILED"
    assert receipt.exact_commit_sha == COMMIT_SHA
    assert receipt.provider_request_count == 1
    assert receipt.canonical_store_update_committed is False
    assert (tmp_path / ARTIFACT_RELATIVE / "ingest-receipt.json").read_bytes() == receipt.canonical_bytes


def test_unreviewed_acquisition_provenance_fails_closed(tmp_path: Path) -> None:
    def acquire(*, request_date: str, timezone: str, ccode3: str):
        value = fake_response(request_date)
        return CapturedFotMobDataMatchesResponse(
            status=value.status, content_type=value.content_type,
            content_length=value.content_length, body=value.body,
            observed_at=value.observed_at, network_acquisition_performed=False,
        )
    receipt = execute_ingest_request(
        AthenaIngestRequest.for_dates(("20260901",)), repository_root=tmp_path,
        exact_commit_sha=COMMIT_SHA,
        acquisition_callable=acquire,
    )
    assert receipt.status == "FAILED"
    assert receipt.source_count == 0
    assert receipt.authorities["canonical_source_update"] is False
    assert receipt.exact_commit_sha == COMMIT_SHA


def test_source_validation_failure_is_typed_and_commit_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def invalid_verify(*args, **kwargs):
        raise ValueError("injected offline source validation failure")
    monkeypatch.setattr("services.athena_ingest_service.verify_data_matches_capture_directory", invalid_verify)
    receipt = execute_ingest_request(
        AthenaIngestRequest.for_dates(("20260901",)), repository_root=tmp_path,
        exact_commit_sha=COMMIT_SHA,
        acquisition_callable=lambda **kwargs: fake_response(kwargs["request_date"]),
    )
    assert receipt.failure_code == "SOURCE_CAPTURE_VALIDATION_FAILED"
    assert receipt.stage == "SOURCE_PERSISTENCE"
    assert receipt.exact_commit_sha == COMMIT_SHA
    assert receipt.provider_request_count == 1
    assert receipt.source_count == 0


def test_artifact_persistence_failure_is_typed_when_receipt_can_be_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_copy(*args, **kwargs):
        raise OSError("injected offline artifact persistence failure")
    monkeypatch.setattr("services.athena_ingest_service._copy_capture", fail_copy)
    receipt = execute_ingest_request(
        AthenaIngestRequest.for_dates(("20260901",)), repository_root=tmp_path,
        exact_commit_sha=COMMIT_SHA,
        acquisition_callable=lambda **kwargs: fake_response(kwargs["request_date"]),
    )
    assert receipt.failure_code == "ARTIFACT_PERSISTENCE_FAILED"
    assert receipt.stage == "SOURCE_PERSISTENCE"
    assert receipt.exact_commit_sha == COMMIT_SHA
    assert (tmp_path / ARTIFACT_RELATIVE / RECEIPT_NAME).read_bytes() == receipt.canonical_bytes


def test_artifact_path_traversal_and_contradictory_request_fail_before_acquisition(tmp_path: Path) -> None:
    with pytest.raises(AthenaIngestServiceError, match="traversal"):
        _safe_directory(Path("artifacts/../outside"), tmp_path)
    root = tmp_path / ARTIFACT_RELATIVE
    root.mkdir(parents=True)
    (root / REQUEST_NAME).write_bytes(b"contradictory")
    calls: list[str] = []
    def acquire(*, request_date: str, timezone: str, ccode3: str):
        calls.append(request_date)
        return fake_response(request_date)
    with pytest.raises(AthenaIngestServiceError, match="overwrite"):
        execute_ingest_request(
            AthenaIngestRequest.for_dates(("20260901",)), repository_root=tmp_path,
            exact_commit_sha=COMMIT_SHA,
            acquisition_callable=acquire,
        )
    assert calls == []


def test_service_budget_timeout_preserves_completed_source_and_stops_next_date(tmp_path: Path) -> None:
    dates = ("20260901", "20260902", "20260903")
    calls: list[str] = []
    clock_values = iter((0, 0, 0, 0, INGEST_SERVICE_BUDGET_SECONDS + 1))
    def clock() -> float:
        return float(next(clock_values))
    def acquire(*, request_date: str, timezone: str, ccode3: str):
        calls.append(request_date)
        return fake_response(request_date)

    receipt = execute_ingest_request(
        AthenaIngestRequest.for_dates(dates), repository_root=tmp_path,
        exact_commit_sha=COMMIT_SHA, acquisition_callable=acquire,
        monotonic_clock=clock,
    )
    root = tmp_path / ARTIFACT_RELATIVE
    assert calls == ["20260901"]
    assert receipt.status == "FAILED"
    assert receipt.failure_code == "TIMEOUT"
    assert receipt.stage == "SOURCE_ACQUISITION"
    assert receipt.exact_commit_sha == COMMIT_SHA
    assert receipt.provider_request_count == 1
    assert receipt.source_count == 1
    assert receipt.canonical_store_update_committed is False
    update = AthenaCanonicalStoreUpdate.from_mapping(strict_json_loads((root / UPDATE_NAME).read_bytes()))
    assert update.commit_status == NOT_COMMITTED
    assert len(update.source_records) == 1
    record = update.source_records[0]
    assert (root / record.capture_relative_path / "response.json").read_bytes() == fake_response("20260901").body
    assert (root / RECEIPT_NAME).read_bytes() == receipt.canonical_bytes
