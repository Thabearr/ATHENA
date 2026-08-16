import json

import domain.pr69_primary_time_basis_semantic_qualification_v2 as q


def test_exact_v2_artifact_and_protocol_lineage_are_frozen():
    assert q.V2_RUN_ID == 31974333489
    assert q.V2_ARTIFACT_ID == 9270750452
    assert q.V2_ARTIFACT_SHA256 == "186188a0cec4e3febc8971c0f69eb1feb7dec6d2f35052ce48d2913c37265a6c"
    assert q.V2_PACKAGE_SHA256 == "2212663bece44296494a0aff1edbdb1574e940685588f73829ac80f58a6791c5"
    assert q.PR124_PROTOCOL_SHA256 == "28ec0a0208858ce3258a584bad1361577a0e202e5cbdb8eb9b13cdd47d7455a3"


def test_capture_campaign_is_complete_and_pair_stable():
    receipt = q.qualification_receipt()
    assessment = receipt["capture_assessment"]
    assert assessment["successful_slots"] == assessment["required_slots"] == 8
    assert assessment["all_pairs_identical"] is True
    assert assessment["all_pairs_within_frozen_window"] is True
    assert len(assessment["targets"]) == 4
    assert all(target["pair_identical"] for target in assessment["targets"])
    assert all(300 <= target["pair_separation_seconds"] <= 3600 for target in assessment["targets"])


def test_primary_notes_prove_field_meaning_but_not_clock_basis():
    records = {record["record_id"]: record for record in q.SEMANTIC_RECORDS}
    time_record = records["NOTES_TIME_FIELD_MEANING"]
    assert time_record["text"] == "Time = Time of match kick off"
    assert time_record["classification"] == "ADMISSIBLE_PRIMARY_FIELD_SEMANTIC"
    assert time_record["establishes_csv_time_basis"] is False
    assert time_record["establishes_historical_effective_scope"] is False


def test_uk_and_bst_context_cannot_be_promoted_to_csv_time_rule():
    context = [
        record for record in q.SEMANTIC_RECORDS
        if record["classification"] == "ADMISSIBLE_PRIMARY_SITE_CLOCK_CONTEXT_ONLY"
    ]
    assert {record["record_id"] for record in context} == {
        "FIXTURE_ODDS_COLLECTION_BST_CONTEXT",
        "FIXTURE_UPLOAD_UK_TIME_CONTEXT",
    }
    assert all(record["establishes_csv_time_basis"] is False for record in context)


def test_direct_resolution_fails_closed_for_all_21226_rows():
    route = q.DIRECT_ROUTE
    assert route["available"] is False
    assert route["explicit_csv_timezone_or_offset_rule_present"] is False
    assert route["explicit_dst_transition_rule_present"] is False
    assert route["historical_effective_scope_proven"] is False
    assert route["all_relevant_pr69_rows_mappable"] is False
    assert route["mapped_rows"] == 0
    assert route["unresolved_rows"] == 21226
    assert route["reason"] == q.PRIMARY_STATUS


def test_no_cross_source_or_downstream_authority_is_created():
    assert q.QUALIFICATION_STATE == "EXECUTED_PRIMARY_EVIDENCE_ADMISSIBLE_DIRECT_TIME_BASIS_UNRESOLVED"
    assert q.FORMAL_INVARIANCE_ROUTE["executed"] is False
    assert q.FORMAL_INVARIANCE_ROUTE["assumptions_proven"] is False
    assert all(value is False for value in q.SAFETY.values())


def test_receipt_is_deterministic_and_validates():
    q.validate_qualification()
    first = q.canonical_receipt_bytes()
    second = q.canonical_receipt_bytes()
    assert first == second
    assert json.loads(first) == q.qualification_receipt()
    assert len(q.canonical_receipt_sha256()) == 64
