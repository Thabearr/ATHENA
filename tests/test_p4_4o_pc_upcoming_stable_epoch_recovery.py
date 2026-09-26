from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from domain import current_shadow_fixture_identity_compatibility as identity_compatibility
from domain import current_shadow_fixture_identity_v2 as identity_v2
from domain import current_shadow_sportybet_international_provider_family_bridge as bridge
from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime
from domain import current_shadow_sportybet_team_label_compatibility as team_labels
from domain import current_shadow_sportybet_upcoming_reconciliation as wap
from domain import current_shadow_sportybet_paginated_discovery_reconciliation as paginated
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout


UTC = timezone.utc
OBSERVED = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def _event(number: int) -> dict:
    return {
        "eventId": f"sr:match:{99000000000 + number}",
        "homeTeamId": f"sr:competitor:{88000000000 + number * 2}",
        "homeTeamName": f"Synthetic Home {number}",
        "awayTeamId": f"sr:competitor:{88000000001 + number * 2}",
        "awayTeamName": f"Synthetic Away {number}",
        "estimateStartTime": int(datetime(2026, 10, 1, 12, tzinfo=UTC).timestamp() * 1000),
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


def _install_pages(monkeypatch: pytest.MonkeyPatch, pages: list[tuple[int, int, range] | Exception | bytes]) -> list[int]:
    requested: list[int] = []

    def fetch(page_num: int, nonce: int):
        index = len(requested)
        requested.append(page_num)
        if index >= len(pages):
            raise AssertionError("unexpected third epoch or per-page retry")
        item = pages[index]
        if isinstance(item, Exception):
            raise item
        observed_at = datetime.fromtimestamp(nonce / 1000, tz=UTC) + timedelta(seconds=1)
        if type(item) is bytes:
            return item, observed_at
        expected_page, total, numbers = item
        assert page_num == expected_page
        return _raw(total, numbers), observed_at

    monkeypatch.setattr(source, "_fetch_page", fetch)
    return requested


def _stable_101_pages(start: int = 1000) -> list[tuple[int, int, range]]:
    return [
        (1, 101, range(start, start + 100)),
        (2, 101, range(start + 100, start + 101)),
    ]


def _attempt(root: Path, index: int) -> Path:
    return root / runtime.RUNTIME_ATTEMPTS_DIRECTORY / f"attempt-{index:03d}"


def test_stable_first_epoch_is_accepted_without_a_second_epoch(monkeypatch, tmp_path):
    requested = _install_pages(monkeypatch, [(1, 1, range(1, 2))])
    root, manifest = runtime.capture_current_pc_upcoming_discovery(
        repository_root=tmp_path, execute_live_network=True
    )

    assert requested == [1]
    assert manifest.pagination_complete is True
    assert manifest.captured_event_count == manifest.provider_total_num == 1
    assert (root / "manifest.json").is_file()
    assert (root / "pages/page-001.raw.json").read_bytes() == (
        _attempt(root, 1) / "pages/page-001.raw.json"
    ).read_bytes()
    state = runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)
    assert state["attempt_count"] == 1
    assert state["accepted_attempt_index"] == 1
    assert state["failed_attempt_indices"] == []
    assert state["final_state"] == "ACCEPTED_ATTEMPT_1"


def test_exact_drift_then_stable_epoch_restarts_at_page_one_and_isolates_failed_events(monkeypatch, tmp_path):
    pages = [
        (1, 1053, range(1, 101)),
        (2, 1052, range(101, 201)),
        *_stable_101_pages(1000),
    ]
    requested = _install_pages(monkeypatch, pages)
    root, manifest = runtime.capture_current_pc_upcoming_discovery(
        repository_root=tmp_path, execute_live_network=True
    )

    assert requested == [1, 2, 1, 2]
    assert manifest.provider_total_num == manifest.captured_event_count == 101
    assert manifest.pagination_complete is True
    accepted_ids = {event.event_id for event in manifest.events}
    assert accepted_ids == {f"sr:match:{99000000000 + number}" for number in range(1000, 1101)}
    assert "sr:match:99000000001" not in accepted_ids
    assert all((_attempt(root, 1) / f"pages/page-{page:03d}.raw.json").is_file() for page in (1, 2))
    assert all((_attempt(root, 2) / f"pages/page-{page:03d}.raw.json").is_file() for page in (1, 2))
    for attempt_index in (1, 2):
        attempt_root = _attempt(root, attempt_index)
        raw_journal = runtime._read_raw_response_observations(attempt_root)
        assert [row["page_num"] for row in raw_journal] == [1, 2]
        assert all(row["semantic_parse_attempted"] is True and row["semantic_parse_succeeded"] is True for row in raw_journal)
        assert not (attempt_root / runtime.PARSE_FAILURE_FILENAME).exists()
        journal = runtime._read_page_observations(attempt_root)
        assert [row["page_num"] for row in journal] == [1, 2]
        for row in journal:
            raw = (attempt_root / f"pages/page-{row['page_num']:03d}.raw.json").read_bytes()
            replayed = source.parse_page(
                raw,
                page_num=row["page_num"],
                request_nonce_ms=row["request_nonce"],
                observed_at=source._parse_utc_text(row["observed_at"], "observed_at"),
            )
            assert row == runtime._page_observation(replayed, attempt_index)
            assert hashlib.sha256(raw).hexdigest() == row["raw_sha256"]
    for page in manifest.pages:
        assert (root / page.raw_relative_path).read_bytes() == (
            _attempt(root, 2) / page.raw_relative_path
        ).read_bytes()

    projection_seen: list[dict] = []
    monkeypatch.setattr(runtime, "_read_pages", lambda *_args: tuple(page.raw_bytes for page in manifest.pages))
    monkeypatch.setattr(
        identity_compatibility,
        "begin_identity_scope",
        lambda _captures, *, provider_raw_bytes, provider_identity_projection_bytes: projection_seen.extend(
            json.loads(raw.decode("utf-8")) for raw in provider_identity_projection_bytes
        ),
    )
    runtime._identity_scope((), tuple(page.raw_bytes for page in manifest.pages), manifest)
    projected_ids = {event["eventId"] for event in projection_seen[0]["events"]}
    assert projected_ids == accepted_ids
    assert "sr:match:99000000001" not in projected_ids

    state = runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)
    assert state["accepted_attempt_index"] == 2
    assert state["failed_attempt_indices"] == [1]


def test_same_page_count_bucket_does_not_make_drifted_epoch_valid(monkeypatch, tmp_path):
    requested = _install_pages(monkeypatch, [
        (1, 1053, range(1, 101)),
        (2, 1052, range(101, 201)),
    ])
    with pytest.raises(source.PcUpcomingDiscoveryError, match="totalNum changed"):
        source.capture_current_pc_upcoming_discovery(
            repository_root=tmp_path, execute_live_network=True
        )
    assert requested == [1, 2]
    root = tmp_path / source.EVIDENCE_ROOT
    assert (root / "pages/page-001.raw.json").is_file()
    assert (root / "pages/page-002.raw.json").is_file()
    assert not (root / "manifest.json").exists()


def test_two_exact_drift_epochs_fail_closed_without_third_epoch_or_manifest(monkeypatch, tmp_path):
    requested = _install_pages(monkeypatch, [
        (1, 1053, range(1, 101)), (2, 1052, range(101, 201)),
        (1, 1053, range(1001, 1101)), (2, 1052, range(1101, 1201)),
    ])
    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="PC_UPCOMING_RUNTIME_PAGINATION_INCOMPLETE.*both allowed capture epochs"):
        runtime.capture_current_pc_upcoming_discovery(
            repository_root=tmp_path, execute_live_network=True
        )
    assert requested == [1, 2, 1, 2]
    root = tmp_path / source.EVIDENCE_ROOT
    assert not (root / "manifest.json").exists()
    assert not (root / "pages").exists()
    assert all((_attempt(root, attempt) / f"pages/page-{page:03d}.raw.json").is_file()
               for attempt in (1, 2) for page in (1, 2))
    state = runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)
    assert state["accepted_attempt_index"] is None
    assert state["failed_attempt_indices"] == [1, 2]
    assert state["final_state"] == "FAILED_AFTER_EXACT_TOTALNUM_DRIFT"


def test_drift_then_http_failure_stops_without_third_epoch(monkeypatch, tmp_path):
    requested = _install_pages(monkeypatch, [
        (1, 1053, range(1, 101)),
        (2, 1052, range(101, 201)),
        source.PcUpcomingDiscoveryError("provider returned HTTP 503"),
    ])
    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="HTTP 503"):
        runtime.capture_current_pc_upcoming_discovery(
            repository_root=tmp_path, execute_live_network=True
        )
    assert requested == [1, 2, 1]
    state = runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)
    assert state["attempt_count"] == 2
    assert state["accepted_attempt_index"] is None
    assert state["final_state"] == "FAILED_SOURCE_OR_EVIDENCE_ERROR"


@pytest.mark.parametrize("failure", [
    source.PcUpcomingDiscoveryError("provider returned HTTP 503"),
    b"{malformed-json",
    json.dumps({"bizCode": 10000, "data": {"totalNum": 1, "tournaments": [{
        "id": "sr:tournament:242", "name": "Synthetic League",
        "categoryId": "sr:category:26", "categoryName": "Synthetic",
        "events": [{**_event(1), "eventId": "not-a-provider-event-id"}],
    }]}}).encode("utf-8"),
])
def test_non_drift_source_errors_are_translated_without_new_epoch(monkeypatch, tmp_path, failure):
    requested = _install_pages(monkeypatch, [failure])
    with pytest.raises(runtime.SportyBetCurrentEventDiscoveryError, match="PC_UPCOMING_RUNTIME_SOURCE_INCOMPLETE"):
        runtime.capture_current_pc_upcoming_discovery(
            repository_root=tmp_path, execute_live_network=True
        )
    assert requested == [1]
    state = runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)
    assert state["attempt_count"] == 1
    assert state["accepted_attempt_index"] is None


def test_stable_but_incomplete_epoch_does_not_get_a_second_epoch(monkeypatch, tmp_path):
    requested = _install_pages(monkeypatch, [
        (1, 101, range(1, 2)),
        (2, 101, range(2, 3)),
    ])
    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="PC_UPCOMING_RUNTIME_PAGINATION_INCOMPLETE"):
        runtime.capture_current_pc_upcoming_discovery(
            repository_root=tmp_path, execute_live_network=True
        )
    assert requested == [1, 2]
    state = runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)
    assert state["attempt_count"] == 1
    assert state["accepted_attempt_index"] is None
    attempt = _attempt(tmp_path / source.EVIDENCE_ROOT, 1)
    assert (attempt / "manifest.json").is_file()
    assert not (tmp_path / source.EVIDENCE_ROOT / "manifest.json").exists()


def test_maximum_page_bound_is_still_twenty_without_hidden_extension(monkeypatch, tmp_path):
    pages: list[tuple[int, int, range]] = []
    next_event = 5000
    for page_num in range(1, 21):
        pages.append((page_num, 2001, range(next_event, next_event + 100)))
        next_event += 100
    requested = _install_pages(monkeypatch, pages)
    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="PC_UPCOMING_RUNTIME_PAGINATION_INCOMPLETE"):
        runtime.capture_current_pc_upcoming_discovery(
            repository_root=tmp_path, execute_live_network=True
        )
    assert requested == list(range(1, 21))
    assert len(requested) == runtime.MAX_PAGES_PER_EPOCH
    assert runtime.MAX_CAPTURE_EPOCHS * runtime.MAX_PAGES_PER_EPOCH == 40


def test_runtime_stabilization_verifier_rejects_raw_metadata_and_receipt_tampering(monkeypatch, tmp_path):
    _install_pages(monkeypatch, [(1, 1, range(1, 2))])
    root, _manifest = runtime.capture_current_pc_upcoming_discovery(
        repository_root=tmp_path, execute_live_network=True
    )
    attempt = _attempt(root, 1)

    raw_path = attempt / "pages/page-001.raw.json"
    original_raw = raw_path.read_bytes()
    raw_path.write_bytes(original_raw + b" ")
    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="raw replay|metadata differs"):
        runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)
    raw_path.write_bytes(original_raw)

    metadata_path = attempt / "page-observations.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["pages"][0]["totalNum"] += 1
    metadata["canonical_sha256"] = hashlib.sha256(runtime._canonical({k: v for k, v in metadata.items() if k != "canonical_sha256"})).hexdigest()
    metadata_path.write_text(json.dumps(metadata, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="observation ancestry"):
        runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)


def test_runtime_stabilization_receipt_hash_tampering_fails_closed(monkeypatch, tmp_path):
    _install_pages(monkeypatch, [(1, 1, range(1, 2))])
    root, _manifest = runtime.capture_current_pc_upcoming_discovery(
        repository_root=tmp_path, execute_live_network=True
    )
    receipt_path = root / runtime.STABILIZATION_RECEIPT_FILENAME
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["fallback"] = True
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError, match="receipt SHA mismatch"):
        runtime.verify_runtime_capture_stabilization(repository_root=tmp_path)


def test_failed_epoch_does_not_write_identity_state(monkeypatch, tmp_path):
    state_path = tmp_path / "identity-state.json"
    monkeypatch.setenv("ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH", str(state_path))
    _install_pages(monkeypatch, [
        (1, 1053, range(1, 101)),
        (2, 1052, range(101, 201)),
        (1, 101, range(1000, 1100)),
        (2, 101, range(1100, 1101)),
    ])
    _root, _manifest = runtime.capture_current_pc_upcoming_discovery(
        repository_root=tmp_path, execute_live_network=True
    )
    assert not state_path.exists()


def test_runtime_source_and_identity_pins_remain_unchanged(monkeypatch):
    runtime.validate_contract()
    assert source.POLICY_ID == "ATHENA_CURRENT_SHADOW_PC_UPCOMING_GLOBAL_FOOTBALL_SOURCE_V1"
    assert source.calculate_policy_sha256() == source.PINNED_POLICY_SHA256 == "f0e25a0da8fab8ae22a6d8f4b2d6931c5d16297e28365d8c492c2504a05f431b"
    assert team_labels.EXPECTED_POLICY_SHA256 == "0c382ec8b12d802879a51b766daae8f655dd5b371509653e56a13190a85c6c7b"
    assert identity_compatibility.EXPECTED_POLICY_SHA256 == "5b5f804fc0ca21a8f5a15334a32faedc5f9eaa23024adac5c42d467f9fef37fc"
    assert bridge.PINNED_POLICY_SHA256 == "e6e937ff72c83ff2120fcfdfbc3dc3cbf6c8fa10a17122308d60dd0fb0505d2d"
    assert identity_v2.REGISTRY_SHA256 == "d787ace95bcd9e95c8ade0120580f8f42245f2a32bedd1441825cf42a78f67db"
    assert identity_v2.SEED_REGISTRY_SHA256 == "7fe662fc91a80daabf1e774ddd5c8ecdb5215eaf63adb03822b3fb05f872df79"
    assert wap.CURRENT_SHADOW_UPCOMING_COMPATIBILITY_SHA256 == "1ef767b2de32b4d3a51bd9ec5c8244744ce5ba9ddf45c7d61b307327351e81a4"
    assert paginated.EXPECTED_CONTRACT_SHA256 == "17b5e525ea5a253738ab3daed06e0af93ac54eed6e3f06a2278262e6898ad7b6"
    assert fanout.EXPECTED_CONTRACT_SHA256 == "9fa6673848e627e1b59d922dd83b93dd979fa2325eac26b84917cd20f187e022"
