"""Qualify the preserved PR69 primary time-basis evidence campaign V2.

This module records the reviewed semantic result of the exact preserved V2
campaign. It does not infer a CSV timezone from generic site clock wording and
it does not authorize PR80/model/probability/pricing/selection/BET use.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = 2
QUALIFICATION_ID = "PR69_PRIMARY_TIME_BASIS_SEMANTIC_QUALIFICATION_V2"
QUALIFICATION_SCOPE = (
    "EXACT_PRESERVED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_CAMPAIGN_V2_ONLY"
)
QUALIFICATION_STATE = (
    "EXECUTED_PRIMARY_EVIDENCE_ADMISSIBLE_DIRECT_TIME_BASIS_UNRESOLVED"
)
PRIMARY_STATUS = "BLOCKED_NO_EXPLICIT_CSV_TIME_BASIS_OR_HISTORICAL_EFFECTIVE_SCOPE"
BASE_MAIN_SHA = "4a2ca10af4b14194253ba6fc84bca780e2b03d58"

PR122_PROTOCOL_SHA256 = "d3bf061ade81bb1b60f38e98f5fa3c8c21ba5bf6652879f2cc19e151b53aee4a"
PR124_PROTOCOL_SHA256 = "28ec0a0208858ce3258a584bad1361577a0e202e5cbdb8eb9b13cdd47d7455a3"
PR123_RECEIPT_SHA256 = "a3736753862781efc9d8ce6c15aa814185b73ed14fea82c4e8ebaa10a3ab656c"

V2_RUN_ID = 31_974_333_489
V2_ARTIFACT_ID = 9_270_750_452
V2_ARTIFACT_NAME = "pr69-primary-time-basis-evidence-campaign-v2-31974333489"
V2_ARTIFACT_SHA256 = "186188a0cec4e3febc8971c0f69eb1feb7dec6d2f35052ce48d2913c37265a6c"
V2_ARTIFACT_SIZE = 428_972
V2_PACKAGE_SHA256 = "2212663bece44296494a0aff1edbdb1574e940685588f73829ac80f58a6791c5"
V2_PACKAGE_SIZE = 419_840

PR69_SOURCE_FILE_COUNT = 66
PR69_SOURCE_TOTAL_BYTES = 10_006_877
PR69_SOURCE_FIXTURE_COUNT = 21_226
PR69_SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26")
PR69_MODEL_LEAGUE_CODES = (
    "B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1"
)

TARGETS: tuple[dict[str, Any], ...] = (
    {
        "target_id": "NOTES_TXT",
        "url": "https://www.football-data.co.uk/notes.txt",
        "raw_sha256": "6ecd41a98ad2751372817e7e6f1709bfeb433c53dd9aeda330fd926a5471452d",
        "raw_size": 7_686,
        "pair_identical": True,
        "pair_separation_seconds": 317.882937,
    },
    {
        "target_id": "DATA_OVERVIEW",
        "url": "https://www.football-data.co.uk/data.php",
        "raw_sha256": "2dde0990feec3aa626c922f588a16897920061482c0e8b44f0644be91d1fc7ed",
        "raw_size": 45_576,
        "pair_identical": True,
        "pair_separation_seconds": 318.093548,
    },
    {
        "target_id": "HISTORICAL_DOWNLOAD_OVERVIEW",
        "url": "https://www.football-data.co.uk/downloadm.php",
        "raw_sha256": "94922a8099dd04983f72123da2f1afdacffa293032ce27e65eff6f852d7e50af",
        "raw_size": 104_882,
        "pair_identical": True,
        "pair_separation_seconds": 318.213764,
    },
    {
        "target_id": "FIXTURES_OVERVIEW",
        "url": "https://www.football-data.co.uk/matches.php",
        "raw_sha256": "62793b3461420db06c176e1fa6b1b55b0cde46f5846ff73bcd1e5ad89bf0365f",
        "raw_size": 33_148,
        "pair_identical": True,
        "pair_separation_seconds": 318.093185,
    },
)

SEMANTIC_RECORDS: tuple[dict[str, Any], ...] = (
    {
        "record_id": "NOTES_DATE_FIELD_MEANING",
        "target_id": "NOTES_TXT",
        "raw_sha256": TARGETS[0]["raw_sha256"],
        "line": 8,
        "byte_start": 448,
        "byte_end": 476,
        "text": "Date = Match Date (dd/mm/yy)",
        "classification": "ADMISSIBLE_PRIMARY_FIELD_SEMANTIC",
        "establishes_csv_time_basis": False,
        "establishes_historical_effective_scope": False,
    },
    {
        "record_id": "NOTES_TIME_FIELD_MEANING",
        "target_id": "NOTES_TXT",
        "raw_sha256": TARGETS[0]["raw_sha256"],
        "line": 9,
        "byte_start": 478,
        "byte_end": 507,
        "text": "Time = Time of match kick off",
        "classification": "ADMISSIBLE_PRIMARY_FIELD_SEMANTIC",
        "establishes_csv_time_basis": False,
        "establishes_historical_effective_scope": False,
    },
    {
        "record_id": "FIXTURE_DOWNLOAD_CONTAINS_MATCH_DATES_TIMES",
        "target_id": "FIXTURES_OVERVIEW",
        "raw_sha256": TARGETS[3]["raw_sha256"],
        "line": 171,
        "byte_start": 12_699,
        "byte_end": 12_821,
        "text": (
            "Below you will find download links to the latest main leagues fixtures list, "
            "with the match dates, times and betting odds."
        ),
        "classification": "ADMISSIBLE_PRIMARY_FIXTURE_CONTEXT",
        "establishes_csv_time_basis": False,
        "establishes_historical_effective_scope": False,
    },
    {
        "record_id": "FIXTURE_ODDS_COLLECTION_BST_CONTEXT",
        "target_id": "FIXTURES_OVERVIEW",
        "raw_sha256": TARGETS[3]["raw_sha256"],
        "line": 183,
        "byte_start": 13_753,
        "byte_end": 13_774,
        "text": "British Standard Time",
        "classification": "ADMISSIBLE_PRIMARY_SITE_CLOCK_CONTEXT_ONLY",
        "establishes_csv_time_basis": False,
        "establishes_historical_effective_scope": False,
    },
    {
        "record_id": "FIXTURE_UPLOAD_UK_TIME_CONTEXT",
        "target_id": "FIXTURES_OVERVIEW",
        "raw_sha256": TARGETS[3]["raw_sha256"],
        "line": 194,
        "byte_start": 14_268,
        "byte_end": 14_293,
        "text": "Latest fixtures uploaded:",
        "classification": "ADMISSIBLE_PRIMARY_SITE_CLOCK_CONTEXT_ONLY",
        "establishes_csv_time_basis": False,
        "establishes_historical_effective_scope": False,
    },
)

DIRECT_ROUTE = {
    "available": False,
    "explicit_csv_timezone_or_offset_rule_present": False,
    "explicit_dst_transition_rule_present": False,
    "historical_effective_scope_proven": False,
    "all_relevant_pr69_rows_mappable": False,
    "mapped_rows": 0,
    "unresolved_rows": PR69_SOURCE_FIXTURE_COUNT,
    "reason": PRIMARY_STATUS,
}

FORMAL_INVARIANCE_ROUTE = {
    "executed": False,
    "assumptions_proven": False,
    "status": "NOT_REACHED_DIRECT_PRIMARY_SEMANTICS_REMAIN_UNRESOLVED",
}

SAFETY = {
    "pr69_source_local_time_basis_resolved": False,
    "fotmob_source_local_time_semantic_equivalence_qualified": False,
    "pr80_constructor_input_authorized": False,
    "model_training_authorized": False,
    "expected_goals_production_authorized": False,
    "score_matrix_authorized": False,
    "probability_inference_authorized": False,
    "pricing_authorized": False,
    "selection_authorized": False,
    "production_approval_authorized": False,
    "bet_authorized": False,
}

NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_FOTMOB_NATIVE_SUCCESSOR_FEATURE_TIME_BASIS_PROTOCOL_OR_"
    "SEPARATELY_PROVEN_PR69_INVARIANCE_ROUTE"
)


def qualification_receipt() -> dict[str, Any]:
    """Return the deterministic, result-bearing semantic qualification receipt."""
    return {
        "schema_version": SCHEMA_VERSION,
        "qualification_id": QUALIFICATION_ID,
        "qualification_scope": QUALIFICATION_SCOPE,
        "qualification_state": QUALIFICATION_STATE,
        "primary_status": PRIMARY_STATUS,
        "base_main_sha": BASE_MAIN_SHA,
        "lineage": {
            "pr122_protocol_sha256": PR122_PROTOCOL_SHA256,
            "pr124_protocol_sha256": PR124_PROTOCOL_SHA256,
            "pr123_receipt_sha256": PR123_RECEIPT_SHA256,
            "v2_run_id": V2_RUN_ID,
            "v2_artifact_id": V2_ARTIFACT_ID,
            "v2_artifact_name": V2_ARTIFACT_NAME,
            "v2_artifact_sha256": V2_ARTIFACT_SHA256,
            "v2_artifact_size": V2_ARTIFACT_SIZE,
            "v2_package_sha256": V2_PACKAGE_SHA256,
            "v2_package_size": V2_PACKAGE_SIZE,
        },
        "capture_assessment": {
            "successful_slots": 8,
            "required_slots": 8,
            "all_pairs_identical": True,
            "all_pairs_within_frozen_window": True,
            "targets": [dict(item) for item in TARGETS],
        },
        "semantic_records": [dict(item) for item in SEMANTIC_RECORDS],
        "direct_route": dict(DIRECT_ROUTE),
        "formal_invariance_route": dict(FORMAL_INVARIANCE_ROUTE),
        "pr69_scope": {
            "source_file_count": PR69_SOURCE_FILE_COUNT,
            "source_total_bytes": PR69_SOURCE_TOTAL_BYTES,
            "source_fixture_count": PR69_SOURCE_FIXTURE_COUNT,
            "seasons": list(PR69_SEASONS),
            "model_league_codes": list(PR69_MODEL_LEAGUE_CODES),
        },
        "safety": dict(SAFETY),
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
    }


def canonical_receipt_bytes() -> bytes:
    return (
        json.dumps(
            qualification_receipt(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def canonical_receipt_sha256() -> str:
    return hashlib.sha256(canonical_receipt_bytes()).hexdigest()


def validate_qualification() -> None:
    receipt = qualification_receipt()
    targets = receipt["capture_assessment"]["targets"]
    assert len(targets) == 4
    assert receipt["capture_assessment"]["successful_slots"] == 8
    assert all(item["pair_identical"] is True for item in targets)
    assert all(300 <= item["pair_separation_seconds"] <= 3600 for item in targets)
    assert DIRECT_ROUTE["mapped_rows"] + DIRECT_ROUTE["unresolved_rows"] == PR69_SOURCE_FIXTURE_COUNT
    assert DIRECT_ROUTE["unresolved_rows"] == PR69_SOURCE_FIXTURE_COUNT
    assert all(not value for value in SAFETY.values())
    assert all(
        record["establishes_csv_time_basis"] is False
        for record in SEMANTIC_RECORDS
        if record["classification"] != "ADMISSIBLE_PRIMARY_FIELD_SEMANTIC"
        or record["record_id"] == "NOTES_TIME_FIELD_MEANING"
    )
