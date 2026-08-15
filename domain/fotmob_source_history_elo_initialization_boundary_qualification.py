"""Validate the reviewed PR #114 FotMob Elo-initialization qualification receipt.

PR #114 proves only the source-history replay *initialization boundary* defined
by PR #113.  It does not authorize historical rows, a source-history adapter,
model training, probabilities, pricing, selection, production, or BET.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import domain.fotmob_source_history_elo_initialization_boundary_protocol as pr113
import domain.fotmob_source_history_rearrangement_chronology_qualification as pr112

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "fotmob-source-history-elo-initialization-boundary-qualification-v1.json"
)

RECEIPT_SHA256 = "fbbec0b858c3e9630d9f4c7dec630012f57811de52d300db3a11b781a719e110"
RECEIPT_SIZE = 24_428
REPOSITORY_MAIN_ANCHOR = "7b0ed65347020c839802700be547ceb304aeddfd"
PR113_PROTOCOL_BLOB_SHA = "84f9bf695ff2baeb81f053a09c8ae1709b82d75f"
PR113_PROTOCOL_SHA256 = "61f62252c178fb2e87a1f704848dfadb19213a9dede8fd2925b5d938faf0186c"
PR113_PROTOCOL_SIZE = 8_405
PR112_RECEIPT_SHA256 = "58c7a275580cc74489269a66de2836544e78ca232693d5283f1813ee817d3fc0"
PR112_RECEIPT_SIZE = 7_980
PR69_SOURCE_CORPUS_SHA256 = "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0"
PR69_CANONICAL_REPLAY_SHA256 = "b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3"
PR69_CANONICAL_REPLAY_SIZE = 39_952_730
PR69_SOURCE_FILE_COUNT = 66
PR69_SOURCE_TOTAL_BYTES = 10_006_877
PR69_SOURCE_FIXTURE_COUNT = 21_226
FOTMOB_ARTIFACT_ID = 9_249_856_559
FOTMOB_ARTIFACT_SHA256 = "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
FOTMOB_ARTIFACT_SIZE = 61_886_753
FOTMOB_CACHE_SHA256 = "cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6"
FOTMOB_CACHE_SIZE = 61_881_610
TARGET_FAMILY_PROJECTION_SHA256 = "e98715f599fd9495f7a606e0a05a07bdc56781d35ba497522610efdab775c0b9"
TARGET_FAMILY_PROJECTION_SIZE = 6_853_903
QUALIFICATION_STATE = "EXECUTED_PR69_EQUIVALENT_ELO_INITIALIZATION_BOUNDARY_QUALIFIED"
QUALIFIED_STATUS = "QUALIFIED_PR69_EQUIVALENT_EMPTY_1500_INITIALIZATION_BOUNDARY"
RESOLVED_BLOCKER = "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN"
EXPECTED_REMAINING_BLOCKERS = ("BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",)
NEXT_REQUIRED_BOUNDARY = "EXECUTE_REVIEWED_SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_ASSESSMENT"

SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26")
MODEL_LEAGUES = ("B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1")

EXPECTED_FLOORS = {
    "B1": "2020-08-08",
    "D1": "2020-09-18",
    "E0": "2020-09-12",
    "F1": "2020-08-21",
    "G1": "2020-09-11",
    "I1": "2020-09-19",
    "N1": "2020-09-12",
    "P1": "2020-09-18",
    "SC0": "2020-08-01",
    "SP1": "2020-09-12",
    "T1": "2020-09-11",
}

EXPECTED_2020_21_SOURCE_HASHES = {
    "B1": "6e74a3f376c67b18bc40175aaf4d87b553ed8d10335ec48e6c0d805fd0117687",
    "D1": "48ec5d53d2452b6ebdbc07bd78a836d6a4686f99fc020439ee3292e685315e61",
    "E0": "5afe63f69401457b8354eaacee24f9a3e520b3c3af6329564a9783e20d789c62",
    "F1": "124560ab39a1c256eb6ee5ad2dd1eed250c9780d0cbb34525d9abee41fbf7f70",
    "G1": "311c5af3fe0e8b0edc6c7be2667f31927a9086e8f904a82f1097868ba070698a",
    "I1": "c09196fa18877547442807d375317299947abdd6d51a5e0df044cc6026e13f36",
    "N1": "65d532e1ea878954043454422ba2c770d05909691b219f39fcc6e9c4c4037657",
    "P1": "c6bb505a2a2a3f5a71f5d37cbe9f717fb683d706b66170b6b3bef7947a5252cb",
    "SC0": "0456d91665fccef8a7b4cce781b9a56a0df451d43dc1f67f0d623ac90aa26817",
    "SP1": "b4137db923101f464e8403c4973acbfaf7d71724ce93b4336fad580e894d9591",
    "T1": "f50a1ca815964b11f818a3ca35035f57969e5b3b04e267ad508e8b9282920cfd",
}

# code, primaryId, country, floor, pre-floor occurrences, admitted ordinary-FT
# candidates, source team count, first fixture id.
EXPECTED_FAMILY_SUMMARY = (
    ("B1", 40, "BEL", "2020-08-08", 0, 1933, 25, 3360882),
    ("D1", 54, "GER", "2020-09-18", 0, 1835, 25, 3399144),
    ("E0", 47, "ENG", "2020-09-12", 0, 2280, 28, 3411352),
    ("F1", 53, "FRA", "2020-08-21", 0, 2056, 27, 3361606),
    ("G1", 135, "GRE", "2020-09-11", 0, 1431, 19, 3433968),
    ("I1", 55, "ITA", "2020-09-19", 10, 2280, 30, 3428767),
    ("N1", 57, "NED", "2020-09-12", 0, 1865, 26, 3377416),
    ("P1", 61, "POR", "2020-09-18", 0, 1846, 27, 3421632),
    ("SC0", 64, "SCO", "2020-08-01", 0, 1380, 15, 3358641),
    ("SP1", 87, "ESP", "2020-09-12", 0, 2280, 28, 3424041),
    ("T1", 71, "TUR", "2020-09-11", 0, 2140, 32, 3419278),
)

EXPECTED_CHECKS = {
    "all_eleven_reference_floors_have_reviewed_result_evidence": True,
    "first_seen_team_seed_count": 282,
    "malformed_fixture_identity_count": 0,
    "out_of_universe_state_update_count": 0,
    "preboundary_fixture_date_occurrence_count": 10,
    "preboundary_state_leakage_count": 0,
    "request_date_count": 2205,
    "response_file_count": 4410,
    "reused_team_state_observation_count": 42370,
    "reviewed_ordinary_ft_candidate_count_on_or_after_floor": 21326,
    "same_date_pair_cardinality_mismatch_count": 0,
    "same_date_pair_relevant_field_conflict_count": 0,
    "season_reset_count": 0,
    "special_or_nonordinary_state_update_count": 0,
    "special_state_occurrence_count_on_or_after_floor": 304,
    "static_fixture_identity_drift_count": 0,
    "target_family_fixture_date_pair_count": 21640,
    "target_family_projection_sha256": TARGET_FAMILY_PROJECTION_SHA256,
    "target_family_projection_size_bytes": TARGET_FAMILY_PROJECTION_SIZE,
    "target_family_raw_capture_row_count": 43280,
    "team_identity_violation_count": 0,
}


class FotMobSourceHistoryEloInitializationBoundaryQualificationError(ValueError):
    """Raised when the exact PR #114 receipt no longer revalidates."""


def _error(message: str) -> FotMobSourceHistoryEloInitializationBoundaryQualificationError:
    return FotMobSourceHistoryEloInitializationBoundaryQualificationError(message)


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("PR114 receipt serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _load_exact_receipt() -> dict[str, Any]:
    raw = RECEIPT_PATH.read_bytes()
    if len(raw) != RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise _error("PR114 qualification receipt identity changed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("PR114 receipt is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or raw != _canonical(value):
        raise _error("PR114 receipt is not exact canonical JSON")
    return value


def _verify_upstream() -> None:
    protocol = pr113.build_fotmob_source_history_elo_initialization_boundary_protocol()
    protocol_raw = pr113.canonical_fotmob_source_history_elo_initialization_boundary_protocol_bytes(
        protocol
    )
    if (len(protocol_raw), hashlib.sha256(protocol_raw).hexdigest()) != (
        PR113_PROTOCOL_SIZE,
        PR113_PROTOCOL_SHA256,
    ):
        raise _error("PR113 protocol identity changed")
    if pr113.NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_ELO_INITIALIZATION_BOUNDARY_QUALIFICATION"
    ):
        raise _error("PR113 execution boundary changed")

    pr112_raw = pr112.canonical_fotmob_source_history_rearrangement_chronology_qualification_receipt_bytes()
    pr112_receipt = pr112.load_fotmob_source_history_rearrangement_chronology_qualification_receipt()
    if (len(pr112_raw), hashlib.sha256(pr112_raw).hexdigest()) != (
        PR112_RECEIPT_SIZE,
        PR112_RECEIPT_SHA256,
    ):
        raise _error("PR112 receipt identity changed")
    if pr112_receipt.get("rearrangement_chronology_qualified") is not True:
        raise _error("PR112 chronology qualification changed")
    if pr112_receipt.get("remaining_blockers") != [
        "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN",
        "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",
    ]:
        raise _error("PR112 blocker ancestry changed")


def _validate_pr69(receipt: dict[str, Any]) -> None:
    upstream = receipt.get("upstream")
    if upstream != {
        "pr112_receipt_sha256": PR112_RECEIPT_SHA256,
        "pr112_receipt_size_bytes": PR112_RECEIPT_SIZE,
        "pr69_canonical_replay_sha256": PR69_CANONICAL_REPLAY_SHA256,
        "pr69_canonical_replay_size_bytes": PR69_CANONICAL_REPLAY_SIZE,
        "pr69_source_corpus_sha256": PR69_SOURCE_CORPUS_SHA256,
    }:
        raise _error("PR69/PR112 upstream ancestry changed")

    rebuild = receipt.get("pr69_rebuild")
    if not isinstance(rebuild, dict):
        raise _error("PR69 rebuild evidence missing")
    if rebuild.get("checks") != {
        "canonical_replay_sha256": PR69_CANONICAL_REPLAY_SHA256,
        "canonical_replay_size_bytes": PR69_CANONICAL_REPLAY_SIZE,
        "fixture_count": PR69_SOURCE_FIXTURE_COUNT,
        "source_corpus_sha256": PR69_SOURCE_CORPUS_SHA256,
        "source_file_count": PR69_SOURCE_FILE_COUNT,
        "source_total_bytes": PR69_SOURCE_TOTAL_BYTES,
    }:
        raise _error("exact PR69 rebuild checks changed")

    source_hashes = rebuild.get("source_file_sha256")
    expected_keys = {f"{season}/{league}" for season in SEASONS for league in MODEL_LEAGUES}
    if not isinstance(source_hashes, dict) or set(source_hashes) != expected_keys:
        raise _error("PR69 exact 66-file membership changed")
    for league, expected_hash in EXPECTED_2020_21_SOURCE_HASHES.items():
        if source_hashes.get(f"2020-21/{league}") != expected_hash:
            raise _error(f"{league} 2020-21 exact source identity changed")

    witness = rebuild.get("reference_floor_witness")
    if not isinstance(witness, dict) or set(witness) != set(EXPECTED_FLOORS):
        raise _error("reference-floor witness family set changed")
    for league, floor in EXPECTED_FLOORS.items():
        row = witness[league]
        if not isinstance(row, dict):
            raise _error(f"{league} reference-floor witness missing")
        if row.get("reference_floor_source_local_date") != floor:
            raise _error(f"{league} reference floor changed")
        if row.get("source_file_sha256") != EXPECTED_2020_21_SOURCE_HASHES[league]:
            raise _error(f"{league} reference-floor source file changed")
        if not str(row.get("source_fixture_identifier", "")).startswith("football_data_uk_csv:"):
            raise _error(f"{league} reference-floor source fixture identity changed")


def _validate_fotmob(receipt: dict[str, Any]) -> None:
    source = receipt.get("source_evidence")
    if source != {
        "football_data_source_file_count": PR69_SOURCE_FILE_COUNT,
        "football_data_source_fixture_count": PR69_SOURCE_FIXTURE_COUNT,
        "football_data_source_total_bytes": PR69_SOURCE_TOTAL_BYTES,
        "fotmob_artifact_id": FOTMOB_ARTIFACT_ID,
        "fotmob_artifact_name": "fotmob-ordinary-ft-source-history-campaign-31887523012",
        "fotmob_artifact_sha256": FOTMOB_ARTIFACT_SHA256,
        "fotmob_artifact_size_bytes": FOTMOB_ARTIFACT_SIZE,
        "fotmob_research_cache_tar_gz_sha256": FOTMOB_CACHE_SHA256,
        "fotmob_research_cache_tar_gz_size_bytes": FOTMOB_CACHE_SIZE,
    }:
        raise _error("source-evidence identity changed")

    assessment = receipt.get("fotmob_boundary_assessment")
    if not isinstance(assessment, dict) or assessment.get("checks") != EXPECTED_CHECKS:
        raise _error("FotMob initialization-boundary checks changed")
    checks = assessment["checks"]
    # The exact accounting leaves no unreviewed residual source state at/after
    # the floor: 10 pre-floor + 21,326 ordinary + 304 special = 21,640 pairs.
    if (
        checks["preboundary_fixture_date_occurrence_count"]
        + checks["reviewed_ordinary_ft_candidate_count_on_or_after_floor"]
        + checks["special_state_occurrence_count_on_or_after_floor"]
        != checks["target_family_fixture_date_pair_count"]
    ):
        raise _error("target-family state accounting no longer closes exactly")

    families = assessment.get("families")
    if not isinstance(families, list) or len(families) != 11:
        raise _error("qualification must contain exactly eleven family records")
    observed = []
    preboundary_families = []
    for row in families:
        if not isinstance(row, dict):
            raise _error("family record must be an object")
        first = row.get("first_reviewed_ordinary_ft_candidate")
        if not isinstance(first, dict):
            raise _error("family first admitted candidate is missing")
        observed.append(
            (
                row.get("model_league_code"),
                row.get("fotmob_primary_id"),
                row.get("expected_country_code"),
                row.get("pr69_reference_floor_source_local_date"),
                row.get("fotmob_preboundary_fixture_date_occurrence_count"),
                row.get("reviewed_ordinary_ft_candidate_count_on_or_after_floor"),
                row.get("source_scoped_team_id_count_in_candidate_stream"),
                first.get("fixture_id"),
            )
        )
        if row.get("fotmob_preboundary_fixture_date_occurrence_count"):
            preboundary_families.append(row.get("model_league_code"))
        if row.get("initial_rating") != 1500 or row.get("initial_matches") != 0:
            raise _error("first-seen team seed semantics changed")
        for key in (
            "preboundary_rows_used_to_seed_or_update_state",
            "special_or_nonordinary_rows_used_to_seed_or_update_state",
            "season_reset_count",
        ):
            if row.get(key) != 0:
                raise _error(f"{row.get('model_league_code')} {key} must remain zero")
        if row.get("qualification_status") != QUALIFIED_STATUS:
            raise _error("family qualification status changed")
    if tuple(observed) != EXPECTED_FAMILY_SUMMARY:
        raise _error("family-level initialization evidence changed")
    if preboundary_families != ["I1"]:
        raise _error("only I1 may retain the observed pre-floor FotMob evidence")


def _validate_receipt(receipt: dict[str, Any]) -> None:
    if receipt.get("schema_version") != 1:
        raise _error("receipt schema changed")
    if receipt.get("dataset_name") != (
        "athena-fotmob-source-history-elo-initialization-boundary-qualification-v1"
    ):
        raise _error("receipt dataset changed")
    if receipt.get("scope") != (
        "IMMUTABLE_PR69_EQUIVALENT_ELO_INITIALIZATION_BOUNDARY_QUALIFICATION_RECEIPT_ONLY"
    ):
        raise _error("receipt scope changed")
    if receipt.get("repository_main_anchor") != REPOSITORY_MAIN_ANCHOR:
        raise _error("receipt main anchor changed")
    if receipt.get("protocol") != {
        "canonical_sha256": PR113_PROTOCOL_SHA256,
        "canonical_size_bytes": PR113_PROTOCOL_SIZE,
        "protocol_id": pr113.PROTOCOL_ID,
    }:
        raise _error("PR113 protocol ancestry changed")
    if receipt.get("qualification_state") != QUALIFICATION_STATE:
        raise _error("qualification state changed")
    if receipt.get("qualification_status") != QUALIFIED_STATUS:
        raise _error("qualification status changed")
    if receipt.get("reference_floor_granularity") != (
        "PR69_SOURCE_LOCAL_CALENDAR_DATE_VS_FOTMOB_REQUEST_DATE_ONLY"
    ):
        raise _error("reference-floor granularity changed")
    if receipt.get("initialization_boundary_execution_performed") is not True:
        raise _error("initialization execution must remain performed")
    if receipt.get("initialization_boundary_qualified") is not True:
        raise _error("initialization qualification must remain proven")
    if receipt.get("resolved_blocker") != RESOLVED_BLOCKER:
        raise _error("resolved blocker changed")
    if tuple(receipt.get("remaining_blockers", ())) != EXPECTED_REMAINING_BLOCKERS:
        raise _error("remaining blocker set changed")
    if receipt.get("next_required_boundary") != NEXT_REQUIRED_BOUNDARY:
        raise _error("next reviewed boundary changed")

    for key in (
        "source_history_mutation_performed",
        "ordinary_ft_history_rows_authorized",
        "historical_coverage_proven",
        "source_capability_registry_mutation_performed",
        "competition_registry_mutation_performed",
        "cross_source_fixture_identity_inferred",
        "cross_source_team_identity_inferred",
        "cross_source_numeric_elo_equivalence_claimed",
    ):
        if receipt.get(key) is not False:
            raise _error(f"{key} must remain exact False")
    safety = receipt.get("safety")
    if not isinstance(safety, dict) or not safety or any(value is not False for value in safety.values()):
        raise _error("all PR114 downstream safety values must remain exact False")

    _validate_pr69(receipt)
    _validate_fotmob(receipt)


def load_fotmob_source_history_elo_initialization_boundary_qualification_receipt() -> dict[str, Any]:
    """Load and fully validate the exact durable PR #114 receipt."""
    _verify_upstream()
    receipt = _load_exact_receipt()
    _validate_receipt(receipt)
    return receipt


def canonical_fotmob_source_history_elo_initialization_boundary_qualification_receipt_bytes() -> bytes:
    """Return the exact canonical checked-in PR #114 receipt bytes."""
    receipt = load_fotmob_source_history_elo_initialization_boundary_qualification_receipt()
    raw = _canonical(receipt)
    if len(raw) != RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise _error("PR114 canonical receipt identity changed")
    return raw


__all__ = [
    "EXPECTED_CHECKS",
    "EXPECTED_FAMILY_SUMMARY",
    "EXPECTED_FLOORS",
    "NEXT_REQUIRED_BOUNDARY",
    "QUALIFICATION_STATE",
    "QUALIFIED_STATUS",
    "RECEIPT_SHA256",
    "RECEIPT_SIZE",
    "RESOLVED_BLOCKER",
    "FotMobSourceHistoryEloInitializationBoundaryQualificationError",
    "canonical_fotmob_source_history_elo_initialization_boundary_qualification_receipt_bytes",
    "load_fotmob_source_history_elo_initialization_boundary_qualification_receipt",
]
