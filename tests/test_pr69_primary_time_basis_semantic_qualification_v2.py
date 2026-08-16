import json
from pathlib import Path

import domain.pr69_primary_time_basis_semantic_qualification_v2 as q


RECEIPT_PATH = Path(
    "artifacts/research-manifests/"
    "pr69-primary-time-basis-semantic-qualification-v2.json"
)
EXPECTED_RECEIPT_SHA256 = (
    "cbdf0bbf9e31d44e0d00125bd10d714272ac6046386cf52f1d9d27b3ab84bb8d"
)
EXPECTED_RECEIPT_SIZE = 5_422


def test_exact_v2_artifact_and_protocol_lineage_are_frozen():
    assert q.V2_RUN_ID == 31974333489
    assert q.V2_ARTIFACT_ID == 9270750452
    assert q.V2_ARTIFACT_SHA256 == (
        "186188a0cec4e3febc8971c0f69eb1feb7dec6d2f35052ce48d2913c37265a6c"
    )
    assert q.V2_PACKAGE_SHA256 == (
        "2212663bece44296494a0aff1edbdb1574e940685588f73829ac80f58a6791c5"
    )
    assert q.PR122_PROTOCOL_SHA256 == q.pr122.PROTOCOL_SHA256
    assert q.PR124_PROTOCOL_SHA256 == q.pr124.PROTOCOL_SHA256


def test_capture_campaign_is_complete_and_pair_stable():
    receipt = q.qualification_receipt()
    assessment = receipt["capture_assessment"]
    assert assessment["successful_slots"] == assessment["required_slots"] == 8
    assert assessment["all_pairs_identical"] is True
    assert assessment["all_pairs_within_frozen_window"] is True
    assert len(assessment["targets"]) == 4
    assert all(target["pair_identical"] for target in assessment["targets"])
    assert all(
        300 <= target["pair_separation_seconds"] <= 3600
        for target in assessment["targets"]
    )


def test_primary_notes_prove_field_meaning_but_not_clock_basis():
    records = {record["record_id"]: record for record in q.SEMANTIC_RECORDS}
    time_record = records["NOTES_TIME_FIELD_MEANING"]
    assert time_record["text"] == "Time = Time of match kick off"
    assert time_record["classification"] == "ADMISSIBLE_PRIMARY_FIELD_SEMANTIC"
    assert time_record["establishes_csv_time_basis"] is False
    assert time_record["establishes_historical_effective_scope"] is False


def test_uk_and_bst_context_cannot_be_promoted_to_csv_time_rule():
    records = {record["record_id"]: record for record in q.SEMANTIC_RECORDS}
    bst = records["FIXTURE_ODDS_COLLECTION_BST_CONTEXT"]
    upload = records["FIXTURE_UPLOAD_UK_TIME_CONTEXT"]

    assert bst["text"] == "British Standard Time"
    assert upload["text"] == "Latest fixtures uploaded: 14/08/26 11:26 UK time."
    assert upload["byte_start"] == 14_268
    assert upload["byte_end"] == 14_317
    assert all(
        record["establishes_csv_time_basis"] is False
        for record in (bst, upload)
    )


def test_direct_resolution_uses_frozen_pr122_blocker_and_fails_all_rows_closed():
    route = q.DIRECT_ROUTE
    assert q.PRIMARY_STATUS in q.pr122.QUALIFICATION_STATUS_VOCABULARY
    assert q.PRIMARY_STATUS == "BLOCKED_TIME_BASIS_SCOPE_OR_EFFECTIVE_PERIOD_AMBIGUOUS"
    assert route["available"] is False
    assert route["explicit_csv_timezone_or_offset_rule_present"] is False
    assert route["explicit_dst_transition_rule_present"] is False
    assert route["historical_effective_scope_proven"] is False
    assert route["all_relevant_pr69_rows_mappable"] is False
    assert route["mapped_rows"] == 0
    assert route["unresolved_rows"] == 21_226
    assert route["reason"] == q.PRIMARY_STATUS


def test_pr122_continuation_is_formal_invariance_not_a_silent_successor_rewrite():
    assert q.FORMAL_INVARIANCE_ROUTE == {
        "executed": False,
        "assumptions_proven": False,
        "status": "REQUIRED_NOT_EXECUTED_DIRECT_PRIMARY_SEMANTICS_UNRESOLVED",
    }
    assert q.NEXT_REQUIRED_BOUNDARY == (
        "PRE_REGISTER_REVIEWED_PR69_FORMAL_OPERATIONAL_INVARIANCE_QUALIFICATION_PROTOCOL"
    )


def test_no_cross_source_or_downstream_authority_is_created():
    assert q.QUALIFICATION_STATE == (
        "EXECUTED_PRIMARY_EVIDENCE_ADMISSIBLE_DIRECT_TIME_BASIS_UNRESOLVED"
    )
    assert all(value is False for value in q.SAFETY.values())


def test_checked_in_receipt_is_exact_canonical_bytes():
    q.validate_qualification()
    raw = RECEIPT_PATH.read_bytes()
    assert raw == q.canonical_receipt_bytes()
    assert len(raw) == EXPECTED_RECEIPT_SIZE == q.CANONICAL_RECEIPT_SIZE
    assert q.canonical_receipt_sha256() == EXPECTED_RECEIPT_SHA256
    assert q.CANONICAL_RECEIPT_SHA256 == EXPECTED_RECEIPT_SHA256
    assert json.loads(raw) == q.qualification_receipt()
