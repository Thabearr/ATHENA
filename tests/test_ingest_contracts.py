from __future__ import annotations

import pytest

from domain.ingest_contracts import (
    AthenaIngestContractError, AthenaIngestRequest, canonical_json_bytes,
    parse_dates_input, strict_json_loads,
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
