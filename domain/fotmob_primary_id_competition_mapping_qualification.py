"""Validate the reviewed FotMob primaryId competition-mapping qualification receipt.

PR #108 qualifies only the source-scoped competition-family identity semantics
pre-registered by PR #107 against the preserved PR #105 campaign artifact.
It does not mutate competition/source registries, prove historical coverage, or
authorize model, calibration, pricing, selection, production, or betting use.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import domain.fotmob_primary_id_competition_mapping_semantics_protocol as pr107


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "fotmob-primary-id-competition-mapping-qualification-v1.json"
)
PR105_RECEIPT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "fotmob-ordinary-ft-source-history-campaign-completeness-receipt-v1.json"
)

REPOSITORY_MAIN_ANCHOR = "72cfd3aea494b85188e625328f8f49d379dbdf23"
PR107_PROTOCOL_BLOB_SHA = "649fe1b28693ac283e0fb0f93f1554c12b77f19e"
PR107_PROTOCOL_SHA256 = "6d3e6083325853b481fe2a5ad928d67c5fe7cb46d25f5c33024146855c6e725e"
PR107_PROTOCOL_SIZE = 7_370
PR105_RECEIPT_SHA256 = "a8c5a704e06853d6debfc029653132ca201b98c1fc8a32b3e3095db18f8e1363"
PR105_RECEIPT_SIZE = 11_995

RECEIPT_SHA256 = "fdb55feef9585fe0aa2668ddb9ac9a6eb8e63ac8870c06cdb7917d1f996e7bc9"
RECEIPT_SIZE = 13_681
MAPPING_EVIDENCE_PROJECTION_SHA256 = (
    "05a468ad53d3feea1b7072bafea1c0b91e6e1ceeccdf0f1edfe031359a369d3a"
)
MAPPING_EVIDENCE_PROJECTION_SIZE = 3_361_516

DATASET_NAME = "athena-fotmob-primary-id-competition-mapping-qualification-v1"
SCOPE = "IMMUTABLE_PRIMARY_ID_COMPETITION_MAPPING_QUALIFICATION_RECEIPT_ONLY"
QUALIFICATION_STATE = (
    "EXECUTED_INITIAL_ELEVEN_PRIMARY_ID_COMPETITION_MAPPING_QUALIFIED"
)
MAPPING_SEMANTICS = "FOTMOB_PRIMARY_ID_IS_SOURCE_SCOPED_COMPETITION_FAMILY_IDENTITY"
QUALIFIED_STATUS = "QUALIFIED_SOURCE_SCOPED_COMPETITION_FAMILY_IDENTITY"
NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_SPECIAL_RESULT_SEMANTICS_PROTOCOL"
)

EXPECTED_REMAINING_BLOCKERS = (
    "BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW",
    "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT",
    "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN",
    "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",
)


class FotMobPrimaryIdCompetitionMappingQualificationError(ValueError):
    """Raised when the frozen PR #108 qualification receipt cannot be reproduced."""


def _error(message: str) -> FotMobPrimaryIdCompetitionMappingQualificationError:
    return FotMobPrimaryIdCompetitionMappingQualificationError(message)


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
        raise _error("competition-mapping qualification serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _load_exact_json(path: Path, *, expected_sha256: str, expected_size: int) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) != expected_size:
        raise _error(f"{path.name} size changed")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise _error(f"{path.name} SHA-256 changed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(f"{path.name} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise _error(f"{path.name} root must be an object")
    if raw != _canonical(value):
        raise _error(f"{path.name} is not canonical JSON")
    return value


def _verify_upstream_protocol() -> pr107.FotMobPrimaryIdCompetitionMappingSemanticsProtocol:
    protocol = pr107.build_fotmob_primary_id_competition_mapping_semantics_protocol()
    raw = pr107.canonical_fotmob_primary_id_competition_mapping_semantics_protocol_bytes(
        protocol
    )
    if len(raw) != PR107_PROTOCOL_SIZE:
        raise _error("PR107 protocol size changed")
    if hashlib.sha256(raw).hexdigest() != PR107_PROTOCOL_SHA256:
        raise _error("PR107 protocol SHA-256 changed")
    if pr107.PROTOCOL_SHA256 != PR107_PROTOCOL_SHA256:
        raise _error("PR107 exported protocol SHA-256 changed")
    if pr107.PROTOCOL_SIZE != PR107_PROTOCOL_SIZE:
        raise _error("PR107 exported protocol size changed")
    if protocol.next_required_boundary != (
        "QUALIFY_REVIEWED_FOTMOB_PRIMARY_ID_COMPETITION_MAPPING_SEMANTICS_"
        "AGAINST_PRESERVED_CAMPAIGN_EVIDENCE"
    ):
        raise _error("PR107 qualification boundary changed")
    return protocol


def _verify_pr105_receipt() -> dict[str, Any]:
    receipt = _load_exact_json(
        PR105_RECEIPT_PATH,
        expected_sha256=PR105_RECEIPT_SHA256,
        expected_size=PR105_RECEIPT_SIZE,
    )
    if receipt.get("primary_status") != "BLOCKED_LEAGUE_MAPPING_UNPROVEN":
        raise _error("PR105 mapping blocker changed")
    if receipt.get("historical_coverage_proven") is not False:
        raise _error("PR105 historical coverage premise changed")
    mapping = receipt.get("league_mapping_evidence")
    if not isinstance(mapping, dict) or mapping.get("mapping_proven") is not False:
        raise _error("PR105 mapping evidence must remain discovery-only")
    if receipt.get("next_required_boundary") != (
        "PRE_REGISTER_REVIEWED_FOTMOB_PRIMARY_ID_COMPETITION_MAPPING_SEMANTICS_PROTOCOL"
    ):
        raise _error("PR105 next reviewed boundary changed")
    return receipt


def _expected_candidates(
    protocol: pr107.FotMobPrimaryIdCompetitionMappingSemanticsProtocol,
) -> dict[str, tuple[int, str, str]]:
    return {
        item.model_league_code: (
            item.fotmob_primary_id,
            item.expected_country_code,
            item.competition_class,
        )
        for item in protocol.initial_mapping_candidates
    }


def _validate_records(
    receipt: dict[str, Any],
    protocol: pr107.FotMobPrimaryIdCompetitionMappingSemanticsProtocol,
    pr105_receipt: dict[str, Any],
) -> None:
    records = receipt.get("records")
    if not isinstance(records, list) or len(records) != 11:
        raise _error("qualification receipt must contain exactly eleven records")
    if any(not isinstance(item, dict) for item in records):
        raise _error("qualification records must be objects")

    expected = _expected_candidates(protocol)
    actual = {
        item.get("model_league_code"): (
            item.get("fotmob_primary_id"),
            item.get("expected_country_code"),
            item.get("competition_class"),
        )
        for item in records
    }
    if actual != expected:
        raise _error("qualification candidate identity differs from PR107 proof set")

    pr105_mapping = pr105_receipt.get("league_mapping_evidence")
    if not isinstance(pr105_mapping, dict):
        raise _error("PR105 mapping evidence missing")
    pr105_records_raw = pr105_mapping.get("records")
    if not isinstance(pr105_records_raw, list):
        raise _error("PR105 mapping records missing")
    pr105_records = {
        item["model_league_code"]: item
        for item in pr105_records_raw
        if isinstance(item, dict) and isinstance(item.get("model_league_code"), str)
    }
    if set(pr105_records) != set(expected):
        raise _error("PR105 mapping record set changed")

    for item in records:
        code = item["model_league_code"]
        primary_id, country, competition_class = expected[code]
        upstream = pr105_records[code]

        if item.get("fotmob_primary_id") != primary_id:
            raise _error(f"{code} primaryId changed")
        if item.get("expected_country_code") != country:
            raise _error(f"{code} expected country changed")
        if item.get("competition_class") != competition_class:
            raise _error(f"{code} competition class changed")
        if item.get("observed_country_codes") != [country]:
            raise _error(f"{code} country lineage is not exact")

        wrappers = item.get("observed_wrapper_league_ids")
        names = item.get("observed_name_variants")
        match_wrappers = item.get("observed_match_league_ids")
        parent_ids = item.get("observed_parent_league_ids")
        if (
            not isinstance(wrappers, list)
            or not wrappers
            or any(type(value) is not int or value <= 0 for value in wrappers)
            or wrappers != sorted(set(wrappers))
        ):
            raise _error(f"{code} wrapper league IDs are not exact sorted unique integers")
        if (
            not isinstance(match_wrappers, list)
            or match_wrappers != wrappers
        ):
            raise _error(f"{code} match league IDs do not account for every wrapper")
        if (
            not isinstance(names, list)
            or not names
            or any(type(value) is not str or not value for value in names)
            or names != sorted(set(names))
        ):
            raise _error(f"{code} name variants are not exact sorted unique text")
        if (
            not isinstance(parent_ids, list)
            or parent_ids != sorted(set(parent_ids))
            or any(value != primary_id for value in parent_ids)
        ):
            raise _error(f"{code} parentLeagueId lineage conflicts with primaryId")

        if len(wrappers) != upstream.get("observed_wrapper_league_id_count"):
            raise _error(f"{code} wrapper count differs from PR105 evidence")
        if len(names) != upstream.get("observed_name_variant_count"):
            raise _error(f"{code} name variant count differs from PR105 evidence")
        for key in (
            "unique_fixture_ids",
            "qualified_ordinary_ft_fixture_ids",
            "blocked_nonordinary_finished_fixture_ids",
            "unresolved_nonresult_fixture_ids",
        ):
            if item.get(key) != upstream.get(key):
                raise _error(f"{code} {key} differs from PR105 evidence")

        for key in (
            "wrapper_count_matches_pr105",
            "name_variant_count_matches_pr105",
            "country_lineage_exact",
            "all_match_league_ids_accounted_by_wrapper_ids",
            "all_parent_league_ids_absent_or_primary_id",
        ):
            if item.get(key) is not True:
                raise _error(f"{code} {key} must remain exact True")
        if item.get("qualification_status") != QUALIFIED_STATUS:
            raise _error(f"{code} qualification status changed")


def _validate_receipt(
    receipt: dict[str, Any],
    protocol: pr107.FotMobPrimaryIdCompetitionMappingSemanticsProtocol,
    pr105_receipt: dict[str, Any],
) -> None:
    if receipt.get("schema_version") != 1:
        raise _error("qualification receipt schema version changed")
    if receipt.get("dataset_name") != DATASET_NAME:
        raise _error("qualification receipt dataset name changed")
    if receipt.get("scope") != SCOPE:
        raise _error("qualification receipt scope changed")
    if receipt.get("repository_main_anchor") != REPOSITORY_MAIN_ANCHOR:
        raise _error("qualification receipt main anchor changed")
    if receipt.get("qualification_state") != QUALIFICATION_STATE:
        raise _error("qualification state changed")
    if receipt.get("mapping_semantics") != MAPPING_SEMANTICS:
        raise _error("mapping semantics changed")

    protocol_receipt = receipt.get("protocol")
    if protocol_receipt != {
        "protocol_id": pr107.PROTOCOL_ID,
        "canonical_sha256": PR107_PROTOCOL_SHA256,
        "canonical_size_bytes": PR107_PROTOCOL_SIZE,
        "blob_sha": PR107_PROTOCOL_BLOB_SHA,
    }:
        raise _error("qualification receipt protocol ancestry changed")

    source_evidence = receipt.get("source_evidence")
    if not isinstance(source_evidence, dict):
        raise _error("source evidence is missing")
    pr105_artifact = pr105_receipt.get("artifact")
    campaign = pr105_receipt.get("campaign")
    if not isinstance(pr105_artifact, dict) or not isinstance(campaign, dict):
        raise _error("PR105 source evidence is incomplete")
    expected_source_fields = {
        "artifact_id": pr105_artifact.get("artifact_id"),
        "artifact_name": pr105_artifact.get("artifact_name"),
        "artifact_sha256": pr105_artifact.get("artifact_sha256"),
        "artifact_size_bytes": pr105_artifact.get("artifact_size_bytes"),
        "research_cache_tar_gz_sha256": pr105_artifact.get("research_cache_tar_gz_sha256"),
        "research_cache_tar_gz_size_bytes": pr105_artifact.get("research_cache_tar_gz_size_bytes"),
        "pr105_receipt_sha256": PR105_RECEIPT_SHA256,
        "pr105_receipt_size_bytes": PR105_RECEIPT_SIZE,
        "request_date_count": campaign.get("required_date_count"),
        "successful_capture_count": campaign.get("successful_slot_count"),
        "response_file_count": campaign.get("response_file_count"),
        "target_league_object_observation_count": 15_088,
        "mapping_evidence_projection_sha256": MAPPING_EVIDENCE_PROJECTION_SHA256,
        "mapping_evidence_projection_size_bytes": MAPPING_EVIDENCE_PROJECTION_SIZE,
    }
    if source_evidence != expected_source_fields:
        raise _error("qualification source evidence ancestry changed")

    _validate_records(receipt, protocol, pr105_receipt)

    checks = receipt.get("checks")
    if checks != {
        "initial_candidate_count": 11,
        "qualified_mapping_count": 11,
        "blocked_mapping_count": 0,
        "all_initial_candidates_observed": True,
        "all_expected_country_lineage_exact": True,
        "all_wrapper_id_counts_match_pr105": True,
        "all_name_variant_counts_match_pr105": True,
        "all_observed_match_league_ids_accounted_by_wrapper_ids": True,
        "all_parent_league_ids_absent_or_equal_primary_id": True,
        "wrapper_primary_id_conflict_count": 0,
        "parent_primary_id_conflict_count": 0,
        "match_wrapper_identity_conflict_count": 0,
        "country_conflict_count": 0,
        "competition_class_conflict_count": 0,
        "primary_id_collision_count": 0,
    }:
        raise _error("qualification checks changed")

    if receipt.get("mapping_qualification_proven") is not True:
        raise _error("primaryId mapping qualification must remain proven")
    if receipt.get("competition_registry_mutation_performed") is not False:
        raise _error("competition registry mutation must remain false")
    if receipt.get("source_capability_registry_mutation_performed") is not False:
        raise _error("source capability mutation must remain false")
    if receipt.get("historical_coverage_proven") is not False:
        raise _error("historical coverage must remain unproven")
    if tuple(receipt.get("remaining_blockers", ())) != EXPECTED_REMAINING_BLOCKERS:
        raise _error("remaining blocker set changed")
    if receipt.get("next_required_boundary") != NEXT_REQUIRED_BOUNDARY:
        raise _error("next reviewed boundary changed")

    safety = receipt.get("safety")
    if (
        not isinstance(safety, dict)
        or not safety
        or any(type(value) is not bool or value is not False for value in safety.values())
    ):
        raise _error("all downstream safety flags must remain exact False")


def load_fotmob_primary_id_competition_mapping_qualification_receipt() -> dict[str, Any]:
    """Load and fully validate the canonical PR #108 qualification receipt."""

    protocol = _verify_upstream_protocol()
    pr105_receipt = _verify_pr105_receipt()
    receipt = _load_exact_json(
        RECEIPT_PATH,
        expected_sha256=RECEIPT_SHA256,
        expected_size=RECEIPT_SIZE,
    )
    _validate_receipt(receipt, protocol, pr105_receipt)
    return receipt


def canonical_fotmob_primary_id_competition_mapping_qualification_receipt_bytes() -> bytes:
    """Return the exact canonical checked-in qualification receipt bytes."""

    receipt = load_fotmob_primary_id_competition_mapping_qualification_receipt()
    raw = _canonical(receipt)
    if len(raw) != RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise _error("qualification receipt canonical identity changed")
    return raw
