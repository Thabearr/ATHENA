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
    build_capture_manifest,
    canonical_manifest_bytes,
    capture_identifier,
    request_target,
    sha256_bytes,
    store_capture,
    validate_html_content_type,
    verify_capture_directory,
)
from domain.sportybet_provider_native_inventory import (
    NativeAvailability,
    SportyBetProviderInventoryError,
    build_inventory,
    canonical_inventory_bytes,
    extract_native_selections,
)
from scripts.capture_sportybet_lite_source import (
    AUTOMATED_NETWORK_BLOCK_STATE,
    build_blocked_receipt,
    canonical_blocked_receipt_bytes,
    main as capture_main,
)
from services.betting_service import (
    BOOKMAKER_RESOLUTION_BLOCK_STATE,
    BettingService,
)


OBSERVED = dt.datetime(2026, 8, 18, 12, 0, tzinfo=dt.timezone.utc)
EVENT_ID = "sr:match:72348790"


def _href(
    *,
    market_id: str,
    outcome_id: str,
    odds: str,
    specifier: str | None = None,
    event_id: str = EVENT_ID,
) -> str:
    parts = [
        f"eventId={event_id.replace(':', '%3A')}",
        "marketGroupsName=Main",
        f"marketId={market_id}",
        f"odds={odds}",
        f"outcomeId={outcome_id}",
        "productId=3",
        "selected=0",
        "sportId=sr%3Asport%3A1",
    ]
    if specifier is not None:
        parts.append("specifier=" + specifier.replace("=", "%3D"))
    return "/ng/lite?" + "&".join(parts)


def _html(links: list[str] | None = None) -> bytes:
    links = links or [
        _href(market_id="1", outcome_id="1", odds="1.40"),
        _href(market_id="1", outcome_id="2", odds="5.40"),
        _href(market_id="1", outcome_id="3", odds="8.23"),
        _href(market_id="18", outcome_id="12", odds="1.86", specifier="total=2.5"),
        _href(market_id="18", outcome_id="13", odds="1.96", specifier="total=2.5"),
        _href(market_id="18", outcome_id="12", odds="2.34", specifier="total=3.5"),
        _href(market_id="18", outcome_id="13", odds="1.61", specifier="total=3.5"),
    ]
    anchors: list[str] = []
    for href in links:
        attrs = ""
        if "marketId=18" in href and "outcomeId=13" in href and "total%3D3.5" in href:
            attrs = ' data-status="suspended" data-market-name="Over/Under"'
        odds = href.split("odds=")[1].split("&")[0]
        anchors.append(f'<a href="{href}"{attrs}>{odds}</a>')
    return ("<html><body>" + "".join(anchors) + "</body></html>").encode("utf-8")


def _response(body: bytes | None = None, *, observed_at: dt.datetime = OBSERVED, network: bool = True):
    body = body or _html()
    return CapturedSportyBetLiteResponse(
        status=200,
        content_type="text/html; charset=utf-8",
        content_length=len(body),
        body=body,
        observed_at=observed_at,
        network_acquisition_performed=network,
    )


def _manifest(body: bytes | None = None, *, observed_at: dt.datetime = OBSERVED):
    return build_capture_manifest(
        _response(body, observed_at=observed_at),
        request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
        event_id=EVENT_ID,
        sport_id=FOOTBALL_SPORT_ID,
        market_groups_name=DEFAULT_MARKET_GROUP,
    )


def test_reviewed_request_target_is_exact_public_lite_surface():
    assert request_target(SportyBetLiteRequestKind.INDEX) == "/ng/lite"
    assert request_target(
        SportyBetLiteRequestKind.EVENT_DETAIL,
        event_id=EVENT_ID,
        sport_id=FOOTBALL_SPORT_ID,
        market_groups_name=DEFAULT_MARKET_GROUP,
    ) == (
        "/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A72348790"
        "&marketGroupsName=Main&sportId=sr%3Asport%3A1"
    )


def test_manifest_is_canonical_and_quote_time_stays_unknown():
    manifest = _manifest()
    raw = canonical_manifest_bytes(manifest)
    assert raw.endswith(b"\n")
    assert manifest.provider_quote_at is None
    assert manifest.provider_snapshot_id is None
    assert b'"provider_quote_at":null' in raw
    assert b'"provider_snapshot_id":null' in raw
    assert all(value is False for value in manifest.safety.values())


def test_non_200_media_contradiction_length_mismatch_and_empty_body_fail_closed():
    body = _html()
    with pytest.raises(SportyBetLiteCaptureError):
        CapturedSportyBetLiteResponse(
            status=503,
            content_type="text/html",
            content_length=len(body),
            body=body,
            observed_at=OBSERVED,
            network_acquisition_performed=True,
        )
    with pytest.raises(SportyBetLiteCaptureError):
        validate_html_content_type("application/json")
    with pytest.raises(SportyBetLiteCaptureError):
        CapturedSportyBetLiteResponse(
            status=200,
            content_type="text/html",
            content_length=len(body) + 1,
            body=body,
            observed_at=OBSERVED,
            network_acquisition_performed=True,
        )
    with pytest.raises(SportyBetLiteCaptureError):
        CapturedSportyBetLiteResponse(
            status=200,
            content_type="text/html",
            content_length=0,
            body=b"",
            observed_at=OBSERVED,
            network_acquisition_performed=True,
        )


def test_same_capture_identity_same_bytes_is_idempotent(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    response = _response()
    kwargs = dict(
        request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
        repository_root=repo,
        event_id=EVENT_ID,
        sport_id=FOOTBALL_SPORT_ID,
        market_groups_name=DEFAULT_MARKET_GROUP,
    )
    path1, manifest1 = store_capture(response, **kwargs)
    path2, manifest2 = store_capture(response, **kwargs)
    assert path1 == path2
    assert manifest1.to_dict() == manifest2.to_dict()
    verified = verify_capture_directory(path1, allowed_root=repo / ALLOWED_OUTPUT_RELATIVE)
    assert verified.raw_sha256 == sha256_bytes(response.body)


def test_same_observation_identity_different_bytes_fails_closed(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    kwargs = dict(
        request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
        repository_root=repo,
        event_id=EVENT_ID,
        sport_id=FOOTBALL_SPORT_ID,
        market_groups_name=DEFAULT_MARKET_GROUP,
    )
    first = _response(_html())
    path, manifest = store_capture(first, **kwargs)
    changed = _response(_html([_href(market_id="1", outcome_id="1", odds="1.41")]))
    changed_manifest = build_capture_manifest(
        changed,
        request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
        event_id=EVENT_ID,
        sport_id=FOOTBALL_SPORT_ID,
        market_groups_name=DEFAULT_MARKET_GROUP,
    )
    assert capture_identifier(changed_manifest) == capture_identifier(manifest)
    with pytest.raises(SportyBetLiteCaptureError):
        store_capture(changed, **kwargs)
    assert path.exists()


def test_output_traversal_and_symlink_escape_are_rejected(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(SportyBetLiteCaptureError):
        store_capture(
            _response(),
            request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
            repository_root=repo,
            output_root=Path("../escape"),
            event_id=EVENT_ID,
            sport_id=FOOTBALL_SPORT_ID,
            market_groups_name=DEFAULT_MARKET_GROUP,
        )
    cache = repo / ".cache"
    cache.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (cache / "athena-research").symlink_to(outside, target_is_directory=True)
    with pytest.raises(SportyBetLiteCaptureError):
        store_capture(
            _response(),
            request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
            repository_root=repo,
            event_id=EVENT_ID,
            sport_id=FOOTBALL_SPORT_ID,
            market_groups_name=DEFAULT_MARKET_GROUP,
        )


def test_provider_native_inventory_preserves_ids_lines_and_suspension():
    selections = extract_native_selections(_html())
    assert len(selections) == 7
    assert {item.event_id for item in selections} == {EVENT_ID}
    assert {
        item.market_identity for item in selections if item.market_id == "18"
    } == {("18", "total=2.5"), ("18", "total=3.5")}
    suspended = [
        item for item in selections
        if item.market_id == "18"
        and item.specifier == "total=3.5"
        and item.outcome_id == "13"
    ]
    assert suspended[0].availability is NativeAvailability.SUSPENDED
    assert suspended[0].market_name == "Over/Under"


def test_total_and_handicap_specifiers_remain_distinct():
    total = _href(market_id="18", outcome_id="12", odds="1.76", specifier="total=2.5")
    handicap = _href(market_id="16", outcome_id="1714", odds="5.10", specifier="hcp=-2.5")
    selections = extract_native_selections(_html([total, handicap]))
    assert [(item.market_id, item.specifier) for item in selections] == [
        ("16", "hcp=-2.5"),
        ("18", "total=2.5"),
    ]


def test_event_navigation_is_not_a_selection_but_incomplete_selection_fails():
    event_only = (
        "/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A72348790"
        "&marketGroupsName=Main&sportId=sr%3Asport%3A1"
    )
    selection = _href(market_id="1", outcome_id="1", odds="1.40")
    raw = f'<a href="{event_only}">Fixture</a><a href="{selection}">1.40</a>'.encode()
    assert len(extract_native_selections(raw)) == 1
    missing_market = selection.replace("marketId=1&", "")
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([missing_market]))


def test_invalid_event_duplicate_selection_and_bad_odds_fail_closed():
    invalid_event = _href(
        market_id="1", outcome_id="1", odds="1.40", event_id="bad"
    )
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([invalid_event]))
    duplicate = _href(market_id="1", outcome_id="1", odds="1.40")
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([duplicate, duplicate]))
    changed_odds = _href(market_id="1", outcome_id="1", odds="1.41")
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([duplicate, changed_odds]))
    for bad_odds in ("NaN", "1.00", "-2.00"):
        with pytest.raises(SportyBetProviderInventoryError):
            extract_native_selections(
                _html([_href(market_id="1", outcome_id="1", odds=bad_odds)])
            )


def test_no_fuzzy_canonical_market_mapping_occurs():
    href = _href(market_id="18", outcome_id="12", odds="1.86", specifier="total=2.5")
    raw = (
        '<a data-market-name="Over 2.5" '
        f'href="{href}">Over</a>'
    ).encode()
    item = extract_native_selections(raw)[0]
    assert item.market_name == "Over 2.5"
    assert "canonical" not in item.to_dict()
    assert item.market_identity == ("18", "total=2.5")


def test_observed_at_never_becomes_provider_quote_timestamp_or_snapshot():
    manifest = _manifest()
    manifest_sha = sha256_bytes(canonical_manifest_bytes(manifest))
    inventory = build_inventory(manifest, _html(), source_manifest_sha256=manifest_sha)
    assert inventory.source_observed_at == "2026-08-18T12:00:00.000000Z"
    assert inventory.provider_quote_timestamp_capability == "UNPROVEN_ON_REVIEWED_LITE_HTML"
    assert inventory.provider_snapshot_id_capability == "UNPROVEN_ON_REVIEWED_LITE_HTML"
    assert all(item.provider_quote_at is None for item in inventory.selections)
    assert all(item.provider_snapshot_id is None for item in inventory.selections)


def test_unproven_event_metadata_remains_null_not_guessed():
    manifest = _manifest()
    inventory = build_inventory(
        manifest,
        _html(),
        source_manifest_sha256=sha256_bytes(canonical_manifest_bytes(manifest)),
    )
    event = inventory.events[0]
    assert event.event_id == EVENT_ID
    assert event.competition_id is None
    assert event.competition_name is None
    assert event.home_participant_id is None
    assert event.home_participant_name is None
    assert event.away_participant_id is None
    assert event.away_participant_name is None
    assert event.kickoff is None
    assert event.event_status is None


def test_inventory_order_and_canonical_bytes_are_deterministic():
    links = [
        _href(market_id="1", outcome_id="3", odds="8.23"),
        _href(market_id="18", outcome_id="12", odds="1.86", specifier="total=2.5"),
        _href(market_id="1", outcome_id="1", odds="1.40"),
    ]
    assert [item.selection_identity for item in extract_native_selections(_html(links))] == [
        item.selection_identity for item in extract_native_selections(_html(list(reversed(links))))
    ]
    manifest = _manifest()
    manifest_sha = sha256_bytes(canonical_manifest_bytes(manifest))
    first = build_inventory(manifest, _html(), source_manifest_sha256=manifest_sha)
    second = build_inventory(manifest, _html(), source_manifest_sha256=manifest_sha)
    assert canonical_inventory_bytes(first) == canonical_inventory_bytes(second)
    assert all(value is False for value in first.safety.values())


def test_invalid_utf8_foreign_host_and_plain_http_fail_closed():
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(b"<html>\xff</html>")
    foreign = (
        "https://evil.example/ng/lite?eventId=sr%3Amatch%3A72348790"
        "&marketId=1&outcomeId=1&odds=1.40"
    )
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([foreign]))
    insecure = (
        "http://www.sportybet.com/ng/lite?eventId=sr%3Amatch%3A72348790"
        "&marketId=1&outcomeId=1&odds=1.40"
    )
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([insecure]))


def test_automated_source_command_is_policy_blocked_and_performs_no_network(capsys):
    receipt = build_blocked_receipt(request_kind=SportyBetLiteRequestKind.INDEX)
    assert receipt["status"] == AUTOMATED_NETWORK_BLOCK_STATE
    assert receipt["network_acquisition_performed"] is False
    assert receipt["network_acquisition_authorized"] is False
    assert receipt["bet_authorized"] is False
    raw = canonical_blocked_receipt_bytes(receipt)
    assert raw.endswith(b"\n")
    assert capture_main(["--index"]) == 3
    emitted = capsys.readouterr().out
    assert AUTOMATED_NETWORK_BLOCK_STATE in emitted
    assert '"network_acquisition_performed":false' in emitted


def test_product_facing_sportybet_resolver_remains_fail_closed():
    result = BettingService().resolve_sportybet("ABC123")
    assert result["success"] is False
    assert result["state"] == BOOKMAKER_RESOLUTION_BLOCK_STATE
    assert result["legs"] == []
    assert result["athena_approval"] is None
