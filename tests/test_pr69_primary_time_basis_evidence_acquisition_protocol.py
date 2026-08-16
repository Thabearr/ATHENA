"""Tests for PR124 primary time-basis evidence acquisition preregistration."""
from __future__ import annotations

import dataclasses
import hashlib

import pytest

import domain.pr69_primary_time_basis_evidence_acquisition_protocol as p


def _protocol():
    return p.build_pr69_primary_time_basis_evidence_acquisition_protocol()


def test_protocol_is_exact_canonical_identity() -> None:
    protocol = _protocol()
    raw = p.canonical_pr69_primary_time_basis_evidence_acquisition_protocol_bytes(protocol)
    assert len(raw) == p.PROTOCOL_SIZE == 9_039
    assert hashlib.sha256(raw).hexdigest() == p.PROTOCOL_SHA256
    assert p.PROTOCOL_SHA256 == "28ec0a0208858ce3258a584bad1361577a0e202e5cbdb8eb9b13cdd47d7455a3"


def test_protocol_preserves_pr123_blocker_and_frozen_scope() -> None:
    protocol = _protocol()
    assert protocol.blocking_status == "BLOCKED_NO_ADMISSIBLE_PRIMARY_TIME_BASIS_EVIDENCE"
    scope = protocol.effective_scope_contract
    assert tuple(scope["frozen_seasons"]) == p.SEASONS
    assert tuple(scope["frozen_model_league_codes"]) == p.MODEL_LEAGUE_CODES
    assert scope["source_file_count"] == 66
    assert scope["source_fixture_count"] == 21_226
    assert scope["source_total_bytes"] == 10_006_877
    assert scope["full_athena_competition_universe_claimed"] is False


def test_exact_primary_targets_are_frozen_and_role_limited() -> None:
    targets = _protocol().targets
    assert [target.target_id for target in targets] == [
        "NOTES_TXT", "DATA_OVERVIEW", "HISTORICAL_DOWNLOAD_OVERVIEW", "FIXTURES_OVERVIEW"
    ]
    assert [target.path for target in targets] == ["/notes.txt", "/data.php", "/downloadm.php", "/matches.php"]
    assert all(target.to_dict()["url"].startswith(p.PRIMARY_ORIGIN) for target in targets)
    notes = targets[0]
    assert notes.content_type_prefix == "text/plain"
    assert "TIMEZONE_OFFSET_DST" in notes.interpretation_limit
    fixtures = targets[-1]
    assert "CONTEXT_ONLY" in fixtures.interpretation_limit


def test_request_and_capture_contract_do_not_impersonate_or_normalize() -> None:
    protocol = _protocol()
    request = protocol.request_identity
    assert request["method"] == "GET"
    assert request["host"] == "www.football-data.co.uk"
    assert request["redirects_authorized"] is False
    assert request["cookies_authorized"] is False
    assert request["browser_impersonation_authorized"] is False
    assert request["proxy_evasion_authorized"] is False
    assert request["tls_verification_required"] is True
    capture = protocol.capture_contract
    assert capture["raw_body_hashed_before_decode"] is True
    assert capture["raw_body_line_endings_normalized_before_hash"] is False
    assert capture["raw_body_charset_normalized_before_hash"] is False
    assert capture["no_overwrite"] is True


def test_repeated_capture_schedule_and_failure_accounting_are_frozen() -> None:
    schedule = _protocol().capture_schedule
    assert schedule["target_count"] == 4
    assert schedule["capture_slots_per_target"] == 2
    assert tuple(schedule["slot_labels"]) == ("A", "B")
    assert schedule["minimum_same_target_pair_separation_seconds"] == 300
    assert schedule["maximum_same_target_pair_separation_seconds"] == 3600
    assert schedule["maximum_attempts_per_slot"] == 3
    assert tuple(schedule["retry_delays_seconds"]) == (60, 300)
    assert schedule["required_successful_capture_count"] == 8
    assert schedule["failed_attempts_count_as_success"] is False


def test_admissibility_separates_current_semantics_from_historical_scope() -> None:
    contract = _protocol().admissibility_contract
    assert contract["exact_raw_bytes_and_sha256_required"] is True
    assert contract["semantic_extract_must_reference_raw_sha256_and_exact_byte_or_line_location"] is True
    assert contract["timezone_or_offset_or_civil_time_rule_must_be_explicit_for_direct_resolution"] is True
    assert contract["dst_transition_semantics_must_be_explicit_when_applicable"] is True
    assert contract["historical_effective_scope_must_be_separately_proven"] is True
    assert contract["current_capture_alone_proves_historical_scope"] is False
    assert contract["site_clock_wording_alone_proves_csv_time_basis"] is False


def test_forbidden_shortcuts_cover_current_notes_and_site_clock_wording() -> None:
    forbidden = set(_protocol().forbidden_shortcuts)
    assert "DO_NOT_BACKDATE_CURRENT_NOTES_TXT_TO_THE_FROZEN_SIX_SEASONS_WITHOUT_PRIMARY_EFFECTIVE_SCOPE_EVIDENCE" in forbidden
    assert "DO_NOT_TREAT_SITE_WIDE_UK_TIME_OR_BRITISH_STANDARD_TIME_WORDING_AS_THE_CSV_TIME_RULE_UNLESS_PRIMARY_BYTES_EXPLICITLY_LINK_THEM" in forbidden
    assert "DO_NOT_TREAT_TIME_EQUALS_MATCH_KICK_OFF_AS_A_TIMEZONE_OFFSET_OR_DST_RULE" in forbidden
    assert "DO_NOT_TREAT_FOTMOB_EUROPE_OSLO_OR_ANY_CROSS_SOURCE_CLOCK_AS_PRIMARY_REFERENCE_EVIDENCE" in forbidden


def test_execution_output_is_acquisition_only() -> None:
    protocol = _protocol()
    output = protocol.execution_output_contract
    assert output["raw_capture_bundle_required"] is True
    assert output["pair_drift_table_required"] is True
    assert output["historical_effective_scope_inventory_required"] is True
    assert output["source_file_scope_coverage_accounting_required"] is True
    assert output["fixture_row_scope_coverage_accounting_required"] is True
    assert output["pr69_source_local_time_basis_resolution_performed"] is False
    assert output["fotmob_equivalence_assessment_performed"] is False
    assert output["pr80_constructor_input_authorized"] is False


def test_all_downstream_authority_remains_false_and_next_boundary_is_runner() -> None:
    protocol = _protocol()
    assert set(protocol.safety) == p.SAFETY_KEYS
    assert all(value is False for value in protocol.safety.values())
    assert protocol.network_acquisition_performed is False
    assert protocol.campaign_runner_implemented is False
    assert protocol.evidence_records_captured == 0
    assert protocol.next_required_boundary == "IMPLEMENT_REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_RUNNER"


def test_protocol_fails_closed_against_tampering() -> None:
    protocol = _protocol()
    with pytest.raises(p.PR69PrimaryTimeBasisEvidenceAcquisitionProtocolError):
        dataclasses.replace(protocol, network_acquisition_performed=True)
