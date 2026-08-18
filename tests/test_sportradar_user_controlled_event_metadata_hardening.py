from __future__ import annotations

import dataclasses
import json

import pytest

from domain import sportradar_user_controlled_event_metadata as metadata
from tests.test_sportradar_user_controlled_event_metadata import (
    IMPORTED,
    OBSERVED,
    _evidence,
    _payload,
    _raw,
    _url,
)
from tests.test_sportybet_sportradar_event_identity import _build as _build_bridge


def test_source_url_rejects_query_fragment_credentials_ports_and_percent_encoding() -> None:
    invalid = [
        _url() + "?api_key=secret",
        _url() + "#fragment",
        _url().replace("https://", "https://user:secret@"),
        _url().replace("api.sportradar.com", "api.sportradar.com:443"),
        _url().replace("sr:sport_event:123", "sr%3Asport_event%3A123"),
        _url().replace("/en/", "/de/"),
        _url().replace("/v4/", "/v3/"),
        _url().replace("/trial/", "/unknown/"),
    ]
    for value in invalid:
        with pytest.raises(metadata.SportradarUserControlledEventMetadataError):
            metadata.validate_source_url(value)


def test_exact_timestamp_and_normalized_timestamp_cannot_diverge(tmp_path) -> None:
    value, *_ = _evidence(tmp_path)
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="start_time_utc_normalized",
    ):
        dataclasses.replace(
            value,
            start_time_utc_normalized="2026-08-18T21:00:00.000000Z",
        )
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="provider_generated_at_utc_normalized",
    ):
        dataclasses.replace(
            value,
            provider_generated_at_utc_normalized="2026-08-18T19:00:01.000000Z",
        )


def test_legacy_and_current_event_numeric_payload_must_match(tmp_path) -> None:
    value, *_ = _evidence(tmp_path)
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="numeric payload",
    ):
        dataclasses.replace(value, source_sportybet_event_id="sr:match:124")


def test_response_requires_exactly_one_home_and_one_away(tmp_path) -> None:
    event_bridge, manifest, inventory, sporty_raw = _build_bridge(tmp_path)
    payload = _payload()
    payload["sport_event"]["competitors"][1]["qualifier"] = "home"
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="one home and one away",
    ):
        metadata.build_event_metadata_evidence(
            raw,
            source_url=_url(),
            observed_at_user_attested=OBSERVED,
            imported_at_utc=IMPORTED,
            attestation=metadata.ATTESTATION,
            event_bridge=event_bridge,
            sportybet_manifest=manifest,
            sportybet_inventory=inventory,
            sportybet_raw_html=sporty_raw,
        )


def test_home_and_away_competitor_ids_must_be_distinct(tmp_path) -> None:
    value, *_ = _evidence(tmp_path)
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="must be distinct",
    ):
        dataclasses.replace(value, away_competitor_id=value.home_competitor_id)


def test_malformed_or_naive_provider_timestamp_fails_closed(tmp_path) -> None:
    event_bridge, manifest, inventory, sporty_raw = _build_bridge(tmp_path)
    for start_time in ("not-a-time", "2026-08-18T20:00:00"):
        with pytest.raises(metadata.SportradarUserControlledEventMetadataError):
            metadata.build_event_metadata_evidence(
                _raw(start_time=start_time),
                source_url=_url(),
                observed_at_user_attested=OBSERVED,
                imported_at_utc=IMPORTED,
                attestation=metadata.ATTESTATION,
                event_bridge=event_bridge,
                sportybet_manifest=manifest,
                sportybet_inventory=inventory,
                sportybet_raw_html=sporty_raw,
            )


def test_nonfinite_json_is_rejected() -> None:
    raw = b'{"sport_event":{"id":"sr:sport_event:123","x":NaN}}'
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="non-finite",
    ):
        metadata.strict_response_json(raw)


@pytest.mark.parametrize(
    "field",
    [
        "event_metadata_resolution_authorized",
        "sportybet_year_promoted",
        "sportybet_kickoff_utc_promoted",
        "fixture_identity_promoted",
    ],
)
def test_no_promotion_flag_can_be_flipped(tmp_path, field: str) -> None:
    value, *_ = _evidence(tmp_path)
    with pytest.raises(metadata.SportradarUserControlledEventMetadataError):
        dataclasses.replace(value, **{field: True})


def test_every_safety_authority_remains_exact_false(tmp_path) -> None:
    value, *_ = _evidence(tmp_path)
    for key in value.safety:
        promoted = dict(value.safety)
        promoted[key] = True
        with pytest.raises(
            metadata.SportradarUserControlledEventMetadataError,
            match="must be exact bool False",
        ):
            dataclasses.replace(value, safety=promoted)


def test_api_key_or_request_headers_cannot_be_marked_persisted(tmp_path) -> None:
    value, *_ = _evidence(tmp_path)
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="must never be persisted",
    ):
        dataclasses.replace(value, api_key_persisted=True)
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="must never be persisted",
    ):
        dataclasses.replace(value, request_headers_persisted=True)


def test_tampered_raw_response_cannot_revalidate_existing_metadata(tmp_path) -> None:
    value, raw_response, event_bridge, manifest, inventory, sporty_raw = _evidence(tmp_path)
    tampered = raw_response.replace(b"Example Home FC", b"Forged Home FC", 1)
    with pytest.raises(metadata.SportradarUserControlledEventMetadataError):
        metadata.revalidate_event_metadata_evidence(
            value,
            tampered,
            event_bridge=event_bridge,
            sportybet_manifest=manifest,
            sportybet_inventory=inventory,
            sportybet_raw_html=sporty_raw,
        )


def test_tampered_sportybet_source_cannot_reuse_metadata(tmp_path) -> None:
    value, raw_response, event_bridge, manifest, inventory, sporty_raw = _evidence(tmp_path)
    tampered_sporty = sporty_raw.replace(b"Example Home FC", b"Forged Home FC", 1)
    with pytest.raises(metadata.SportradarUserControlledEventMetadataError):
        metadata.revalidate_event_metadata_evidence(
            value,
            raw_response,
            event_bridge=event_bridge,
            sportybet_manifest=manifest,
            sportybet_inventory=inventory,
            sportybet_raw_html=tampered_sporty,
        )


def test_evidence_directory_rejects_extra_files(tmp_path) -> None:
    event_bridge, manifest, inventory, sporty_raw = _build_bridge(tmp_path)
    repository = tmp_path / "repo"
    directory, _ = metadata.store_event_metadata_evidence(
        _raw(),
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
    (directory / "unexpected.txt").write_text("nope", encoding="utf-8")
    with pytest.raises(
        metadata.SportradarUserControlledEventMetadataError,
        match="contents mismatch",
    ):
        metadata.verify_evidence_directory(
            directory,
            allowed_root=repository / metadata.ALLOWED_OUTPUT_RELATIVE,
        )
