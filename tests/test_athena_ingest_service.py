from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from domain.fotmob_data_matches_capture import CapturedFotMobDataMatchesResponse
from domain.ingest_contracts import (
    AthenaCanonicalStoreUpdate, AthenaIngestRequest, NOT_COMMITTED, READY,
    strict_json_loads,
)
from services.athena_ingest_service import ARTIFACT_RELATIVE, execute_ingest_request


OBSERVED = datetime(2026, 9, 23, 10, 7, tzinfo=timezone.utc)


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
        acquisition_callable=acquire,
    )
    assert calls == list(dates)
    assert receipt.status == "SUCCESS"
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
        repository_root=tmp_path, acquisition_callable=acquire,
    )
    assert calls == ["20260901", "20260902"]
    assert receipt.status == "FAILED"
    assert receipt.failure_code == "PROVIDER_ACQUISITION_FAILED"
    assert receipt.provider_request_count == 2
    assert receipt.source_count == 1
    update = AthenaCanonicalStoreUpdate.from_mapping(strict_json_loads(
        (tmp_path / ARTIFACT_RELATIVE / "canonical-store-update.json").read_bytes()
    ))
    assert update.commit_status == NOT_COMMITTED
    assert len(update.source_records) == 1


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
        acquisition_callable=acquire,
    )
    assert receipt.status == "FAILED"
    assert receipt.source_count == 0
    assert receipt.authorities["canonical_source_update"] is False
