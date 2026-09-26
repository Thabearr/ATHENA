from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import hashlib

import pytest

from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime


UTC = timezone.utc
OBSERVED = datetime(2026, 9, 25, 21, 32, 56, 419000, tzinfo=UTC)


def _provider_event(number: int, *, home: str, away: str, tournament_id: int, tournament_name: str,
                    category_id: int, category_name: str, kickoff: datetime) -> dict:
    return {
        "eventId": f"sr:match:{73220860 + number}",
        "homeTeamId": f"sr:competitor:{21800 + number * 2}",
        "homeTeamName": home,
        "awayTeamId": f"sr:competitor:{21801 + number * 2}",
        "awayTeamName": away,
        "estimateStartTime": int(kickoff.timestamp() * 1000),
        "status": 0,
        "matchStatus": "Not start",
        "bookingStatus": "Booked",
    }


def _manifest(total: int = 2):
    tournaments = [
        {
            "id": "sr:tournament:242",
            "name": "MLS",
            "categoryId": "sr:category:26",
            "categoryName": "USA",
            "events": [_provider_event(
                1, home="Atlanta United FC", away="New York City FC", tournament_id=242,
                tournament_name="MLS", category_id=26, category_name="USA",
                kickoff=datetime(2026, 9, 26, 22, 0, tzinfo=UTC),
            )],
        },
        {
            "id": "sr:tournament:27420",
            "name": "CONCACAF Nations League",
            "categoryId": "sr:category:4",
            "categoryName": "International",
            "events": [_provider_event(
                2, home="Grenada", away="Cuba", tournament_id=27420,
                tournament_name="CONCACAF Nations League", category_id=4,
                category_name="International", kickoff=datetime(2026, 9, 26, 23, 0, tzinfo=UTC),
            )],
        },
    ]
    raw = json.dumps({"bizCode": 10000, "data": {"totalNum": total, "tournaments": tournaments}},
                     separators=(",", ":")).encode()
    page = source.parse_page(
        raw, page_num=1, request_nonce_ms=int(OBSERVED.timestamp() * 1000) - 1,
        observed_at=OBSERVED,
    )
    return source.build_manifest((page,))


def _page(page_num: int, *, total: int, count: int, first_number: int):
    observed = OBSERVED.replace(microsecond=0).replace(second=OBSERVED.second + page_num)
    if observed <= OBSERVED:
        observed = OBSERVED.replace(microsecond=page_num * 1000)
    kickoff = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    events = [
        _provider_event(
            number, home=f"Home {number}", away=f"Away {number}",
            tournament_id=27420, tournament_name="CONCACAF Nations League",
            category_id=4, category_name="International", kickoff=kickoff,
        )
        for number in range(first_number, first_number + count)
    ]
    raw = json.dumps({
        "bizCode": 10000,
        "data": {"totalNum": total, "tournaments": [{
            "id": "sr:tournament:27420",
            "name": "CONCACAF Nations League",
            "categoryId": "sr:category:4",
            "categoryName": "International",
            "events": events,
        }]},
    }, separators=(",", ":")).encode()
    page = source.parse_page(
        raw,
        page_num=page_num,
        request_nonce_ms=int(observed.timestamp() * 1000) - 1,
        observed_at=observed,
    )
    return raw, page


def test_runtime_wrapper_policy_and_ancestry_are_pinned() -> None:
    identities = runtime.validate_contract()
    assert runtime.calculate_policy_sha256() == runtime.PINNED_POLICY_SHA256
    assert identities["source_policy_id"] == "ATHENA_CURRENT_SHADOW_PC_UPCOMING_GLOBAL_FOOTBALL_SOURCE_V1"
    assert identities["source_policy_sha256"] == "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075"
    assert identities["bridge_policy_id"] == "ATHENA_CURRENT_SHADOW_INTERNATIONAL_PROVIDER_FAMILY_BRIDGE_V1"
    assert identities["bridge_policy_sha256"] == "7db676111a9be06f63fd207815837d53699d6bf1a98364fc2163046cd1c0a4bb"
    assert identities["v2_semantic_registry_sha256"] == "fc64fb0c2df3cee4f425158c48cfaada6757ba01e1759dd5b976ca899f85421e"
    assert identities["identity_compatibility_policy_sha256"] == "dbef6539dd7c5d1c1589debe8daca9378ea2e0c0bb32acf3315a0d1a005c2b58"
    assert identities["pagination_complete_required"] is True


def test_complete_manifest_may_contain_club_and_international_fixtures() -> None:
    manifest = _manifest()
    assert manifest.pagination_complete is True
    runtime._require_complete(manifest)
    events = runtime._provider_events(manifest)
    assert [(row.home_team_name, row.away_team_name) for row in events] == [
        ("Atlanta United FC", "New York City FC"), ("Grenada", "Cuba")
    ]
    assert events[1].competition_name == "CONCACAF Nations League"
    assert events[1].source_raw_sha256 == manifest.pages[0].raw_sha256
    assert events[1].source_page_num == 1
    assert events[1].kickoff_utc == datetime(2026, 9, 26, 23, 0, tzinfo=UTC)
    assert events[1].home_team_id == "sr:competitor:21804"
    assert events[1].away_team_id == "sr:competitor:21805"
    assert events[1].category_id == "sr:category:4"
    assert events[1].tournament_id == "sr:tournament:27420"


def test_incomplete_pagination_fails_at_source_boundary() -> None:
    manifest = _manifest(total=101)
    assert manifest.pagination_complete is False
    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="PC_UPCOMING_RUNTIME_PAGINATION_INCOMPLETE"):
        runtime._require_complete(manifest)


def test_provider_total_beyond_maximum_runtime_pages_fails_closed() -> None:
    manifest = _manifest(total=2001)
    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="PC_UPCOMING_RUNTIME_PAGINATION_INCOMPLETE"):
        runtime._require_complete(manifest)


def test_viability_summary_reports_complete_global_page_scope() -> None:
    manifest = _manifest()
    summary = runtime.prospective_discovery_assessment(
        manifest, evaluation_time=datetime(2026, 9, 25, 22, 0, tzinfo=UTC)
    )
    assert summary["provider_event_count"] == 2
    assert summary["provider_total_num"] == 2
    assert summary["captured_page_count"] == 1
    assert summary["provider_discovery_pagination_complete"] is True
    assert summary["provider_discovery_source_method"] == "PUBLIC_ANONYMOUS_FACTS_CENTER_PC_UPCOMING_EVENTS_GET"
    assert summary["provider_future_lead_eligible_count"] == 2


def test_complete_two_page_manifest_replays_each_exact_raw_page(tmp_path: Path) -> None:
    raw1, page1 = _page(1, total=101, count=100, first_number=1)
    raw2, page2 = _page(2, total=101, count=1, first_number=101)
    manifest = source.build_manifest((page1, page2))
    assert manifest.pagination_complete is True
    assert manifest.captured_event_count == manifest.provider_total_num == 101
    assert tuple(page.page_num for page in manifest.pages) == (1, 2)

    root = tmp_path / source.EVIDENCE_ROOT
    (root / "pages").mkdir(parents=True)
    (root / page1.raw_relative_path).write_bytes(raw1)
    (root / page2.raw_relative_path).write_bytes(raw2)
    (root / "manifest.json").write_bytes(source._canonical(manifest.to_dict(), newline=True))

    replayed = runtime.verify_current_pc_upcoming_discovery(repository_root=tmp_path)
    assert replayed.to_dict() == manifest.to_dict()
    assert hashlib.sha256((root / page1.raw_relative_path).read_bytes()).hexdigest() == page1.raw_sha256
    assert hashlib.sha256((root / page2.raw_relative_path).read_bytes()).hexdigest() == page2.raw_sha256


def test_projection_is_supplied_after_raw_pages_and_binds_page_hashes(monkeypatch) -> None:
    manifest = _manifest()
    raw_page = b"exact raw pcUpcoming page bytes"
    monkeypatch.setattr(runtime, "_read_pages", lambda *_args: (raw_page,))
    observed = {}

    def observe(captures, *, provider_raw_bytes, provider_identity_projection_bytes):
        observed["captures"] = captures
        observed["raw"] = tuple(provider_raw_bytes)
        observed["projection"] = tuple(provider_identity_projection_bytes)

    monkeypatch.setattr(runtime.identity_compatibility, "begin_identity_scope", observe)
    runtime._identity_scope((), (raw_page,), manifest)
    projection = json.loads(observed["projection"][0].decode("utf-8"))
    assert observed["raw"] == (raw_page,)
    assert observed["projection"] == (source.provider_identity_projection_bytes(manifest),)
    assert projection["is_provider_response"] is False
    assert all(row["source_ancestry"]["source_raw_sha256"] == manifest.pages[0].raw_sha256
               for row in projection["events"])
    assert all(row["source_ancestry"]["source_page_num"] == 1 for row in projection["events"])


def test_direct_event_native_ancestry_must_match_global_page(tmp_path: Path) -> None:
    manifest = _manifest()
    event = manifest.events[1]
    event_id = event.event_id
    detail_dir = tmp_path / "direct" / event_id.replace(":", "-")
    detail_dir.mkdir(parents=True)
    detail_path = detail_dir / runtime.live.RAW_FILENAME
    detail = {
        "bizCode": 10000,
        "data": [{
            "eventId": event_id,
            "homeTeamName": event.home_team_name,
            "awayTeamName": event.away_team_name,
            "estimateStartTime": event.estimate_start_time_ms,
            "bookingStatus": "Booked",
            "matchStatus": "Not start",
            "sport": {"category": {
                "id": event.category_id,
                "name": event.category_name,
                "tournament": {"id": event.tournament_id, "name": event.tournament_name},
            }},
            "markets": [],
        }],
    }
    detail_path.write_text(json.dumps(detail, separators=(",", ":")), encoding="utf-8")
    runtime._validate_direct_native_ancestry(
        tmp_path, manifest, {event_id: detail_dir}
    )

    detail["data"][0]["sport"]["category"]["tournament"]["id"] = "sr:tournament:23755"
    detail_path.write_text(json.dumps(detail, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="conflicts with pcUpcoming ancestry"):
        runtime._validate_direct_native_ancestry(tmp_path, manifest, {event_id: detail_dir})
