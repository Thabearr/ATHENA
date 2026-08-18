from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from scripts import build_sportybet_user_controlled_native_inventory as command


OBSERVED = dt.datetime(2026, 8, 18, 12, 0, tzinfo=dt.timezone.utc)
IMPORTED = dt.datetime(2026, 8, 18, 12, 1, tzinfo=dt.timezone.utc)
DETAIL_URL = (
    "https://www.sportybet.com/ng/lite/preMatch/detail?"
    "eventId=sr%3Amatch%3A123&marketGroupsName=Main&sportId=sr%3Asport%3A1"
)
RAW = b'''<!doctype html><html><body>
<a data-active="true" data-market-name="Total Goals" data-outcome-name="Over 2.5" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=18&outcomeId=12&odds=1.85&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main&specifier=total%3D2.5">Over 2.5</a>
<a data-status="suspended" data-market-name="Total Goals" data-outcome-name="Over 3.5" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=18&outcomeId=13&odds=2.40&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main&specifier=total%3D3.5">Over 3.5</a>
<a data-market-name="1X2" data-outcome-name="Home" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=1&odds=2.05&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Home</a>
</body></html>'''


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def _evidence(
    repo: Path,
    *,
    raw: bytes = RAW,
    source_url: str = DETAIL_URL,
) -> Path:
    directory, _ = manual.store_user_controlled_evidence(
        raw,
        source_url=source_url,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    return directory


def test_build_inventory_preserves_native_odds_lines_and_manual_time_authority(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    evidence = _evidence(repo)
    inventory = native.build_inventory_from_evidence(
        evidence,
        allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
    )
    assert len(inventory.events) == 1
    assert len(inventory.selections) == 3
    assert [item.market_id for item in inventory.selections] == ["1", "18", "18"]
    total_rows = [item for item in inventory.selections if item.market_id == "18"]
    assert [item.specifier for item in total_rows] == ["total=2.5", "total=3.5"]
    assert [item.odds_raw for item in total_rows] == ["1.85", "2.40"]
    assert [item.odds_decimal for item in total_rows] == ["1.85", "2.4"]
    assert total_rows[0].availability.value == "AVAILABLE"
    assert total_rows[1].availability.value == "SUSPENDED"
    assert inventory.observation_authority == "USER_ATTESTED_NOT_PROVIDER_TIMESTAMP"
    assert inventory.observed_at_user_attested == "2026-08-18T12:00:00.000000Z"
    assert inventory.imported_at_utc == "2026-08-18T12:01:00.000000Z"
    assert inventory.athena_network_acquisition_performed is False
    assert inventory.provider_quote_at is None
    assert inventory.provider_snapshot_id is None
    assert all(value is False for value in inventory.safety.values())


def test_same_market_id_with_distinct_specifiers_is_not_collapsed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    evidence = _evidence(repo)
    inventory = native.build_inventory_from_evidence(
        evidence,
        allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
    )
    identities = {
        item.selection_identity for item in inventory.selections if item.market_id == "18"
    }
    assert identities == {
        ("sr:match:123", "18", "total=2.5", "12"),
        ("sr:match:123", "18", "total=3.5", "13"),
    }


def test_event_detail_html_must_match_attested_source_event_id(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    bad = RAW.replace(b"sr%3Amatch%3A123", b"sr%3Amatch%3A999")
    evidence = _evidence(repo, raw=bad)
    with pytest.raises(native.SportyBetUserInventoryError, match="source eventId"):
        native.build_inventory_from_evidence(
            evidence,
            allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
        )


def test_event_detail_html_must_match_attested_source_sport_id(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    bad = RAW.replace(b"sr%3Asport%3A1", b"sr%3Asport%3A2")
    evidence = _evidence(repo, raw=bad)
    with pytest.raises(native.SportyBetUserInventoryError, match="source sportId"):
        native.build_inventory_from_evidence(
            evidence,
            allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
        )


def test_event_detail_html_must_not_switch_market_group(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    bad = RAW.replace(b"marketGroupsName=Main", b"marketGroupsName=Other")
    evidence = _evidence(repo, raw=bad)
    with pytest.raises(native.SportyBetUserInventoryError, match="market group"):
        native.build_inventory_from_evidence(
            evidence,
            allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
        )


def test_index_evidence_can_inventory_multiple_provider_events(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    index_url = "https://www.sportybet.com/ng/lite"
    raw = RAW + RAW.replace(
        b"sr%3Amatch%3A123",
        b"sr%3Amatch%3A456",
    ).replace(b"outcomeId=1", b"outcomeId=9")
    evidence = _evidence(repo, raw=raw, source_url=index_url)
    inventory = native.build_inventory_from_evidence(
        evidence,
        allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
    )
    assert [item.event_id for item in inventory.events] == [
        "sr:match:123",
        "sr:match:456",
    ]


def test_tampered_source_evidence_is_rejected_before_inventory(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    evidence = _evidence(repo)
    (evidence / manual.RAW_FILENAME).write_bytes(RAW + b" ")
    with pytest.raises(native.SportyBetUserInventoryError):
        native.build_inventory_from_evidence(
            evidence,
            allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
        )


def test_store_verify_and_exact_replay_are_deterministic(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    evidence = _evidence(repo)
    first_dir, first = native.store_inventory_from_evidence(
        evidence,
        repository_root=repo,
    )
    second_dir, second = native.store_inventory_from_evidence(
        evidence,
        repository_root=repo,
    )
    assert first_dir == second_dir
    assert first.to_dict() == second.to_dict()
    assert first_dir.parent == repo / native.ALLOWED_OUTPUT_RELATIVE
    assert first_dir.name == first.source_evidence_id
    verified = native.verify_inventory_directory(
        first_dir,
        evidence_directory=evidence,
        repository_root=repo,
    )
    assert verified.to_dict() == first.to_dict()
    stored = (first_dir / native.INVENTORY_FILENAME).read_bytes()
    assert stored == native.canonical_inventory_bytes(first)
    assert stored.endswith(b"\n")


def test_tampered_derived_inventory_is_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    evidence = _evidence(repo)
    directory, _ = native.store_inventory_from_evidence(
        evidence,
        repository_root=repo,
    )
    payload = json.loads((directory / native.INVENTORY_FILENAME).read_text("utf-8"))
    payload["selections"][0]["odds_raw"] = "99.0"
    (directory / native.INVENTORY_FILENAME).write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )
    with pytest.raises(native.SportyBetUserInventoryError, match="noncanonical"):
        native.verify_inventory_directory(
            directory,
            evidence_directory=evidence,
            repository_root=repo,
        )


def test_wrong_or_traversing_roots_fail_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    evidence = _evidence(repo)
    with pytest.raises(native.SportyBetUserInventoryError):
        native.store_inventory_from_evidence(
            evidence,
            repository_root=repo,
            output_root=Path("../escape"),
        )
    with pytest.raises(native.SportyBetUserInventoryError):
        native.store_inventory_from_evidence(
            evidence,
            repository_root=repo,
            evidence_root=Path(".cache/athena-research/not-reviewed"),
        )


def test_command_receipt_exposes_counts_but_never_fresh_price_authority(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    evidence = _evidence(repo)
    receipt = command.build_user_inventory(
        evidence_directory=evidence,
        repository_root=repo,
    )
    assert receipt["status"] == "USER_CONTROLLED_PROVIDER_NATIVE_INVENTORY_PRESERVED"
    assert receipt["event_count"] == 1
    assert receipt["selection_count"] == 3
    assert receipt["market_identity_count"] == 3
    assert receipt["available_selection_count"] == 1
    assert receipt["suspended_selection_count"] == 1
    assert receipt["unknown_availability_selection_count"] == 1
    assert receipt["athena_network_acquisition_performed"] is False
    assert receipt["provider_quote_at"] is None
    assert receipt["provider_snapshot_id"] is None
    for key in (
        "network_acquisition_authorized",
        "fixture_reconciliation_authorized",
        "canonical_market_mapping_authorized",
        "fresh_price_authorized",
        "pricing_authorized",
        "model_integration_authorized",
        "selection_authorized",
        "slip_construction_authorized",
        "sportybet_execution_authorized",
        "bet_authorized",
    ):
        assert receipt[key] is False


def test_inventory_and_command_contain_no_network_client_imports() -> None:
    source = Path(native.__file__).read_text(encoding="utf-8")
    script = Path(command.__file__).read_text(encoding="utf-8")
    forbidden = (
        "urllib.request",
        "http.client",
        "requests",
        "httpx",
        "aiohttp",
        "socket.create_connection",
        "playwright",
        "selenium",
    )
    for token in forbidden:
        assert token not in source
        assert token not in script
