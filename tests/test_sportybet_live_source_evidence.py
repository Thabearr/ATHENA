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
    SportyBetLiteNetworkError,
    fetch_sportybet_lite,
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
) -> str:
    parts = [
        f"eventId={EVENT_ID.replace(':', '%3A')}",
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
    anchors = []
    for href in links:
        attrs = ""
        if "marketId=18" in href and "outcomeId=13" in href and "total%3D3.5" in href:
            attrs = ' data-status="suspended" data-market-name="Over/Under"'
        anchors.append(f'<a href="{href}"{attrs}>{href.split("odds=")[1].split("&")[0]}</a>')
    return ("<html><body>" + "".join(anchors) + "</body></html>").encode("utf-8")


def _response(body: bytes | None = None, *, observed_at: dt.datetime = OBSERVED):
    body = body or _html()
    return CapturedSportyBetLiteResponse(
        status=200,
        content_type="text/html; charset=utf-8",
        content_length=len(body),
        body=body,
        observed_at=observed_at,
        network_acquisition_performed=True,
    )


def _manifest(body: bytes | None = None, *, observed_at: dt.datetime = OBSERVED):
    return build_capture_manifest(
        _response(body, observed_at=observed_at),
        request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
        event_id=EVENT_ID,
        sport_id=FOOTBALL_SPORT_ID,
        market_groups_name=DEFAULT_MARKET_GROUP,
    )


def test_reviewed_request_target_is_exact_public_read_only_lite_surface():
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


def test_valid_raw_capture_manifest_is_canonical_and_preserves_unknown_quote_time():
    manifest = _manifest()
    raw = canonical_manifest_bytes(manifest)
    assert raw.endswith(b"\n")
    assert manifest.provider_quote_at is None
    assert manifest.provider_snapshot_id is None
    assert b'"provider_quote_at":null' in raw
    assert b'"provider_snapshot_id":null' in raw
    assert all(value is False for value in manifest.safety.values())


def test_non_200_and_content_type_contradiction_fail_closed():
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


def test_content_length_mismatch_and_empty_body_fail_closed():
    body = _html()
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
    path1, manifest1 = store_capture(
        response,
        request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
        repository_root=repo,
        event_id=EVENT_ID,
        sport_id=FOOTBALL_SPORT_ID,
        market_groups_name=DEFAULT_MARKET_GROUP,
    )
    path2, manifest2 = store_capture(
        response,
        request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
        repository_root=repo,
        event_id=EVENT_ID,
        sport_id=FOOTBALL_SPORT_ID,
        market_groups_name=DEFAULT_MARKET_GROUP,
    )
    assert path1 == path2
    assert manifest1.to_dict() == manifest2.to_dict()
    verified = verify_capture_directory(
        path1,
        allowed_root=repo / ALLOWED_OUTPUT_RELATIVE,
    )
    assert verified.raw_sha256 == sha256_bytes(response.body)


def test_same_observation_identity_different_bytes_fails_closed(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    first = _response(_html())
    path, manifest = store_capture(
        first,
        request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
        repository_root=repo,
        event_id=EVENT_ID,
        sport_id=FOOTBALL_SPORT_ID,
        market_groups_name=DEFAULT_MARKET_GROUP,
    )
    changed_body = _html([_href(market_id="1", outcome_id="1", odds="1.41")])
    second = _response(changed_body)
    second_manifest = build_capture_manifest(
        second,
        request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
        event_id=EVENT_ID,
        sport_id=FOOTBALL_SPORT_ID,
        market_groups_name=DEFAULT_MARKET_GROUP,
    )
    assert capture_identifier(second_manifest) == capture_identifier(manifest)
    with pytest.raises(SportyBetLiteCaptureError):
        store_capture(
            second,
            request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
            repository_root=repo,
            event_id=EVENT_ID,
            sport_id=FOOTBALL_SPORT_ID,
            market_groups_name=DEFAULT_MARKET_GROUP,
        )
    assert path.exists()


def test_output_path_traversal_and_symlink_are_rejected(tmp_path: Path):
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
    (cache / "athena-research").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(SportyBetLiteCaptureError):
        store_capture(
            _response(),
            request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
            repository_root=repo,
            event_id=EVENT_ID,
            sport_id=FOOTBALL_SPORT_ID,
            market_groups_name=DEFAULT_MARKET_GROUP,
        )


def test_provider_native_selection_inventory_preserves_ids_lines_and_suspension():
    selections = extract_native_selections(_html())
    assert len(selections) == 7
    assert {item.event_id for item in selections} == {EVENT_ID}
    total_markets = {
        item.market_identity for item in selections if item.market_id == "18"
    }
    assert total_markets == {("18", "total=2.5"), ("18", "total=3.5")}
    suspended = [
        item for item in selections
        if item.market_id == "18" and item.specifier == "total=3.5" and item.outcome_id == "13"
    ]
    assert suspended[0].availability is NativeAvailability.SUSPENDED
    assert suspended[0].market_name == "Over/Under"


def test_same_market_id_different_specifier_is_not_collapsed():
    selections = extract_native_selections(_html())
    over_rows = [
        item for item in selections if item.market_id == "18" and item.outcome_id == "12"
    ]
    assert [item.specifier for item in over_rows] == ["total=2.5", "total=3.5"]
    assert len({item.selection_identity for item in over_rows}) == 2


def test_event_only_navigation_link_is_not_misclassified_as_selection():
    event_only = (
        "/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A72348790"
        "&marketGroupsName=Main&sportId=sr%3Asport%3A1"
    )
    selection = _href(market_id="1", outcome_id="1", odds="1.40")
    raw = (
        f'<html><body><a href="{event_only}">Fixture</a>'
        f'<a href="{selection}">1.40</a></body></html>'
    ).encode()
    assert len(extract_native_selections(raw)) == 1


def test_missing_market_or_outcome_id_fails_closed():
    missing_market = _href(market_id="1", outcome_id="1", odds="1.40").replace("marketId=1&", "")
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([missing_market]))
    missing_outcome = _href(market_id="1", outcome_id="1", odds="1.40").replace("outcomeId=1&", "")
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([missing_outcome]))


def test_invalid_event_id_and_duplicate_selection_identity_fail_closed():
    invalid = _href(market_id="1", outcome_id="1", odds="1.40").replace(
        "sr%3Amatch%3A72348790", "not-a-provider-event"
    )
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([invalid]))
    duplicate = _href(market_id="1", outcome_id="1", odds="1.40")
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([duplicate, duplicate]))


def test_duplicate_selection_identity_with_changed_odds_also_fails_closed():
    one = _href(market_id="1", outcome_id="1", odds="1.40")
    two = _href(market_id="1", outcome_id="1", odds="1.41")
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([one, two]))


def test_decimal_odds_validation_rejects_non_decimal_and_even_money_floor():
    bad = _href(market_id="1", outcome_id="1", odds="NaN")
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([bad]))
    floor = _href(market_id="1", outcome_id="1", odds="1.00")
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([floor]))


def test_no_fuzzy_canonical_market_mapping_occurs():
    href = _href(market_id="18", outcome_id="12", odds="1.86", specifier="total=2.5")
    raw = (
        '<html><body><a data-market-name="Over 2.5" '
        f'href="{href}">Over</a></body></html>'
    ).encode()
    item = extract_native_selections(raw)[0]
    assert item.market_name == "Over 2.5"
    assert "canonical" not in item.to_dict()
    assert item.market_id == "18"
    assert item.specifier == "total=2.5"


def test_observed_at_never_becomes_provider_quote_timestamp_or_snapshot():
    manifest = _manifest()
    inventory = build_inventory(
        manifest,
        _html(),
        source_manifest_sha256=sha256_bytes(canonical_manifest_bytes(manifest)),
    )
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


def test_source_anchor_order_does_not_change_provider_native_selection_order():
    links = [
        _href(market_id="1", outcome_id="3", odds="8.23"),
        _href(market_id="18", outcome_id="12", odds="1.86", specifier="total=2.5"),
        _href(market_id="1", outcome_id="1", odds="1.40"),
    ]
    forward = extract_native_selections(_html(links))
    reverse = extract_native_selections(_html(list(reversed(links))))
    assert [item.selection_identity for item in forward] == [
        item.selection_identity for item in reverse
    ]


def test_canonical_inventory_bytes_are_deterministic_for_same_evidence():
    manifest = _manifest()
    manifest_sha = sha256_bytes(canonical_manifest_bytes(manifest))
    first = build_inventory(manifest, _html(), source_manifest_sha256=manifest_sha)
    second = build_inventory(manifest, _html(), source_manifest_sha256=manifest_sha)
    assert canonical_inventory_bytes(first) == canonical_inventory_bytes(second)
    assert all(value is False for value in first.safety.values())


def test_invalid_utf8_html_fails_closed():
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(b"<html>\xff</html>")


def test_foreign_or_non_https_selection_href_fails_closed():
    foreign = (
        "https://evil.example/ng/lite?eventId=sr%3Amatch%3A72348790"
        "&marketId=1&outcomeId=1&odds=1.40"
    )
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([foreign]))
    http = (
        "http://www.sportybet.com/ng/lite?eventId=sr%3Amatch%3A72348790"
        "&marketId=1&outcomeId=1&odds=1.40"
    )
    with pytest.raises(SportyBetProviderInventoryError):
        extract_native_selections(_html([http]))


def test_network_fetch_is_one_get_without_cookie_or_auth_headers():
    body = _html()

    class FakeResponse:
        status = 200

        def __init__(self):
            self._sent = False

        def getheader(self, name):
            return {
                "Content-Type": "text/html; charset=utf-8",
                "Content-Length": str(len(body)),
            }.get(name)

        def read(self, amount):
            if self._sent:
                return b""
            self._sent = True
            return body

    class FakeConnection:
        instance = None

        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.method = None
            self.target = None
            self.headers = []
            FakeConnection.instance = self

        def putrequest(self, method, target, skip_accept_encoding):
            self.method = method
            self.target = target
            assert skip_accept_encoding is True

        def putheader(self, name, value):
            self.headers.append((name, value))

        def endheaders(self):
            pass

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    response = fetch_sportybet_lite(
        request_kind=SportyBetLiteRequestKind.EVENT_DETAIL,
        event_id=EVENT_ID,
        sport_id=FOOTBALL_SPORT_ID,
        market_groups_name=DEFAULT_MARKET_GROUP,
        connection_factory=FakeConnection,
        clock=lambda: OBSERVED,
    )
    conn = FakeConnection.instance
    assert conn.method == "GET"
    assert conn.target.startswith("/ng/lite/preMatch/detail?")
    names = {name.lower() for name, _ in conn.headers}
    assert "cookie" not in names
    assert "authorization" not in names
    assert response.network_acquisition_performed is True


def test_network_fetch_non_200_fails_without_using_body():
    class FakeResponse:
        status = 403

        def getheader(self, name):
            return None

        def read(self, amount):
            raise AssertionError("body must not be used after non-200")

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            pass
        def putrequest(self, *args, **kwargs):
            pass
        def putheader(self, *args, **kwargs):
            pass
        def endheaders(self):
            pass
        def getresponse(self):
            return FakeResponse()
        def close(self):
            pass

    with pytest.raises(SportyBetLiteNetworkError):
        fetch_sportybet_lite(
            request_kind=SportyBetLiteRequestKind.INDEX,
            connection_factory=FakeConnection,
            clock=lambda: OBSERVED,
        )


def test_product_facing_sportybet_resolver_remains_fail_closed():
    result = BettingService().resolve_sportybet("ABC123")
    assert result["success"] is False
    assert result["state"] == BOOKMAKER_RESOLUTION_BLOCK_STATE
    assert result["legs"] == []
    assert result["athena_approval"] is None
