#!/usr/bin/env python3
"""Execute PR #119 against the exact preserved FotMob historical campaign only."""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import pathlib
import tempfile
from typing import Any
from zoneinfo import ZoneInfo

import domain.fotmob_historical_source_history_completeness_materialization_protocol as pr118
import domain.fotmob_historical_source_history_adapter_qualification as pr117
import domain.prospective_successor_feature_construction_candidate as pr80
import scripts.qualify_fotmob_historical_source_history_adapter as pr117_exec

REPOSITORY_MAIN_ANCHOR = "2b2f6390f077b562c185768db030c7c4e61a06de"
PR118_PROTOCOL_BLOB_SHA = "be7119f06804093959b6730c2fe8ac05ea4d2f05"
EXPECTED_RECEIPT_SHA256 = "da8037cd9b4a4f91be942a4052e76134b66cc94221ed66e624c14008c9e562a0"
EXPECTED_RECEIPT_SIZE = 6_810
MATERIALIZATION_PROJECTION_SHA256 = "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2"
MATERIALIZATION_PROJECTION_SIZE = 10_545_099
NEXT_REQUIRED_BOUNDARY = "PRE_REGISTER_REVIEWED_FOTMOB_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_PROTOCOL"

EXPECTED_BY_LEAGUE = {
    "B1": 1933,
    "D1": 1835,
    "E0": 2280,
    "F1": 2056,
    "G1": 1431,
    "I1": 2280,
    "N1": 1865,
    "P1": 1846,
    "SC0": 1380,
    "SP1": 2280,
    "T1": 2140,
}
EXPECTED_SPECIAL_COUNTS = {
    "ABANDONED": 20,
    "AFTER_EXTRA_TIME": 3,
    "AFTER_PENALTIES": 3,
    "AWARDED_WIN": 26,
    "CANCELLED": 11,
    "POSTPONED": 241,
}
SAFETY_KEYS = (
    "bet_authorized",
    "calibration_for_production_authorized",
    "competition_registry_mutation_authorized",
    "expected_goals_production_authorized",
    "expected_goals_transform_approved",
    "global_historical_coverage_capability_mutation_authorized",
    "market_activation_authorized",
    "model_training_authorized",
    "pr80_constructor_input_authorized",
    "pricing_authorized",
    "probability_adjustment_authorized",
    "probability_inference_authorized",
    "production_approval_authorized",
    "score_matrix_authorized",
    "selection_authorized",
    "successor_candidate_approved",
    "successor_live_inputs_qualified",
)


class QualificationError(RuntimeError):
    """Raised when the exact PR #119 qualification cannot be reproduced."""


def fail(message: str) -> None:
    raise QualificationError(message)


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def parse_utc(value: Any) -> dt.datetime:
    if type(value) is not str:
        fail("UTC timestamp must be exact text")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QualificationError("UTC timestamp is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        fail("UTC timestamp must be timezone-aware")
    return parsed.astimezone(dt.timezone.utc)


def utc_text(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def verify_upstream() -> None:
    protocol = pr118.build_fotmob_historical_source_history_completeness_materialization_protocol()
    protocol_raw = pr118.canonical_fotmob_historical_source_history_completeness_materialization_protocol_bytes(protocol)
    if (hashlib.sha256(protocol_raw).hexdigest(), len(protocol_raw)) != (
        pr118.PROTOCOL_SHA256,
        pr118.PROTOCOL_SIZE,
    ):
        fail("PR118 protocol identity changed")
    if pr118.NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_AND_MATERIALIZATION_QUALIFICATION"
    ):
        fail("PR118 next boundary changed")

    receipt = pr117.load_fotmob_historical_source_history_adapter_qualification_receipt()
    exact = pr117.canonical_fotmob_historical_source_history_adapter_qualification_receipt_bytes()
    if (hashlib.sha256(exact).hexdigest(), len(exact)) != (
        pr117.RECEIPT_SHA256,
        pr117.RECEIPT_SIZE,
    ):
        fail("PR117 receipt identity changed")
    if receipt.get("historical_source_history_adapter_qualified") is not True:
        fail("PR117 historical adapter qualification changed")
    if receipt.get("remaining_blockers") != ["BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"]:
        fail("PR117 blocker ancestry changed")
    if receipt.get("history_rows_materialized") != 0:
        fail("PR117 unexpectedly materialized history rows")


def _materialize_record(record: dict[str, Any], line: bytes) -> tuple[pr80.ProspectiveMatchEvidence, str]:
    kickoff = parse_utc(record.get("kickoff_utc"))
    if record.get("request_date") != kickoff.strftime("%Y%m%d"):
        fail("materializable request date no longer equals kickoff UTC date")

    first_observed = parse_utc(record.get("first_observed_at"))
    second_observed = parse_utc(record.get("second_observed_at"))
    observed_at = min(first_observed, second_observed)
    if observed_at <= kickoff:
        fail("final-result evidence is not strictly post-kickoff")

    fixture_id = record.get("fixture_id")
    home_team_id = record.get("home_team_id")
    away_team_id = record.get("away_team_id")
    if type(fixture_id) is not int or fixture_id < 1:
        fail("materializable fixture identity changed")
    if (
        type(home_team_id) is not int
        or home_team_id < 1
        or type(away_team_id) is not int
        or away_team_id < 1
        or home_team_id == away_team_id
    ):
        fail("materializable team identity changed")

    source_local = kickoff.astimezone(ZoneInfo(pr118.SOURCE_DISPLAY_TIME_BASIS)).replace(tzinfo=None)
    evidence_sha = hashlib.sha256(line).hexdigest()
    reference = (
        f"fotmob-source-history-campaign-31887523012:"
        f"{record['request_date']}:{fixture_id}"
    )
    try:
        evidence = pr80.ProspectiveMatchEvidence(
            source_namespace=pr118.SOURCE_NAMESPACE,
            fixture_identifier=str(fixture_id),
            source_local_kickoff=source_local,
            kickoff_utc=kickoff,
            home_team_identifier=str(home_team_id),
            away_team_identifier=str(away_team_id),
            home_goals=record["home_score"],
            away_goals=record["away_score"],
            observed_at=observed_at,
            evidence_sha256=evidence_sha,
            evidence_reference=reference,
        )
    except pr80.ProspectiveSuccessorFeatureConstructionError as exc:
        raise QualificationError("PR80 structural materialization invariant failed") from exc
    return evidence, record["model_league_code"]


def build_receipt(
    artifact: pathlib.Path,
    projection_output: pathlib.Path | None = None,
) -> dict[str, Any]:
    verify_upstream()

    with tempfile.TemporaryDirectory(prefix="athena-pr119-") as temp:
        pr117_projection_path = pathlib.Path(temp) / "pr117-ordinary-ft.ndjson"
        pr117_receipt = pr117_exec.build_receipt(
            artifact,
            projection_output=pr117_projection_path,
        )
        pr117_receipt_raw = canonical(pr117_receipt)
        if (hashlib.sha256(pr117_receipt_raw).hexdigest(), len(pr117_receipt_raw)) != (
            pr117.RECEIPT_SHA256,
            pr117.RECEIPT_SIZE,
        ):
            fail("PR117 exact artifact re-execution changed")

        projection_raw = pr117_projection_path.read_bytes()
        if (hashlib.sha256(projection_raw).hexdigest(), len(projection_raw)) != (
            pr117.ORDINARY_FT_PROJECTION_SHA256,
            pr117.ORDINARY_FT_PROJECTION_SIZE,
        ):
            fail("PR117 projection identity changed during PR119 execution")

        lines = projection_raw.splitlines(keepends=True)
        if len(lines) != 21_336:
            fail("PR117 ordinary-FT projection record count changed")

        materialized: list[pr80.ProspectiveMatchEvidence] = []
        by_league: collections.Counter[str] = collections.Counter()
        preboundary_count = 0
        seen_fixtures: set[str] = set()
        local_team_slots: set[tuple[dt.datetime, str]] = set()
        utc_team_slots: set[tuple[dt.datetime, str]] = set()
        evidence_hashes: collections.Counter[str] = collections.Counter()
        evidence_refs: collections.Counter[str] = collections.Counter()

        for line in lines:
            try:
                record = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise QualificationError("PR117 projection line is malformed") from exc
            if not isinstance(record, dict) or line != canonical(record):
                fail("PR117 projection line is not exact canonical JSON")
            disposition = record.get("elo_floor_disposition")
            if disposition == "BEFORE_PR114_ELO_INITIALIZATION_FLOOR":
                preboundary_count += 1
                continue
            if disposition != "ON_OR_AFTER_PR114_ELO_INITIALIZATION_FLOOR":
                fail("PR117 Elo-floor disposition changed")

            evidence, league_code = _materialize_record(record, line)
            if evidence.fixture_identifier in seen_fixtures:
                fail("materializable duplicate source fixture identity")
            seen_fixtures.add(evidence.fixture_identifier)
            for team in (evidence.home_team_identifier, evidence.away_team_identifier):
                local_key = (evidence.source_local_kickoff, team)
                utc_key = (evidence.kickoff_utc, team)
                if local_key in local_team_slots:
                    fail("same source-scoped team has multiple source-local fixtures at one kickoff")
                if utc_key in utc_team_slots:
                    fail("same source-scoped team has multiple UTC fixtures at one kickoff")
                local_team_slots.add(local_key)
                utc_team_slots.add(utc_key)
            materialized.append(evidence)
            by_league[league_code] += 1
            evidence_hashes[evidence.evidence_sha256] += 1
            evidence_refs[evidence.evidence_reference] += 1

    if preboundary_count != 10 or len(materialized) != 21_326:
        fail("PR114 floor split changed")
    if dict(sorted(by_league.items())) != EXPECTED_BY_LEAGUE:
        fail("materializable per-league accounting changed")
    if any(count > 1 for count in evidence_hashes.values()):
        fail("materialization evidence hash unexpectedly reused")
    if any(count > 1 for count in evidence_refs.values()):
        fail("materialization evidence reference unexpectedly reused")

    local_order = sorted(
        materialized,
        key=lambda row: (row.source_local_kickoff, row.fixture_identifier),
    )
    utc_order = sorted(
        materialized,
        key=lambda row: (row.kickoff_utc, row.fixture_identifier),
    )
    if tuple(row.fixture_identifier for row in local_order) != tuple(
        row.fixture_identifier for row in utc_order
    ):
        fail("source-display-local and UTC materialization ordering disagree")

    projection = b"".join(canonical(row.to_dict()) for row in local_order)
    if (hashlib.sha256(projection).hexdigest(), len(projection)) != (
        MATERIALIZATION_PROJECTION_SHA256,
        MATERIALIZATION_PROJECTION_SIZE,
    ):
        fail("materialization projection changed")
    if projection_output is not None:
        projection_output.parent.mkdir(parents=True, exist_ok=True)
        projection_output.write_bytes(projection)

    observed = [row.observed_at for row in materialized]
    kickoff = [row.kickoff_utc for row in materialized]
    lag_us = [int((row.observed_at - row.kickoff_utc).total_seconds() * 1_000_000) for row in materialized]
    teams = {
        team
        for row in materialized
        for team in (row.home_team_identifier, row.away_team_identifier)
    }
    adapter = pr117_receipt["adapter_qualification"]
    checks = pr117_receipt["checks"]

    receipt = {
        "schema_version": 1,
        "dataset_name": "athena-fotmob-historical-source-history-completeness-materialization-qualification-v1",
        "qualification_scope": "IMMUTABLE_FROZEN_CAMPAIGN_SCOPED_HISTORICAL_COMPLETENESS_AND_MATERIALIZATION_ONLY",
        "qualification_state": "EXECUTED_SCOPED_HISTORICAL_COMPLETENESS_QUALIFIED_ROWS_MATERIALIZED_PR80_USE_UNREVIEWED",
        "repository_main_anchor": REPOSITORY_MAIN_ANCHOR,
        "protocol": {
            "protocol_id": pr118.PROTOCOL_ID,
            "blob_sha": PR118_PROTOCOL_BLOB_SHA,
            "canonical_sha256": pr118.PROTOCOL_SHA256,
            "canonical_size_bytes": pr118.PROTOCOL_SIZE,
        },
        "upstream": {
            "pr81_protocol_sha256": pr118.PR81_PROTOCOL_SHA256,
            "pr99_protocol_sha256": pr118.PR99_PROTOCOL_SHA256,
            "pr110_special_result_receipt_sha256": pr118.PR110_RECEIPT_SHA256,
            "pr112_rearrangement_chronology_receipt_sha256": pr118.PR112_RECEIPT_SHA256,
            "pr114_elo_initialization_receipt_sha256": pr118.PR114_RECEIPT_SHA256,
            "pr117_historical_adapter_receipt_sha256": pr117.RECEIPT_SHA256,
            "pr117_historical_adapter_receipt_size_bytes": pr117.RECEIPT_SIZE,
            "pr117_ordinary_ft_projection_sha256": pr117.ORDINARY_FT_PROJECTION_SHA256,
            "pr117_ordinary_ft_projection_size_bytes": pr117.ORDINARY_FT_PROJECTION_SIZE,
        },
        "source_evidence": {
            "artifact_id": pr118.ARTIFACT_ID,
            "artifact_name": "fotmob-ordinary-ft-source-history-campaign-31887523012",
            "artifact_sha256": pr118.ARTIFACT_SHA256,
            "artifact_size_bytes": pr118.ARTIFACT_SIZE,
            "research_cache_sha256": pr118.RESEARCH_CACHE_SHA256,
            "research_cache_size_bytes": pr118.RESEARCH_CACHE_SIZE,
            "request_timezone": pr118.REQUEST_TIMEZONE,
            "ccode3": pr118.REQUEST_CCODE3,
            "historical_request_date_start": pr118.HISTORICAL_REQUEST_DATE_START,
            "historical_request_date_end": pr118.HISTORICAL_REQUEST_DATE_END,
            "source_display_time_basis": pr118.SOURCE_DISPLAY_TIME_BASIS,
            "pr80_source_local_semantic_equivalence": pr118.PR80_SOURCE_LOCAL_SEMANTIC_EQUIVALENCE,
        },
        "completeness_qualification": {
            "qualification_status": "QUALIFIED_COMPLETE_FROZEN_HISTORICAL_HISTORY_THROUGH_2026_08_14",
            "request_date_count": adapter["request_date_count"],
            "capture_manifest_count": adapter["capture_manifest_count"],
            "missing_required_date_count": 0,
            "capture_pair_cardinality_mismatch_count": 0,
            "request_identity_mismatch_count": checks["request_identity_mismatch_count"],
            "manifest_raw_lineage_mismatch_count": checks["manifest_raw_lineage_mismatch_count"],
            "target_family_fixture_date_occurrence_count": adapter["target_family_fixture_date_pair_count"],
            "ordinary_ft_occurrence_count": adapter["ordinary_ft_projection_record_count"],
            "reviewed_special_state_occurrence_count": adapter["reviewed_special_state_occurrence_count"],
            "unreviewed_target_state_occurrence_count": checks["unreviewed_target_state_occurrence_count"],
            "preboundary_ordinary_ft_occurrence_count": preboundary_count,
            "on_or_after_floor_materialization_candidate_count": len(materialized),
            "ordinary_ft_unique_source_fixture_id_count": adapter["ordinary_ft_unique_source_fixture_id_count"],
            "ordinary_ft_duplicate_source_fixture_id_count": adapter["ordinary_ft_duplicate_source_fixture_id_count"],
            "materializable_duplicate_source_fixture_id_count": 0,
            "same_team_same_source_local_kickoff_conflict_count": 0,
            "same_team_same_utc_kickoff_conflict_count": 0,
            "request_date_kickoff_utc_date_mismatch_count": 0,
            "source_display_time_basis_mismatch_count": checks["source_display_time_basis_mismatch_count"],
            "source_local_utc_global_order_disagreement_count": 0,
            "final_result_observation_not_after_kickoff_count": 0,
            "materialization_row_invariant_violation_count": 0,
            "materialization_evidence_sha256_duplicate_count": 0,
            "materialization_evidence_reference_duplicate_count": 0,
            "source_scoped_team_identity_count": len(teams),
            "materialized_kickoff_utc_min": utc_text(min(kickoff)),
            "materialized_kickoff_utc_max": utc_text(max(kickoff)),
            "materialized_observed_at_min": utc_text(min(observed)),
            "materialized_observed_at_max": utc_text(max(observed)),
            "minimum_final_result_observation_lag_microseconds": min(lag_us),
            "maximum_final_result_observation_lag_microseconds": max(lag_us),
            "on_or_after_floor_by_model_league": dict(sorted(by_league.items())),
            "special_state_occurrence_counts": checks["special_state_occurrence_counts"],
        },
        "materialization": {
            "history_row_count": len(materialized),
            "projection_format": "CANONICAL_JSON_LINES_SORTED_BY_SOURCE_LOCAL_KICKOFF_THEN_FIXTURE_IDENTIFIER",
            "projection_sha256": MATERIALIZATION_PROJECTION_SHA256,
            "projection_size_bytes": MATERIALIZATION_PROJECTION_SIZE,
            "source_namespace": pr118.SOURCE_NAMESPACE,
            "source_local_kickoff_derivation": "CANONICAL_KICKOFF_UTC_TO_EUROPE_OSLO_THEN_NAIVE_DISPLAY_TIME_CANDIDATE",
            "observed_at_rule": "EARLIEST_OF_THE_TWO_PR117_QUALIFIED_MANIFEST_OBSERVATION_TIMES",
            "evidence_sha256_rule": "SHA256_OF_EXACT_CANONICAL_PR117_ORDINARY_FT_PROJECTION_RECORD",
            "evidence_reference_rule": "FROZEN_CAMPAIGN_REQUEST_DATE_AND_SOURCE_FIXTURE_ID",
            "pr80_structural_validation_performed": True,
            "pr80_source_local_semantic_equivalence_proven": False,
            "pr80_constructor_input_authorized": False,
        },
        "scoped_authority": {
            "frozen_campaign_historical_source_history_completeness_proven": True,
            "frozen_campaign_historical_adapter_approved": True,
            "exact_21326_ordinary_ft_history_rows_materialized": True,
            "exact_21326_ordinary_ft_history_rows_materialization_authorized": True,
        },
        "global_authority": {
            "global_source_capability_historical_coverage_confirmed": False,
            "source_capability_registry_mutation_performed": False,
            "competition_registry_mutation_performed": False,
            "pr80_constructor_input_authorized": False,
            "successor_live_inputs_qualified": False,
            "successor_candidate_approved": False,
            "model_training_authorized": False,
            "expected_goals_production_authorized": False,
            "probability_inference_authorized": False,
            "pricing_authorized": False,
            "market_activation_authorized": False,
            "selection_authorized": False,
            "production_approval_authorized": False,
            "bet_authorized": False,
        },
        "handoff_constraints": [
            "PR80_SOURCE_LOCAL_SEMANTIC_EQUIVALENCE_REMAINS_UNPROVEN",
            "TARGETS_REQUIRING_DATES_AFTER_2026_08_14_REQUIRE_A_SEPARATELY_REVIEWED_CONTIGUOUS_PROSPECTIVE_EXTENSION",
            "PR80_TARGET_SPECIFIC_HISTORY_USE_REMAINS_UNREVIEWED",
        ],
        "resolved_blocker": "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": {key: False for key in SAFETY_KEYS},
    }
    exact = canonical(receipt)
    if (hashlib.sha256(exact).hexdigest(), len(exact)) != (
        EXPECTED_RECEIPT_SHA256,
        EXPECTED_RECEIPT_SIZE,
    ):
        fail("PR119 receipt does not match the frozen execution identity")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=pathlib.Path)
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path(
            "artifacts/research-manifests/"
            "fotmob-historical-source-history-completeness-materialization-qualification-v1.json"
        ),
    )
    parser.add_argument("--projection-output", type=pathlib.Path, default=None)
    args = parser.parse_args()
    receipt = build_receipt(args.artifact, args.projection_output)
    exact = canonical(receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(exact)
    print(
        f"wrote {args.output} size={len(exact)} "
        f"sha256={hashlib.sha256(exact).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
