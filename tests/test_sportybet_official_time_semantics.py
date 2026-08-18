from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from domain import sportybet_official_time_semantics as semantics
from scripts import import_sportybet_official_time_semantics as importer


UTC = dt.timezone.utc
OBSERVED = dt.datetime(2026, 8, 18, 16, 0, tzinfo=UTC)
IMPORTED = dt.datetime(2026, 8, 18, 16, 1, tzinfo=UTC)


def _html(statement: str = semantics.EXPECTED_STATEMENT) -> bytes:
    return (
        "<!doctype html><html><body><h1>Terms &amp; Conditions</h1>"
        f"<p>{statement}</p></body></html>"
    ).encode("utf-8")


def _build(raw: bytes | None = None) -> semantics.SportyBetOfficialTimeSemanticsQualification:
    return semantics.build_qualification(
        _html() if raw is None else raw,
        source_url=semantics.SOURCE_URL,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=semantics.ATTESTATION,
    )


def test_exact_official_gmt_statement_qualifies() -> None:
    qualification = _build()
    assert qualification.semantic_status == semantics.SEMANTIC_STATUS
    assert qualification.time_zone_label == "GMT"
    assert qualification.utc_offset_seconds == 0
    assert qualification.semantics_statement_occurrence_count == 1
    assert qualification.unless_stated_otherwise is True
    assert qualification.event_local_override_check_required is True
    assert qualification.event_application_status == semantics.EVENT_APPLICATION_STATUS
    assert qualification.event_year_proven is False


def test_statement_may_be_split_across_rendered_html_nodes() -> None:
    raw = (
        b"<html><body><p>All times stated on the Website and/or referred to by "
        b"SportyBet staff relate to <strong>GMT</strong> unless stated otherwise.</p>"
        b"</body></html>"
    )
    zone, count = semantics.extract_global_time_semantics(raw)
    assert (zone, count) == ("GMT", 1)


def test_duplicate_identical_rendered_statement_is_semantically_acceptable() -> None:
    raw = (
        "<html><body><p>" + semantics.EXPECTED_STATEMENT + "</p><p>" +
        semantics.EXPECTED_STATEMENT + "</p></body></html>"
    ).encode("utf-8")
    qualification = _build(raw)
    assert qualification.semantics_statement_occurrence_count == 2


@pytest.mark.parametrize(
    "statement",
    [
        "All times stated on the Website and/or referred to by SportyBet staff relate to UTC unless stated otherwise.",
        "All times stated on the Website and/or referred to by SportyBet staff relate to WAT unless stated otherwise.",
        "All times stated on the website and/or referred to by SportyBet staff relate to GMT unless stated otherwise.",
        "All times stated on the Website and/or referred to by SportyBet staff relate to GMT.",
    ],
)
def test_non_exact_or_non_gmt_semantics_fail_closed(statement: str) -> None:
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        _build(_html(statement))


def test_missing_statement_fails_closed() -> None:
    with pytest.raises(
        semantics.SportyBetOfficialTimeSemanticsError,
        match="statement not found",
    ):
        _build(b"<html><body><p>Terms page without time semantics.</p></body></html>")


def test_script_only_statement_cannot_cross_visible_text_boundary() -> None:
    raw = (
        "<html><body><script>" + semantics.EXPECTED_STATEMENT +
        "</script><p>Other visible terms.</p></body></html>"
    ).encode("utf-8")
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        _build(raw)


def test_invalid_utf8_fails_closed() -> None:
    with pytest.raises(
        semantics.SportyBetOfficialTimeSemanticsError,
        match="valid UTF-8",
    ):
        _build(b"\xff\xfe")


@pytest.mark.parametrize(
    "source_url",
    [
        "http://www.sportybet.com/ng/help?nav=terms-and-conditions",
        "https://sportybet.com/ng/help?nav=terms-and-conditions",
        "https://lite.sportybet.com/ng/help?nav=terms-and-conditions",
        "https://www.sportybet.com/ng/help?nav=terms-and-conditions&subNav=x",
        "https://www.sportybet.com/ng/help?nav=terms-and-conditions#section",
        "https://www.sportybet.com/ng/help/?nav=terms-and-conditions",
    ],
)
def test_only_exact_reviewed_official_source_url_is_accepted(source_url: str) -> None:
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        semantics.build_qualification(
            _html(),
            source_url=source_url,
            observed_at_user_attested=OBSERVED,
            imported_at_utc=IMPORTED,
            attestation=semantics.ATTESTATION,
        )


def test_import_time_must_not_precede_manual_observation() -> None:
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        semantics.build_qualification(
            _html(),
            source_url=semantics.SOURCE_URL,
            observed_at_user_attested=IMPORTED,
            imported_at_utc=OBSERVED,
            attestation=semantics.ATTESTATION,
        )


def test_manual_attestation_is_exact() -> None:
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        semantics.build_qualification(
            _html(),
            source_url=semantics.SOURCE_URL,
            observed_at_user_attested=OBSERVED,
            imported_at_utc=IMPORTED,
            attestation="yes I saw it",
        )


def test_statement_hash_is_frozen_and_recomputed() -> None:
    qualification = _build()
    assert qualification.semantics_statement_sha256 == semantics.EXPECTED_STATEMENT_SHA256
    assert semantics.EXPECTED_STATEMENT_SHA256 == (
        "2fed00c2e1d3e7f2b0b6cff1e4f68ee17874529af54958a14aed68e7ca0b7de4"
    )


def test_canonical_qualification_is_deterministic_and_newline_terminated() -> None:
    qualification = _build()
    first = semantics.canonical_qualification_bytes(qualification)
    second = semantics.canonical_qualification_bytes(_build())
    assert first == second
    assert first.endswith(b"\n")
    assert json.loads(first) == qualification.to_dict()
    assert semantics.qualification_sha256(qualification) == semantics.qualification_sha256(_build())


def test_every_downstream_authority_remains_false() -> None:
    qualification = _build()
    assert qualification.safety
    assert all(value is False for value in qualification.safety.values())
    assert qualification.provider_quote_at is None
    assert qualification.provider_snapshot_id is None
    assert qualification.athena_network_acquisition_performed is False


def test_bool_cannot_impersonate_integer_offset_or_occurrence_count() -> None:
    qualification = _build()
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        dataclasses.replace(qualification, utc_offset_seconds=False)
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        dataclasses.replace(qualification, semantics_statement_occurrence_count=True)


def test_forged_event_application_or_year_claim_fails_closed() -> None:
    qualification = _build()
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        dataclasses.replace(qualification, event_local_override_check_required=False)
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        dataclasses.replace(qualification, event_year_proven=True)
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        dataclasses.replace(qualification, event_application_status="AUTHORIZED")


def test_storage_round_trip_is_idempotent_and_replays_raw_semantics(tmp_path: Path) -> None:
    raw = _html()
    directory, first = semantics.store_official_time_semantics_evidence(
        raw,
        source_url=semantics.SOURCE_URL,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=semantics.ATTESTATION,
        repository_root=tmp_path,
    )
    second_directory, second = semantics.store_official_time_semantics_evidence(
        raw,
        source_url=semantics.SOURCE_URL,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=semantics.ATTESTATION,
        repository_root=tmp_path,
    )
    assert directory == second_directory
    assert first.to_dict() == second.to_dict()
    assert directory.name == semantics.evidence_identifier(first)
    verified = semantics.verify_evidence_directory(
        directory,
        allowed_root=tmp_path / semantics.ALLOWED_OUTPUT_RELATIVE,
    )
    assert verified.to_dict() == first.to_dict()


def test_storage_detects_raw_or_qualification_tampering(tmp_path: Path) -> None:
    raw = _html()
    directory, _ = semantics.store_official_time_semantics_evidence(
        raw,
        source_url=semantics.SOURCE_URL,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=semantics.ATTESTATION,
        repository_root=tmp_path,
    )
    (directory / semantics.RAW_FILENAME).write_bytes(raw + b" ")
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        semantics.verify_evidence_directory(
            directory,
            allowed_root=tmp_path / semantics.ALLOWED_OUTPUT_RELATIVE,
        )


def test_unreviewed_output_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        semantics.store_official_time_semantics_evidence(
            _html(),
            source_url=semantics.SOURCE_URL,
            observed_at_user_attested=OBSERVED,
            imported_at_utc=IMPORTED,
            attestation=semantics.ATTESTATION,
            repository_root=tmp_path,
            output_root=Path(".cache/elsewhere"),
        )


def test_import_command_receipt_never_promotes_event_or_betting_authority(
    tmp_path: Path,
) -> None:
    source = tmp_path / "terms.html"
    source.write_bytes(_html())
    receipt = importer.import_evidence(
        html_file=source,
        source_url=semantics.SOURCE_URL,
        observed_at="2026-08-18T16:00:00Z",
        attestation=semantics.ATTESTATION,
        repository_root=tmp_path,
        imported_at_utc=IMPORTED,
    )
    assert receipt["status"] == "OFFICIAL_TIME_SEMANTICS_EVIDENCE_PRESERVED_AND_QUALIFIED"
    assert receipt["time_zone_label"] == "GMT"
    assert receipt["utc_offset_seconds"] == 0
    assert receipt["event_local_override_check_required"] is True
    assert receipt["event_year_proven"] is False
    assert receipt["athena_network_acquisition_performed"] is False
    for key in (
        "fixture_reconciliation_authorized",
        "fresh_price_authorized",
        "pricing_authorized",
        "selection_authorized",
        "slip_construction_authorized",
        "booking_code_authorized",
        "sportybet_execution_authorized",
        "bet_authorized",
    ):
        assert receipt[key] is False


def test_import_command_requires_exact_attestation_and_source(tmp_path: Path) -> None:
    source = tmp_path / "terms.html"
    source.write_bytes(_html())
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        importer.import_evidence(
            html_file=source,
            source_url=semantics.SOURCE_URL,
            observed_at="2026-08-18T16:00:00Z",
            attestation="wrong",
            repository_root=tmp_path,
            imported_at_utc=IMPORTED,
        )
    with pytest.raises(semantics.SportyBetOfficialTimeSemanticsError):
        importer.import_evidence(
            html_file=source,
            source_url="https://www.sportybet.com/ng/help?nav=sports",
            observed_at="2026-08-18T16:00:00Z",
            attestation=semantics.ATTESTATION,
            repository_root=tmp_path,
            imported_at_utc=IMPORTED,
        )


def test_protocol_is_canonical_and_keeps_specific_event_use_closed() -> None:
    path = Path("artifacts/research-protocols/sportybet-official-time-semantics-v1.json")
    raw = path.read_bytes()
    parsed = json.loads(raw)
    canonical = (
        json.dumps(
            parsed,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert raw == canonical
    assert parsed["source_url"] == semantics.SOURCE_URL
    assert parsed["expected_semantics_statement_sha256"] == semantics.EXPECTED_STATEMENT_SHA256
    assert parsed["expected_time_zone_label"] == "GMT"
    assert parsed["utc_offset_seconds"] == 0
    assert parsed["specific_event_time_basis_authorized"] is False
    assert parsed["event_local_override_check_required"] is True
    assert parsed["event_year_proven"] is False
    assert parsed["network_acquisition_authorized"] is False
    assert all(value is False for value in parsed["safety"].values())
