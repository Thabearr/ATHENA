"""Evidence checks for the reviewed FotMob primaryId mapping qualification."""

from __future__ import annotations

import hashlib
import json

import domain.fotmob_primary_id_competition_mapping_qualification as qualification
import domain.fotmob_primary_id_competition_mapping_semantics_protocol as protocol


EXPECTED_CANDIDATES = {
    "B1": (40, "BEL"),
    "D1": (54, "GER"),
    "E0": (47, "ENG"),
    "F1": (53, "FRA"),
    "G1": (135, "GRE"),
    "I1": (55, "ITA"),
    "N1": (57, "NED"),
    "P1": (61, "POR"),
    "SC0": (64, "SCO"),
    "SP1": (87, "ESP"),
    "T1": (71, "TUR"),
}


def _receipt() -> dict[str, object]:
    return qualification.load_fotmob_primary_id_competition_mapping_qualification_receipt()


def test_receipt_is_exact_canonical_frozen_evidence() -> None:
    receipt = _receipt()
    raw = qualification.canonical_fotmob_primary_id_competition_mapping_qualification_receipt_bytes()

    assert len(raw) == qualification.RECEIPT_SIZE == 13_681
    assert hashlib.sha256(raw).hexdigest() == qualification.RECEIPT_SHA256
    assert qualification.RECEIPT_SHA256 == (
        "fdb55feef9585fe0aa2668ddb9ac9a6eb8e63ac8870c06cdb7917d1f996e7bc9"
    )
    assert raw == (
        json.dumps(
            receipt,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    assert receipt["schema_version"] == 1
    assert receipt["dataset_name"] == qualification.DATASET_NAME
    assert receipt["scope"] == qualification.SCOPE
    assert receipt["repository_main_anchor"] == (
        "72cfd3aea494b85188e625328f8f49d379dbdf23"
    )


def test_qualification_is_bound_to_exact_pr107_protocol_and_preserved_pr105_artifact() -> None:
    receipt = _receipt()
    source = receipt["source_evidence"]

    assert receipt["protocol"] == {
        "protocol_id": protocol.PROTOCOL_ID,
        "canonical_sha256": (
            "6d3e6083325853b481fe2a5ad928d67c5fe7cb46d25f5c33024146855c6e725e"
        ),
        "canonical_size_bytes": 7_370,
        "blob_sha": "649fe1b28693ac283e0fb0f93f1554c12b77f19e",
    }
    assert source["artifact_id"] == 9_249_856_559
    assert source["artifact_sha256"] == (
        "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
    )
    assert source["artifact_size_bytes"] == 61_886_753
    assert source["research_cache_tar_gz_sha256"] == (
        "cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6"
    )
    assert source["research_cache_tar_gz_size_bytes"] == 61_881_610
    assert source["pr105_receipt_sha256"] == (
        "a8c5a704e06853d6debfc029653132ca201b98c1fc8a32b3e3095db18f8e1363"
    )
    assert source["pr105_receipt_size_bytes"] == 11_995
    assert source["request_date_count"] == 2_205
    assert source["successful_capture_count"] == 4_410
    assert source["response_file_count"] == 4_410


def test_full_mapping_evidence_projection_is_frozen() -> None:
    source = _receipt()["source_evidence"]

    assert source["target_league_object_observation_count"] == 15_088
    assert source["mapping_evidence_projection_sha256"] == (
        "05a468ad53d3feea1b7072bafea1c0b91e6e1ceeccdf0f1edfe031359a369d3a"
    )
    assert source["mapping_evidence_projection_size_bytes"] == 3_361_516


def test_all_eleven_initial_primary_id_families_qualify_exactly() -> None:
    receipt = _receipt()
    records = {item["model_league_code"]: item for item in receipt["records"]}

    assert set(records) == set(EXPECTED_CANDIDATES)
    assert receipt["qualification_state"] == (
        "EXECUTED_INITIAL_ELEVEN_PRIMARY_ID_COMPETITION_MAPPING_QUALIFIED"
    )
    assert receipt["mapping_semantics"] == (
        "FOTMOB_PRIMARY_ID_IS_SOURCE_SCOPED_COMPETITION_FAMILY_IDENTITY"
    )

    for code, (primary_id, country) in EXPECTED_CANDIDATES.items():
        item = records[code]
        assert item["fotmob_primary_id"] == primary_id
        assert item["expected_country_code"] == country
        assert item["observed_country_codes"] == [country]
        assert item["competition_class"] == "DOMESTIC_LEAGUE"
        assert item["qualification_status"] == (
            "QUALIFIED_SOURCE_SCOPED_COMPETITION_FAMILY_IDENTITY"
        )
        assert item["observed_wrapper_league_ids"]
        assert item["observed_match_league_ids"] == item["observed_wrapper_league_ids"]
        assert all(
            parent_id == primary_id for parent_id in item["observed_parent_league_ids"]
        )
        assert item["country_lineage_exact"] is True
        assert item["wrapper_count_matches_pr105"] is True
        assert item["name_variant_count_matches_pr105"] is True
        assert item["all_match_league_ids_accounted_by_wrapper_ids"] is True
        assert item["all_parent_league_ids_absent_or_primary_id"] is True


def test_wrapper_and_name_drift_is_explicitly_accounted_for_not_hidden() -> None:
    records = {item["model_league_code"]: item for item in _receipt()["records"]}

    assert len(records["B1"]["observed_wrapper_league_ids"]) == 25
    assert len(records["B1"]["observed_name_variants"]) == 11
    assert records["B1"]["observed_parent_league_ids"] == [40]
    assert "First Division A" in records["B1"]["observed_name_variants"]
    assert "Belgian Pro League" in records["B1"]["observed_name_variants"]

    assert len(records["G1"]["observed_wrapper_league_ids"]) == 20
    assert len(records["G1"]["observed_name_variants"]) == 4
    assert records["G1"]["observed_parent_league_ids"] == [135]

    assert len(records["N1"]["observed_wrapper_league_ids"]) == 13
    assert len(records["N1"]["observed_name_variants"]) == 3
    assert records["N1"]["observed_parent_league_ids"] == [57]
    assert "Eredivisie ECL\xa0Playoff" in records["N1"]["observed_name_variants"]

    assert len(records["SC0"]["observed_wrapper_league_ids"]) == 19
    assert len(records["SC0"]["observed_name_variants"]) == 3
    assert records["SC0"]["observed_parent_league_ids"] == [64]


def test_direct_root_id_families_remain_stable_without_wrapper_promotion_logic() -> None:
    records = {item["model_league_code"]: item for item in _receipt()["records"]}

    for code, primary_id in (
        ("D1", 54),
        ("E0", 47),
        ("F1", 53),
        ("I1", 55),
        ("P1", 61),
        ("SP1", 87),
        ("T1", 71),
    ):
        assert records[code]["observed_wrapper_league_ids"] == [primary_id]
        assert records[code]["observed_match_league_ids"] == [primary_id]
        assert records[code]["observed_parent_league_ids"] == []


def test_identity_conflict_checks_are_zero_and_mapping_gate_is_the_only_promoted_fact() -> None:
    receipt = _receipt()
    checks = receipt["checks"]

    assert checks["initial_candidate_count"] == 11
    assert checks["qualified_mapping_count"] == 11
    assert checks["blocked_mapping_count"] == 0
    assert checks["all_initial_candidates_observed"] is True
    assert checks["all_expected_country_lineage_exact"] is True
    assert checks["all_wrapper_id_counts_match_pr105"] is True
    assert checks["all_name_variant_counts_match_pr105"] is True
    assert checks["all_observed_match_league_ids_accounted_by_wrapper_ids"] is True
    assert checks["all_parent_league_ids_absent_or_equal_primary_id"] is True

    for key in (
        "wrapper_primary_id_conflict_count",
        "parent_primary_id_conflict_count",
        "match_wrapper_identity_conflict_count",
        "country_conflict_count",
        "competition_class_conflict_count",
        "primary_id_collision_count",
    ):
        assert checks[key] == 0

    assert receipt["mapping_qualification_proven"] is True
    assert receipt["competition_registry_mutation_performed"] is False
    assert receipt["source_capability_registry_mutation_performed"] is False
    assert receipt["historical_coverage_proven"] is False


def test_broader_competition_universe_is_not_accidentally_promoted() -> None:
    receipt = _receipt()

    assert receipt["safety"]["expanded_competition_universe_authorized"] is False
    assert receipt["safety"]["competition_registry_mutation_authorized"] is False
    assert all(value is False for value in receipt["safety"].values())

    prereg = protocol.build_fotmob_primary_id_competition_mapping_semantics_protocol()
    assert "CONTINENTAL_CLUB" in prereg.supported_competition_classes
    assert "DOMESTIC_CUP" in prereg.supported_competition_classes
    assert "INTERNATIONAL_TOURNAMENT" in prereg.supported_competition_classes
    assert len(prereg.initial_mapping_candidates) == 11


def test_remaining_history_blockers_stay_fail_closed_after_mapping_qualification() -> None:
    receipt = _receipt()

    assert receipt["remaining_blockers"] == [
        "BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW",
        "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT",
        "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN",
        "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",
    ]
    assert receipt["next_required_boundary"] == (
        "PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_SPECIAL_RESULT_SEMANTICS_PROTOCOL"
    )
    assert receipt["historical_coverage_proven"] is False
    assert receipt["safety"]["source_history_adapter_approved"] is False
    assert receipt["safety"]["source_history_completeness_proven"] is False
    assert receipt["safety"]["model_training_authorized"] is False
    assert receipt["safety"]["pricing_authorized"] is False
    assert receipt["safety"]["selection_authorized"] is False
    assert receipt["safety"]["bet_authorized"] is False
