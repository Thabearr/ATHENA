from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from domain.sportybet_lite_source_capture import (
    ALLOWED_OUTPUT_RELATIVE,
    DEFAULT_MARKET_GROUP,
    FOOTBALL_SPORT_ID,
    CapturedSportyBetLiteResponse,
    SportyBetLiteCaptureError,
    SportyBetLiteRequestKind,
    _sync_directory,
    store_capture,
    verify_capture_directory,
)
from domain.sportybet_provider_native_inventory import extract_native_selections


OBSERVED = dt.datetime(2026, 8, 18, 12, 30, tzinfo=dt.timezone.utc)
EVENT_ID = "sr:match:72738018"


def _selection_html(*, specifier: str = "total=2.5") -> bytes:
    encoded = specifier.replace("=", "%3D")
    href = (
        "/ng/lite/preMatch/detail?"
        f"eventId={EVENT_ID.replace(':', '%3A')}"
        "&marketGroupsName=Main"
        "&marketId=18"
        "&odds=1.76"
        "&outcomeId=12"
        "&productId=3"
        "&selected=0"
        f"&specifier={encoded}"
        "&sportId=sr%3Asport%3A1"
    )
    return f'<html><body><a href="{href}">Over 2.5 1.76</a></body></html>'.encode()


def _response(*, network: bool = True) -> CapturedSportyBetLiteResponse:
    body = _selection_html()
    return CapturedSportyBetLiteResponse(
        status=200,
        content_type="text/html; charset=utf-8",
        content_length=len(body),
        body=body,
        observed_at=OBSERVED,
        network_acquisition_performed=network,
    )


def _store(repo: Path, *, network: bool = True):
    return store_capture(
        _response(network=network),
        request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
        repository_root=repo,
        event_id=EVENT_ID,
        sport_id=FOOTBALL_SPORT_ID,
        market_groups_name=DEFAULT_MARKET_GROUP,
    )


def test_verified_capture_directory_name_is_cryptographically_bound(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    capture, _ = _store(repo)
    renamed = capture.with_name("0" * 24)
    capture.rename(renamed)
    with pytest.raises(SportyBetLiteCaptureError, match="directory identity"):
        verify_capture_directory(
            renamed,
            allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
        )


def test_network_provenance_is_required_by_default(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    capture, _ = _store(repo, network=False)
    with pytest.raises(SportyBetLiteCaptureError, match="network provenance"):
        verify_capture_directory(
            capture,
            allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
        )
    verified = verify_capture_directory(
        capture,
        allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
        require_network_acquisition_performed=False,
    )
    assert verified.network_acquisition_performed is False


def test_line_sensitive_current_lite_specifier_is_preserved_exactly():
    selection = extract_native_selections(_selection_html())[0]
    assert selection.event_id == EVENT_ID
    assert selection.market_id == "18"
    assert selection.outcome_id == "12"
    assert selection.specifier == "total=2.5"
    assert selection.odds_raw == "1.76"


def test_asian_handicap_specifier_is_not_collapsed_into_total_line():
    total = extract_native_selections(_selection_html(specifier="total=2.5"))[0]
    handicap = extract_native_selections(_selection_html(specifier="hcp=-2.5"))[0]
    assert total.market_identity == ("18", "total=2.5")
    assert handicap.market_identity == ("18", "hcp=-2.5")
    assert total.market_identity != handicap.market_identity


def test_directory_durability_fails_closed_on_unknown_platform(tmp_path: Path):
    directory = tmp_path / "dir"
    directory.mkdir()
    with pytest.raises(SportyBetLiteCaptureError, match="unsupported"):
        _sync_directory(directory, platform_name="mystery-os")
