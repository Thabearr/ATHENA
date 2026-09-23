from __future__ import annotations

import pytest

from domain.ingest_contracts import (
    AthenaIngestContractError, AthenaIngestRequest, canonical_json_bytes,
    make_failure_receipt, parse_dates_input, strict_json_loads,
    validate_exact_commit_sha,
)


def test_exact_request_round_trip_and_bounds() -> None:
    for count in (1, 7):
        dates = tuple(f"202609{day:02d}" for day in range(1, count + 1))
        request = AthenaIngestRequest.for_dates(dates)
        assert AthenaIngestRequest.from_mapping(strict_json_loads(request.canonical_bytes)) == request
        assert request.canonical_bytes == canonical_json_bytes(request.to_dict())
        assert len(request.canonical_sha256) == 64


@pytest.mark.parametrize("value", [
    "", "20260901,", "20260901,20260901", "20260902,20260901",
    "20260230", "20261301", "2026091", "today", "20260901, 20260902",
    "20260901,20260902,20260903,20260904,20260905,20260906,20260907,20260908",
    "٢٠٢٦٠٩٠١", "20260901\n",
])
def test_bad_date_input_fails_closed(value: str) -> None:
    with pytest.raises(AthenaIngestContractError):
        parse_dates_input(value)


def test_exact_request_fields_and_authority_identity() -> None:
    base = AthenaIngestRequest.for_dates(("20260901",)).to_dict()
    for mutation in (
        dict(base, provider="sportybet"), dict(base, provider="FOTMOB"),
        dict(base, timezone="Africa/Lagos"), dict(base, ccode3="USA"),
        dict(base, schema_version=True), dict(base, extra="unreviewed"),
        {key: value for key, value in base.items() if key != "ccode3"},
    ):
        with pytest.raises(AthenaIngestContractError):
            AthenaIngestRequest.from_mapping(mutation)
    with pytest.raises(AthenaIngestContractError):
        strict_json_loads(b'{"dates":[],"dates":[]}')


@pytest.mark.parametrize("value", ["A" * 40, "a" * 39, "a" * 41, "g" * 40, True])
def test_exact_commit_sha_is_strict(value: object) -> None:
    with pytest.raises(AthenaIngestContractError):
        validate_exact_commit_sha(value)


def test_invalid_request_partial_receipt_has_only_digest_not_raw_input() -> None:
    import hashlib

    raw_input = "20260901,not-a-date".encode("utf-8")
    receipt = make_failure_receipt(
        exact_commit_sha="c" * 40, failure_code="INVALID_REQUEST",
        stage="REQUEST_RESOLUTION", raw_request_input_sha256=hashlib.sha256(raw_input).hexdigest(),
    )
    assert receipt.status == "FAILED"
    assert receipt.exact_commit_sha == "c" * 40
    assert receipt.request_sha256 is None
    assert receipt.canonical_store_update_sha256 is None
    assert receipt.raw_request_input_sha256 == hashlib.sha256(raw_input).hexdigest()
    assert receipt.provider_request_count == 0
    assert receipt.source_count == 0
    assert receipt.canonical_store_update_committed is False
    assert all(value is False for key, value in receipt.authorities.items() if key != "provider_acquisition")


def test_stage_code_pair_is_fail_closed() -> None:
    from dataclasses import replace

    receipt = make_failure_receipt(
        exact_commit_sha="d" * 40, failure_code="TIMEOUT", stage="SOURCE_ACQUISITION",
        request_sha256="e" * 64, canonical_store_update_sha256="f" * 64,
    )
    assert receipt.stage == "SOURCE_ACQUISITION"
    with pytest.raises(AthenaIngestContractError, match="failure stage"):
        replace(receipt, stage="COMPLETED")
