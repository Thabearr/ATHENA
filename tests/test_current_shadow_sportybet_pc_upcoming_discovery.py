from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

import pytest

from domain import current_shadow_sportybet_pc_upcoming_discovery as pc


OBSERVED = datetime(2026, 9, 25, 21, 32, 56, 419000, tzinfo=timezone.utc)
OBSERVED_MS = int(OBSERVED.timestamp() * 1000)


def _event(index: int, *, event_id: str | None = None, home: str | None = None) -> dict:
    kickoff_ms = int(datetime(2026, 9, 26, 0, 0, tzinfo=timezone.utc).timestamp() * 1000) + index
    return {
        "eventId": event_id or f"sr:match:{5000000 + index}",
        "homeTeamId": f"sr:competitor:{6000000 + index * 2}",
        "homeTeamName": home or f"Home {index}",
        "awayTeamId": f"sr:competitor:{6000001 + index * 2}",
        "awayTeamName": f"Away {index}",
        "estimateStartTime": kickoff_ms,
        "status": 0,
        "matchStatus": "Not start",
        "bookingStatus": "Booked",
    }


def _tournament(tournament_id: int, name: str, category_id: int, category: str, rows: list[dict]) -> dict:
    return {
        "id": f"sr:tournament:{tournament_id}",
        "name": name,
        "categoryId": f"sr:category:{category_id}",
        "categoryName": category,
        "events": rows,
    }


def _five_family_response() -> bytes:
    tournaments = [
        _tournament(242, "MLS", 26, "USA", [_event(1)]),
        _tournament(27420, "CONCACAF Nations League", 4, "International", [_event(2)]),
        _tournament(23755, "UEFA Nations League", 4, "International", [_event(3)]),
        _tournament(1848, "Africa Cup of Nations Qualification", 4, "International", [_event(4)]),
        _tournament(851, "Int. Friendly Games", 4, "International", [_event(5)]),
    ]
    return json.dumps({"bizCode": 10000, "message": "OK", "data": {"totalNum": 5, "tournaments": tournaments}}, separators=(",", ":")).encode()


def _response(total: int, events: list[dict], *, tournament_id: int = 242, category_id: int = 26) -> bytes:
    tournament = _tournament(tournament_id, "Synthetic League", category_id, "Synthetic", events)
    return json.dumps({"bizCode": 10000, "data": {"totalNum": total, "tournaments": [tournament]}}, separators=(",", ":")).encode()


def _page(page_num: int, raw: bytes, *, total: int | None = None) -> pc.PcUpcomingPageEvidence:
    observed = OBSERVED.replace(microsecond=419000 + page_num)
    nonce = int(observed.timestamp() * 1000) - 500
    return pc.parse_page(raw, page_num=page_num, request_nonce_ms=nonce, observed_at=observed)


def test_request_path_and_fixed_query_are_exact() -> None:
    target = pc.request_target(2, OBSERVED_MS - 1)
    assert target.startswith("/api/ng/factsCenter/pcUpcomingEvents?")
    assert target == (
        "/api/ng/factsCenter/pcUpcomingEvents?sportId=sr%3Asport%3A1&marketId=1&pageSize=100"
        f"&pageNum=2&todayGames=false&timeline=48&_t={OBSERVED_MS - 1}"
    )
    assert {pair.split("=", 1)[0] for pair in target.split("?", 1)[1].split("&")} == {
        "sportId", "marketId", "pageSize", "pageNum", "todayGames", "timeline", "_t"
    }
    with pytest.raises(pc.PcUpcomingDiscoveryError):
        pc.request_target(True, OBSERVED_MS)
    with pytest.raises(pc.PcUpcomingDiscoveryError):
        pc.request_target(1, True)
    with pytest.raises(pc.PcUpcomingDiscoveryError):
        pc.request_target(0, OBSERVED_MS)
    with pytest.raises(pc.PcUpcomingDiscoveryError):
        pc.request_target(21, OBSERVED_MS)


def test_parser_preserves_mixed_provider_families_and_wrapper_ancestry() -> None:
    raw = _five_family_response()
    page = _page(1, raw)
    assert page.total_num == 5
    assert page.tournament_count == 5
    assert page.event_count == 5
    by_id = {event.tournament_id: event for event in page.events}
    assert set(by_id) == {
        "sr:tournament:242", "sr:tournament:27420", "sr:tournament:23755",
        "sr:tournament:1848", "sr:tournament:851",
    }
    assert by_id["sr:tournament:242"].category_id == "sr:category:26"
    assert by_id["sr:tournament:27420"].category_id == "sr:category:4"
    assert by_id["sr:tournament:27420"].category_name == "International"
    assert by_id["sr:tournament:27420"].home_team_id == "sr:competitor:6000004"
    assert by_id["sr:tournament:27420"].event_id == "sr:match:5000002"
    assert by_id["sr:tournament:27420"].prematch_bookable_observed is True
    assert by_id["sr:tournament:27420"].source_raw_sha256 == hashlib.sha256(raw).hexdigest()


def test_nested_provider_ancestry_must_match_wrapper() -> None:
    event = _event(1)
    event["sport"] = {
        "id": "sr:sport:1",
        "category": {"id": "sr:category:26", "name": "Synthetic", "tournament": {"id": "sr:tournament:242", "name": "Synthetic League"}},
    }
    raw = _response(1, [event])
    parsed = _page(1, raw).events[0]
    assert parsed.tournament_name == "Synthetic League"
    assert parsed.source_sport_id == "sr:sport:1"
    event["sport"]["category"]["tournament"]["id"] = "sr:tournament:999"
    with pytest.raises(pc.PcUpcomingDiscoveryError):
        _page(1, _response(1, [event]))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(bizCode=True),
        lambda value: value["data"].update(totalNum=True),
        lambda value: value["data"].update(tournaments={}),
    ],
)
def test_parser_rejects_wrong_success_or_malformed_page_shape(mutate) -> None:
    value = json.loads(_response(1, [_event(1)]))
    mutate(value)
    with pytest.raises(pc.PcUpcomingDiscoveryError):
        _page(1, json.dumps(value).encode())


def test_parser_rejects_malformed_provider_ids_and_same_competitor() -> None:
    event = _event(1)
    event["eventId"] = "38279"
    with pytest.raises(pc.PcUpcomingDiscoveryError):
        _page(1, _response(1, [event]))
    event = _event(1)
    event["awayTeamId"] = event["homeTeamId"]
    with pytest.raises(pc.PcUpcomingDiscoveryError):
        _page(1, _response(1, [event]))


def test_missing_match_status_is_preserved_as_unknown_and_not_bookable() -> None:
    event = _event(1)
    event.pop("matchStatus")
    parsed = _page(1, _response(1, [event])).events[0]
    assert parsed.match_status is None
    assert parsed.event_status == 0
    assert parsed.booking_status == "Booked"
    assert parsed.prematch_bookable_observed is False


def test_three_page_sequence_and_completion_math_are_deterministic() -> None:
    pages = []
    for page_num, start, count in ((1, 0, 100), (2, 100, 100), (3, 200, 50)):
        raw = _response(250, [_event(index) for index in range(start, start + count)])
        pages.append(_page(page_num, raw))
    manifest = pc.build_manifest(tuple(pages))
    assert [page.page_num for page in manifest.pages] == [1, 2, 3]
    assert [page.raw_sha256 for page in manifest.pages] == [page.raw_sha256 for page in pages]
    assert manifest.provider_total_num == 250
    assert manifest.captured_event_count == 250
    assert len(manifest.events) == 250
    assert manifest.pagination_complete is True


def test_total_drift_and_page_gap_fail_closed() -> None:
    first = _page(1, _response(150, [_event(1)]))
    drift = _page(2, _response(151, [_event(2)]))
    with pytest.raises(pc.PcUpcomingDiscoveryError, match="totalNum"):
        pc.build_manifest((first, drift))
    third = _page(3, _response(250, [_event(3)]))
    with pytest.raises(pc.PcUpcomingDiscoveryError, match="contiguous"):
        pc.build_manifest((first, third))


def test_conflicting_duplicate_event_id_fails_closed() -> None:
    first = _page(1, _response(101, [_event(1)]))
    second = _page(2, _response(101, [_event(2, event_id="sr:match:5000001", home="Different Home")]))
    with pytest.raises(pc.PcUpcomingDiscoveryError, match="conflicting duplicate"):
        pc.build_manifest((first, second))


def test_exact_duplicate_event_is_deduped_but_never_proves_completeness() -> None:
    event = _event(1)
    first = _page(1, _response(101, [event]))
    second = _page(2, _response(101, [event]))
    manifest = pc.build_manifest((first, second))
    assert manifest.captured_event_count == 1
    assert len(manifest.events) == 1
    assert manifest.pagination_complete is False
    assert manifest.pagination_completion_basis == "INCOMPLETE_CAPTURE_DOES_NOT_PROVE_PROVIDER_ABSENCE"


def test_incomplete_pagination_has_no_absence_authority_and_over_max_cannot_complete() -> None:
    first = _page(1, _response(201, [_event(1)]))
    second = _page(2, _response(201, [_event(2)]))
    partial = pc.build_manifest((first, second))
    assert partial.pagination_complete is False
    assert partial.authority["provider_discovery_evidence"] is True
    assert partial.authority["current_shadow_runtime_discovery"] is False
    assert partial.authority["p3_runtime_discovery"] is False
    assert partial.authority["fixture_reconciliation"] is False
    assert partial.authority["pricing"] is False
    assert partial.authority["selection"] is False
    assert partial.authority["login"] is partial.authority["cookies"] is False
    assert partial.authority["wallet"] is partial.authority["staking"] is False
    assert partial.authority["bet"] is partial.authority["wager_placed"] is False
    with pytest.raises(pc.PcUpcomingDiscoveryError):
        pc.request_target(pc.MAX_PAGES + 1, OBSERVED_MS)


def test_projection_is_deterministic_and_binds_raw_page_ancestry() -> None:
    raw = _response(1, [_event(1)])
    page = _page(1, raw)
    one = pc.provider_identity_projection_bytes(page)
    two = pc.provider_identity_projection_bytes(page)
    projection = json.loads(one)
    row = projection["events"][0]
    assert one == two
    assert projection["is_provider_response"] is False
    assert row["sport"]["category"]["tournament"]["id"] == "sr:tournament:242"
    assert "id" not in row["sport"]
    assert row["source_ancestry"] == {
        "source_raw_sha256": hashlib.sha256(raw).hexdigest(),
        "source_page_num": 1,
        "source_observed_at": "2026-09-25T21:32:56.419001Z",
    }


def test_manifest_verification_replays_raw_bytes_not_event_projection(tmp_path) -> None:
    raw = _response(1, [_event(1)])
    page = _page(1, raw)
    manifest = pc.build_manifest((page,))
    root = tmp_path / pc.EVIDENCE_ROOT
    (root / "pages").mkdir(parents=True)
    (root / page.raw_relative_path).write_bytes(raw)
    (root / "manifest.json").write_bytes(
        json.dumps(manifest.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    verified = pc.verify_current_pc_upcoming_discovery(repository_root=tmp_path)
    assert verified.canonical_sha256 == manifest.canonical_sha256
    tampered = manifest.to_dict()
    tampered["events"][0]["home_team_name"] = "Projection lie"
    with pytest.raises(pc.PcUpcomingDiscoveryError):
        pc.verify_current_pc_upcoming_discovery(repository_root=tmp_path, manifest=tampered)


def test_capture_requires_explicit_network_boolean_without_calling_transport(monkeypatch, tmp_path) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("offline test attempted provider acquisition")

    monkeypatch.setattr(pc, "_fetch_page", forbidden)
    with pytest.raises(pc.PcUpcomingDiscoveryError, match="explicit"):
        pc.capture_current_pc_upcoming_discovery(repository_root=tmp_path, execute_live_network=False)


def test_policy_hash_is_pinned() -> None:
    assert pc.PINNED_POLICY_SHA256
    assert pc.calculate_policy_sha256() == pc.PINNED_POLICY_SHA256
