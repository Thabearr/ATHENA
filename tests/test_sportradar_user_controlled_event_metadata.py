from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from domain import sportradar_user_controlled_event_metadata as metadata
from tests.test_sportybet_sportradar_event_identity import _build as _build_bridge


OBSERVED = dt.datetime(2026, 8, 18, 18, 0, tzinfo=dt.timezone.utc)
IMPORTED = dt.datetime(2026, 8, 18, 18, 1, tzinfo=dt.timezone.utc)
PROTOCOL = Path(
    "artifacts/research-protocols/sportradar-user-controlled-event-metadata-evidence-v1.json"
)


def _url(*, event_id: int = 123, access_level: str = "trial") -> str:
    return (
        f"https://api.sportradar.com/soccer/{access_level}/v4/en/"
        f"sport_events/sr:sport_event:{event_id}/summary.json"
    )


def _payload(
    *,
    event_id: int = 123,
    sport_id: int = 1,
    start_time: str = "2026-08-18T20:00:00+00:00",
    start_time_confirmed: bool | None = True,
    date_confirmed: bool | None = True,
) -> dict:
    sport_event = {
        "id": f"sr:sport_event:{event_id}",
        "start_time": start_time,
        "sport_event_context": {
            "sport": {"id": f"sr:sport:{sport_id}", "name": "Soccer"},
            "competition": {
                "id": "sr:competition:17",
                "name": "Example League",
            },
        },
        "competitors": [
            {
                "id": "sr:competitor:100",
                "name": "Example Home FC",
                "qualifier": "home",
            },
            {
                "id": "sr:competitor:200",
                "name": "Example Away FC",
                "qualifier": "away",
            },
        ],
    }
    if start_time_confirmed is not None:
        sport_event["start_time_confirmed"] = start_time_confirmed
    if date_confirmed is not None:
        sport_event["date_confirmed"] = date_confirmed
    return {
        "generated_at": "2026-08-18T18:00:01+00:00",
        "sport_event": sport_event,
    }


def _raw(**kwargs) -> bytes:
    return (
        json.dumps(
            _payload(**kwargs),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _evidence(tmp_path: Path, **response_kwargs):
    event_bridge, manifest, inventory, sporty_raw = _build_bridge(tmp_path)
    raw_response = _raw(**response_kwargs)
    value = metadata.build_event_metadata_evidence(
        raw_response,
        source_url=_url(),
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=metadata.ATTESTATION,
        event_bridge=event_bridge,
        sportybet_manifest=manifest,
        sportybet_inventory=inventory,
        sportybet_raw_html=sporty_raw,
    )
    return value, raw_response, event_bridge, manifest, inventory, sporty_raw


def test_protocol_is_canonical_and_keeps_promotion_closed() -> None:
    raw = PROTOCOL.read_bytes()
    payload = json.loads(raw)
    canonical = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert raw == canonical
    assert payload["schema_version"] == 1
    assert payload["status"] == metadata.STATUS
    assert payload["exact_bridge_revalidation_required"] is True
    assert payload["raw_response_preserved"] is True
    assert payload["event_metadata_ingested"] is True
    assert payload["event_metadata_resolution_authorized"] is False
    assert payload["fixture_identity_promotion_authorized"] is False
    assert payload["sportybet_year_capability"] == "NOT_PROMOTED_IN_THIS_BOUNDARY"
    assert payload["sportybet_kickoff_utc_capability"] == "NOT_PROMOTED_IN_THIS_BOUNDARY"
    assert payload["athena_sportradar_network_acquisition_authorized"] is False
    assert all(item is False for item in payload["safety"].values())


def test_official_response_is_bound_to_exact_verified_bridge(tmp_path: Path) -> None:
    value, _raw_response, event_bridge, *_ = _evidence(tmp_path)
    assert value.source_sportybet_event_id == "sr:match:123"
    assert value.source_sportradar_event_id == "sr:sport_event:123"
    assert value.response_event_id == "sr:sport_event:123"
    assert value.source_bridge_sha256
    assert value.exact_bridge_identity_matched is True
    assert value.official_response_event_identity_matched is True
    assert value.source_bridge_sha256 == __import__(
        "domain.sportybet_sportradar_event_identity",
        fromlist=["bridge_sha256"],
    ).bridge_sha256(event_bridge)


def test_documented_event_metadata_is_preserved_without_promotion(tmp_path: Path) -> None:
    value, *_ = _evidence(tmp_path)
    assert value.sport_id == "sr:sport:1"
    assert value.competition_id == "sr:competition:17"
    assert value.competition_name == "Example League"
    assert value.home_competitor_id == "sr:competitor:100"
    assert value.home_competitor_name == "Example Home FC"
    assert value.away_competitor_id == "sr:competitor:200"
    assert value.away_competitor_name == "Example Away FC"
    assert value.start_time == "2026-08-18T20:00:00+00:00"
    assert value.start_time_utc_normalized == "2026-08-18T20:00:00.000000Z"
    assert value.start_time_confirmed is True
    assert value.date_confirmed is True
    assert value.provider_generated_at == "2026-08-18T18:00:01+00:00"
    assert value.provider_generated_at_utc_normalized == "2026-08-18T18:00:01.000000Z"
    assert value.event_metadata_resolution_authorized is False
    assert value.sportybet_year_promoted is False
    assert value.sportybet_kickoff_utc_promoted is False
    assert value.fixture_identity_promoted is False
    assert all(item is False for item in value.safety.values())


def test_unconfirmed_flags_are_preserved_not_inferred(tmp_path: Path) -> None:
    value, *_ = _evidence(
        tmp_path,
        start_time_confirmed=False,
        date_confirmed=True,
    )
    assert value.start_time_confirmed is False
    assert value.date_confirmed is True
    assert value.sportybet_year_promoted is False
    assert value.sportybet_kickoff_utc_promoted is False


def test_absent_confirmation_flags_remain_unknown(tmp_path: Path) -> None:
    value, *_ = _evidence(
        tmp_path,
        start_time_confirmed=None,
        date_confirmed=None,
    )
    assert value.start_time_confirmed is None
    assert value.date_confirmed is None


def test_wrong_request_event_id_fails_before_response_promotion(tmp_path: Path) -> None:
    event_bridge, manifest, inventory, sporty_raw = _build_bridge(tmp_path)
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="verified bridge ID",
    ):
        metadata.build_event_metadata_evidence(
            _raw(),
            source_url=_url(event_id=124),
            observed_at_user_attested=OBSERVED,
            imported_at_utc=IMPORTED,
            attestation=metadata.ATTESTATION,
            event_bridge=event_bridge,
            sportybet_manifest=manifest,
            sportybet_inventory=inventory,
            sportybet_raw_html=sporty_raw,
        )


def test_wrong_response_event_id_fails_closed(tmp_path: Path) -> None:
    event_bridge, manifest, inventory, sporty_raw = _build_bridge(tmp_path)
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="does not match verified resolver key",
    ):
        metadata.build_event_metadata_evidence(
            _raw(event_id=124),
            source_url=_url(),
            observed_at_user_attested=OBSERVED,
            imported_at_utc=IMPORTED,
            attestation=metadata.ATTESTATION,
            event_bridge=event_bridge,
            sportybet_manifest=manifest,
            sportybet_inventory=inventory,
            sportybet_raw_html=sporty_raw,
        )


def test_non_soccer_metadata_fails_closed(tmp_path: Path) -> None:
    event_bridge, manifest, inventory, sporty_raw = _build_bridge(tmp_path)
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="soccer",
    ):
        metadata.build_event_metadata_evidence(
            _raw(sport_id=2),
            source_url=_url(),
            observed_at_user_attested=OBSERVED,
            imported_at_utc=IMPORTED,
            attestation=metadata.ATTESTATION,
            event_bridge=event_bridge,
            sportybet_manifest=manifest,
            sportybet_inventory=inventory,
            sportybet_raw_html=sporty_raw,
        )


def test_duplicate_json_key_is_rejected_at_nested_level() -> None:
    raw = b'{"sport_event":{"id":"sr:sport_event:123","id":"sr:sport_event:124"}}'
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="duplicate JSON object key",
    ):
        metadata.strict_response_json(raw)


def test_metadata_revalidation_requires_exact_response_and_sportybet_sources(
    tmp_path: Path,
) -> None:
    value, raw_response, event_bridge, manifest, inventory, sporty_raw = _evidence(tmp_path)
    rebuilt = metadata.revalidate_event_metadata_evidence(
        value,
        raw_response,
        event_bridge=event_bridge,
        sportybet_manifest=manifest,
        sportybet_inventory=inventory,
        sportybet_raw_html=sporty_raw,
    )
    assert metadata.canonical_manifest_bytes(rebuilt) == metadata.canonical_manifest_bytes(value)

    forged = dataclasses.replace(value, source_bridge_sha256="0" * 64)
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="exact deterministic derivative",
    ):
        metadata.revalidate_event_metadata_evidence(
            forged,
            raw_response,
            event_bridge=event_bridge,
            sportybet_manifest=manifest,
            sportybet_inventory=inventory,
            sportybet_raw_html=sporty_raw,
        )


def test_durable_store_is_idempotent_and_verifiable(tmp_path: Path) -> None:
    event_bridge, manifest, inventory, sporty_raw = _build_bridge(tmp_path)
    repository = tmp_path / "repo"
    raw_response = _raw()
    first_dir, first = metadata.store_event_metadata_evidence(
        raw_response,
        source_url=_url(),
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=metadata.ATTESTATION,
        event_bridge=event_bridge,
        sportybet_manifest=manifest,
        sportybet_inventory=inventory,
        sportybet_raw_html=sporty_raw,
        repository_root=repository,
    )
    second_dir, second = metadata.store_event_metadata_evidence(
        raw_response,
        source_url=_url(),
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=metadata.ATTESTATION,
        event_bridge=event_bridge,
        sportybet_manifest=manifest,
        sportybet_inventory=inventory,
        sportybet_raw_html=sporty_raw,
        repository_root=repository,
    )
    assert first_dir == second_dir
    assert metadata.canonical_manifest_bytes(first) == metadata.canonical_manifest_bytes(second)
    verified = metadata.verify_evidence_directory(
        first_dir,
        allowed_root=repository / metadata.ALLOWED_OUTPUT_RELATIVE,
    )
    assert metadata.evidence_sha256(verified) == metadata.evidence_sha256(first)
