#!/usr/bin/env python3
"""Execute the reviewed FotMob source-history adapter/completeness boundary.

The assessment is deliberately fail-closed. It binds the exact PR81/PR99
contracts and the PR108/PR110/PR112/PR114 qualifications to the preserved
campaign, then tests whether the already-reviewed prospective ordinary-FT
adapter can admit that historical evidence without changing its contract.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import pathlib
import tarfile
import tempfile
import zipfile
from collections import Counter
from typing import Any
from zoneinfo import ZoneInfo

import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as reviewed_adapter
import domain.fotmob_ordinary_ft_finished_score_source_history_completeness_protocol as pr99
import domain.fotmob_primary_id_competition_mapping_qualification as pr108
import domain.fotmob_source_history_elo_initialization_boundary_qualification as pr114
import domain.fotmob_source_history_rearrangement_chronology_qualification as pr112
import domain.fotmob_source_history_special_result_semantics_qualification as pr110
import domain.prospective_successor_source_history_completeness_protocol as pr81
from domain.fotmob_data_matches_capture import (
    FotMobDataMatchesCaptureManifest,
    parse_utc_timestamp,
    sha256_data_matches_capture_manifest,
)

DATASET_NAME = "athena-fotmob-source-history-adapter-completeness-assessment-v1"
ASSESSMENT_SCOPE = "EXECUTED_REVIEWED_SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_ASSESSMENT_ONLY"
ASSESSMENT_STATE = "EXECUTED_FAIL_CLOSED_REVIEWED_PROSPECTIVE_ADAPTER_INCOMPATIBLE_WITH_HISTORICAL_CAMPAIGN"
REPOSITORY_MAIN_ANCHOR = "1571ab8f1431bd7e083a02f5c55e30ff11c01c5a"

ARTIFACT_ID = 9_249_856_559
ARTIFACT_NAME = "fotmob-ordinary-ft-source-history-campaign-31887523012"
ARTIFACT_SHA256 = "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
ARTIFACT_SIZE = 61_886_753
CACHE_SHA256 = "cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6"
CACHE_SIZE = 61_881_610
CAMPAIGN_START = dt.date(2020, 8, 1)
CAMPAIGN_END = dt.date(2026, 8, 14)
EXPECTED_DATE_COUNT = 2_205
EXPECTED_CAPTURE_COUNT = 4_410
EXPECTED_TARGET_PAIR_COUNT = 21_640
EXPECTED_TARGET_RAW_ROW_COUNT = 43_280
EXPECTED_PREBOUNDARY_ORDINARY = 10
EXPECTED_ORDINARY_ON_OR_AFTER_FLOOR = 21_326
EXPECTED_SPECIAL_ON_OR_AFTER_FLOOR = 304
EXPECTED_IDENTICAL_RAW_PAIR_COUNT = 2_204
EXPECTED_DISTINCT_RAW_PAIR_DATES = ("20250712",)

PR81_SHA256 = "9d16fcc79e9809a82ef154c75b8e263f782a4e1d4723b57cc216d893c88780ec"
PR81_SIZE = 4_223
PR99_SHA256 = "edddd7445bb9bb6ed2db4778b6ab48da9489ae6efac822b6e6c139992275bf87"
PR99_SIZE = 5_741
PR108_RECEIPT_SHA256 = "fdb55feef9585fe0aa2668ddb9ac9a6eb8e63ac8870c06cdb7917d1f996e7bc9"
PR108_RECEIPT_SIZE = 13_681
PR110_RECEIPT_SHA256 = "7d6bb5c86391c45abdbb588a27325c99ebf88c4753f75c108387e2c4d3dbb99d"
PR110_RECEIPT_SIZE = 8_558
PR112_RECEIPT_SHA256 = "58c7a275580cc74489269a66de2836544e78ca232693d5283f1813ee817d3fc0"
PR112_RECEIPT_SIZE = 7_980
PR114_RECEIPT_SHA256 = "fbbec0b858c3e9630d9f4c7dec630012f57811de52d300db3a11b781a719e110"
PR114_RECEIPT_SIZE = 24_428
REVIEWED_ADAPTER_BLOB_SHA = "868563206e09010fce74b4ba7954028930baad54"
DERIVED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
SOURCE_DISPLAY_TIME_BASIS = "Europe/Oslo"
PRIMARY_STATUS = "BLOCKED_RESULT_EVIDENCE_GAP"
NEXT_REQUIRED_BOUNDARY = "PRE_REGISTER_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_ADAPTER_PROTOCOL"

PRIMARY_TO_MODEL = {row[1]: row[0] for row in pr114.EXPECTED_FAMILY_SUMMARY}
MODEL_FLOORS = dict(pr114.EXPECTED_FLOORS)
ORDINARY_REASON = dict(reviewed_adapter.ORDINARY_FT_REASON_TUPLE)
SAFETY_KEYS = (
    "source_history_adapter_approved",
    "source_history_completeness_proven",
    "ordinary_ft_history_rows_authorized",
    "pr80_constructor_input_authorized",
    "successor_live_inputs_qualified",
    "successor_candidate_approved",
    "expected_goals_transform_approved",
    "expected_goals_production_authorized",
    "score_matrix_authorized",
    "probability_inference_authorized",
    "probability_adjustment_authorized",
    "calibration_for_production_authorized",
    "pricing_authorized",
    "market_activation_authorized",
    "selection_authorized",
    "production_approval_authorized",
    "model_training_authorized",
    "bet_authorized",
    "competition_registry_mutation_authorized",
    "source_capability_registry_mutation_authorized",
)


class AssessmentError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise AssessmentError(message)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_json(path: pathlib.Path, expected_sha: str, expected_size: int) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) != expected_size or hashlib.sha256(raw).hexdigest() != expected_sha:
        fail(f"{path.name} exact identity changed")
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != canonical(value):
        fail(f"{path.name} is not exact canonical JSON")
    return value


def manifest_from_dict(value: dict[str, Any]) -> FotMobDataMatchesCaptureManifest:
    return FotMobDataMatchesCaptureManifest(
        schema_version=value["schema_version"], dataset_name=value["dataset_name"],
        request_date=value["request_date"], timezone=value["timezone"], ccode3=value["ccode3"],
        host=value["host"], request_target=value["request_target"],
        request_headers=tuple(tuple(item) for item in value["request_headers"]),
        x_mas_included=value["x_mas_included"], status=value["status"],
        content_type=value["content_type"], content_length=value["content_length"],
        observed_at=parse_utc_timestamp(value["observed_at"], "observed_at"),
        network_acquisition_performed=value["network_acquisition_performed"],
        raw_file_name=value["raw_file_name"], raw_sha256=value["raw_sha256"],
        raw_size=value["raw_size"], safety=value["safety"],
    )


def safe_extract_cache(artifact: pathlib.Path, destination: pathlib.Path) -> pathlib.Path:
    if artifact.stat().st_size != ARTIFACT_SIZE or sha256_file(artifact) != ARTIFACT_SHA256:
        fail("preserved campaign artifact identity changed")
    with zipfile.ZipFile(artifact) as archive:
        cache = archive.read("athena-research-cache.tar.gz")
    if len(cache) != CACHE_SIZE or hashlib.sha256(cache).hexdigest() != CACHE_SHA256:
        fail("preserved campaign research cache identity changed")
    root = destination.resolve()
    with tarfile.open(fileobj=io.BytesIO(cache), mode="r:gz") as tar:
        for member in tar.getmembers():
            target = (root / member.name).resolve()
            if root != target and root not in target.parents:
                fail("campaign cache contains unsafe path traversal")
        tar.extractall(destination, filter="data")
    captures = destination / ".cache" / "athena-research" / "fotmob-data-matches-captures"
    if not captures.is_dir():
        fail("campaign capture directory is missing")
    return captures


def required_dates() -> list[str]:
    dates: list[str] = []
    current = CAMPAIGN_START
    while current <= CAMPAIGN_END:
        dates.append(current.strftime("%Y%m%d"))
        current += dt.timedelta(days=1)
    if len(dates) != EXPECTED_DATE_COUNT:
        fail("internal campaign date count changed")
    return dates


def load_pair(date_dir: pathlib.Path, request_date: str) -> list[tuple[FotMobDataMatchesCaptureManifest, bytes, dict[str, Any], str]]:
    capture_dirs = sorted(path for path in date_dir.iterdir() if path.is_dir())
    if len(capture_dirs) != 2:
        fail(f"{request_date} does not contain exactly two captures")
    result = []
    for capture_dir in capture_dirs:
        manifest_raw = (capture_dir / "manifest.json").read_bytes()
        response = (capture_dir / "response.json").read_bytes()
        manifest_value = json.loads(manifest_raw)
        if manifest_raw != canonical(manifest_value):
            fail(f"{request_date} manifest is not canonical JSON")
        manifest = manifest_from_dict(manifest_value)
        if (manifest.request_date, manifest.timezone, manifest.ccode3) != (request_date, "UTC", "NGA"):
            fail(f"{request_date} request identity changed")
        if hashlib.sha256(response).hexdigest() != manifest.raw_sha256 or len(response) != manifest.raw_size:
            fail(f"{request_date} raw response lineage changed")
        result.append((manifest, response, json.loads(response), hashlib.sha256(manifest_raw).hexdigest()))
    result.sort(key=lambda item: item[0].observed_at)
    return result


def target_index(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    leagues = payload.get("leagues")
    if not isinstance(leagues, list):
        fail("payload leagues shape changed")
    result: dict[int, dict[str, Any]] = {}
    for league in leagues:
        if not isinstance(league, dict):
            fail("league shape changed")
        primary_id = league.get("primaryId")
        model_code = PRIMARY_TO_MODEL.get(primary_id)
        if model_code is None:
            continue
        wrapper_id = league.get("id")
        matches = league.get("matches")
        if type(wrapper_id) is not int or not isinstance(matches, list):
            fail("mapped wrapper shape changed")
        for match in matches:
            fixture_id = match.get("id") if isinstance(match, dict) else None
            if type(fixture_id) is not int or fixture_id < 1 or fixture_id in result:
                fail("mapped fixture identity changed")
            status, home, away = match.get("status"), match.get("home"), match.get("away")
            if not all(isinstance(item, dict) for item in (status, home, away)) or match.get("leagueId") != wrapper_id:
                fail("mapped match structure changed")
            kickoff_text, display_time = status.get("utcTime"), match.get("time")
            if not isinstance(kickoff_text, str) or not isinstance(display_time, str):
                fail("mapped kickoff fields changed")
            kickoff = parse_utc_timestamp(kickoff_text, "kickoff_utc")
            try:
                source_local = dt.datetime.strptime(display_time, "%d.%m.%Y %H:%M")
            except ValueError as exc:
                raise AssessmentError("source display-time format changed") from exc
            oslo = kickoff.astimezone(ZoneInfo(SOURCE_DISPLAY_TIME_BASIS)).replace(tzinfo=None, second=0, microsecond=0)
            result[fixture_id] = {
                "model_league_code": model_code, "primary_id": primary_id,
                "wrapper_league_id": wrapper_id, "home_team_id": home.get("id"),
                "away_team_id": away.get("id"), "home_score": home.get("score"),
                "away_score": away.get("score"), "home_pen_score_present": "penScore" in home,
                "away_pen_score_present": "penScore" in away, "kickoff_utc": kickoff,
                "kickoff_text": kickoff_text, "source_local": source_local,
                "source_local_matches_oslo": source_local == oslo, "finished": status.get("finished"),
                "started": status.get("started"), "cancelled": status.get("cancelled"),
                "awarded": status.get("awarded"), "reason": status.get("reason"),
            }
    return result


def relevant_tuple(item: dict[str, Any]) -> tuple[Any, ...]:
    reason = item["reason"]
    reason_tuple = tuple((key, reason.get(key)) for key in ("short", "shortKey", "long", "longKey")) if isinstance(reason, dict) else None
    return (
        item["model_league_code"], item["primary_id"], item["wrapper_league_id"],
        item["home_team_id"], item["away_team_id"], item["kickoff_text"],
        item["source_local"].isoformat(), item["home_score"], item["away_score"],
        item["home_pen_score_present"], item["away_pen_score_present"],
        item["finished"], item["started"], item["cancelled"], item["awarded"], reason_tuple,
    )


def is_potential_ordinary(item: dict[str, Any]) -> bool:
    return (
        item["finished"] is True and item["started"] is True and item["cancelled"] is False
        and item["awarded"] in (None, False) and item["reason"] == ORDINARY_REASON
        and type(item["home_score"]) is int and item["home_score"] >= 0
        and type(item["away_score"]) is int and item["away_score"] >= 0
        and not item["home_pen_score_present"] and not item["away_pen_score_present"]
    )


def verify_upstream() -> None:
    p81 = pr81.build_prospective_successor_source_history_completeness_protocol()
    raw81 = pr81.canonical_prospective_successor_source_history_completeness_protocol_bytes(p81)
    if (hashlib.sha256(raw81).hexdigest(), len(raw81)) != (PR81_SHA256, PR81_SIZE):
        fail("PR81 protocol identity changed")
    p99 = pr99.build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol()
    raw99 = pr99.canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol_bytes(p99)
    if (hashlib.sha256(raw99).hexdigest(), len(raw99)) != (PR99_SHA256, PR99_SIZE):
        fail("PR99 protocol identity changed")
    receipts = {
        "pr108": exact_json(pr108.RECEIPT_PATH, PR108_RECEIPT_SHA256, PR108_RECEIPT_SIZE),
        "pr110": exact_json(pr110.RECEIPT_PATH, PR110_RECEIPT_SHA256, PR110_RECEIPT_SIZE),
        "pr112": exact_json(pr112.RECEIPT_PATH, PR112_RECEIPT_SHA256, PR112_RECEIPT_SIZE),
        "pr114": exact_json(pr114.RECEIPT_PATH, PR114_RECEIPT_SHA256, PR114_RECEIPT_SIZE),
    }
    if receipts["pr108"].get("mapping_qualification_proven") is not True:
        fail("PR108 mapping qualification changed")
    if receipts["pr110"].get("special_result_semantics_qualified") is not True:
        fail("PR110 special-result qualification changed")
    if receipts["pr112"].get("rearrangement_chronology_qualified") is not True:
        fail("PR112 chronology qualification changed")
    if receipts["pr114"].get("initialization_boundary_qualified") is not True:
        fail("PR114 initialization qualification changed")
    if receipts["pr114"].get("remaining_blockers") != ["BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"]:
        fail("PR114 blocker ancestry changed")


def build_receipt(artifact: pathlib.Path) -> dict[str, Any]:
    verify_upstream()
    with tempfile.TemporaryDirectory(prefix="athena-pr115-") as temp:
        captures_root = safe_extract_cache(artifact, pathlib.Path(temp))
        dates = required_dates()
        if sorted(path.name for path in captures_root.iterdir() if path.is_dir()) != dates:
            fail("campaign daily coverage changed")

        identical_raw_pairs = 0
        distinct_raw_dates: list[str] = []
        distinct_manifest_pairs = 0
        separation_us: list[int] = []
        pair_conflicts = 0
        time_basis_mismatches = 0
        target_pairs = 0
        target_raw_rows = 0
        preboundary_ordinary = 0
        ordinary_after_floor = 0
        special_after_floor = 0
        target_pairs_on_distinct_raw_dates = 0
        ordinary_on_distinct_raw_dates = 0
        by_league: Counter[str] = Counter()
        first_identical_pair = None
        distinct_pair_adapter_results: list[dict[str, Any]] = []

        for request_date in dates:
            pair = load_pair(captures_root / request_date, request_date)
            fm, fr, fp, ffile_sha = pair[0]
            sm, sr, sp, sfile_sha = pair[1]
            if sha256_data_matches_capture_manifest(fm) != ffile_sha or sha256_data_matches_capture_manifest(sm) != sfile_sha:
                fail("manifest canonical lineage changed")
            if ffile_sha == sfile_sha:
                fail("pair reused one manifest lineage")
            distinct_manifest_pairs += 1
            delta_us = int((sm.observed_at - fm.observed_at).total_seconds() * 1_000_000)
            if sm.observed_at <= fm.observed_at or delta_us < 300_000_000:
                fail("capture-pair observation separation changed")
            separation_us.append(delta_us)

            raw_identical = fm.raw_sha256 == sm.raw_sha256
            if raw_identical:
                identical_raw_pairs += 1
                if first_identical_pair is None:
                    first_identical_pair = (fr, fm, sr, sm)
            else:
                distinct_raw_dates.append(request_date)

            fi, si = target_index(fp), target_index(sp)
            if set(fi) != set(si):
                fail(f"{request_date} target membership conflict")
            for fixture_id in sorted(fi):
                a, b = fi[fixture_id], si[fixture_id]
                target_pairs += 1
                target_raw_rows += 2
                if relevant_tuple(a) != relevant_tuple(b):
                    pair_conflicts += 1
                    fail(f"{request_date}/{fixture_id} target field conflict")
                if not a["source_local_matches_oslo"] or not b["source_local_matches_oslo"]:
                    time_basis_mismatches += 1
                ordinary = is_potential_ordinary(a)
                if ordinary and a["kickoff_utc"].date().isoformat() < MODEL_FLOORS[a["model_league_code"]]:
                    preboundary_ordinary += 1
                elif ordinary:
                    ordinary_after_floor += 1
                    by_league[a["model_league_code"]] += 1
                    if not raw_identical:
                        ordinary_on_distinct_raw_dates += 1
                else:
                    special_after_floor += 1
                if not raw_identical:
                    target_pairs_on_distinct_raw_dates += 1

            if not raw_identical:
                try:
                    result = reviewed_adapter.adapt_fotmob_data_matches_ordinary_ft_finished_scores(fr, fm, sr, sm)
                except reviewed_adapter.FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError as exc:
                    distinct_pair_adapter_results.append({
                        "request_date": request_date,
                        "outcome": "BLOCKED",
                        "adapter_status": exc.status.value,
                        "error_message": str(exc),
                    })
                else:
                    distinct_pair_adapter_results.append({
                        "request_date": request_date,
                        "outcome": "PASSED",
                        "adapter_status": result.pair_status.value,
                        "terminal_candidate_union_count": result.terminal_candidate_union_count,
                        "qualified_count": result.qualified_count,
                        "adapter_result_sha256": reviewed_adapter.sha256_fotmob_data_matches_ordinary_ft_finished_score_adapter_result(result),
                    })

        if first_identical_pair is None:
            fail("no identical-raw exemplar found")
        try:
            reviewed_adapter.adapt_fotmob_data_matches_ordinary_ft_finished_scores(*first_identical_pair)
        except reviewed_adapter.FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError as exc:
            identical_exemplar_status = exc.status.value
            identical_exemplar_message = str(exc)
        else:
            fail("reviewed adapter unexpectedly accepted identical raw hashes")

    if (target_pairs, target_raw_rows) != (EXPECTED_TARGET_PAIR_COUNT, EXPECTED_TARGET_RAW_ROW_COUNT):
        fail("target-family campaign accounting changed")
    if (preboundary_ordinary, ordinary_after_floor, special_after_floor) != (
        EXPECTED_PREBOUNDARY_ORDINARY, EXPECTED_ORDINARY_ON_OR_AFTER_FLOOR, EXPECTED_SPECIAL_ON_OR_AFTER_FLOOR
    ):
        fail("PR114 target disposition accounting changed")
    if target_pairs != preboundary_ordinary + ordinary_after_floor + special_after_floor:
        fail("target-family accounting does not close")
    if identical_raw_pairs != EXPECTED_IDENTICAL_RAW_PAIR_COUNT or tuple(distinct_raw_dates) != EXPECTED_DISTINCT_RAW_PAIR_DATES:
        fail("raw pair-lineage membership changed")
    if distinct_manifest_pairs != EXPECTED_DATE_COUNT or pair_conflicts != 0 or time_basis_mismatches != 0:
        fail("manifest/stability/time-basis evidence changed")
    if target_pairs_on_distinct_raw_dates != 0 or ordinary_on_distinct_raw_dates != 0:
        fail("sole distinct-raw date unexpectedly contains target-family evidence")
    if identical_exemplar_status != reviewed_adapter.AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY.value:
        fail("identical-raw adapter blocker changed")
    if len(distinct_pair_adapter_results) != 1 or distinct_pair_adapter_results[0].get("adapter_status") != reviewed_adapter.AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION.value:
        fail("sole distinct-raw pair structural disposition changed")
    expected_by_league = {row[0]: row[5] for row in pr114.EXPECTED_FAMILY_SUMMARY}
    if dict(sorted(by_league.items())) != dict(sorted(expected_by_league.items())):
        fail("per-league ordinary candidate counts changed")

    gates = [
        {"gate_id":"DERIVED_SCORE_CAPABILITY","outcome":"PASSED","status":None,"reason":"PR99_DERIVED_SOURCE_REVALIDATES_SCOPED_ORDINARY_FT_FINISHED_SCORE_AND_FIXTURE_IDENTITY"},
        {"gate_id":"REQUIRED_DAILY_CAPTURE_COVERAGE","outcome":"PASSED","status":None,"reason":"ALL_2205_UTC_REQUEST_DATES_HAVE_EXACTLY_TWO_VALID_NGA_CAPTURE_MANIFESTS_WITH_REQUIRED_SEPARATION"},
        {"gate_id":"ELEVEN_LEAGUE_MAPPING","outcome":"PASSED","status":None,"reason":"PR108_QUALIFIED_ALL_ELEVEN_SOURCE_SCOPED_PRIMARY_ID_COMPETITION_FAMILIES"},
        {"gate_id":"NON_ORDINARY_RESULT_DISPOSITION","outcome":"PASSED","status":None,"reason":"PR110_QUALIFIED_SPECIAL_RESULT_SEMANTICS_AND_PRESERVATION_DISPOSITIONS"},
        {"gate_id":"IDENTITY_AND_REARRANGEMENT_CHRONOLOGY","outcome":"PASSED","status":None,"reason":"PR112_QUALIFIED_THE_EXACT_250_REARRANGED_SOURCE_FIXTURE_LINEAGES"},
        {"gate_id":"ELO_INITIALIZATION_BOUNDARY","outcome":"PASSED","status":None,"reason":"PR114_QUALIFIED_PR69_EQUIVALENT_EMPTY_1500_INITIALIZATION_FLOORS_FOR_ALL_ELEVEN_FAMILIES"},
        {"gate_id":"SOURCE_DISPLAY_TIME_BASIS","outcome":"PASSED_FOR_FROZEN_CORPUS_ONLY","status":None,"reason":"ALL_43280_TARGET_RAW_ROWS_MATCH_UTC_KICKOFF_CONVERTED_TO_EUROPE_OSLO_AT_MINUTE_PRECISION_NO_GLOBAL_PROVIDER_TIMEZONE_CLAIM"},
        {"gate_id":"REUSABLE_ORDINARY_FT_ADAPTER_PAIR_LINEAGE","outcome":"BLOCKED","status":PRIMARY_STATUS,"reason":"2204_OF_2205_CAPTURE_PAIRS_HAVE_IDENTICAL_RAW_SHA256_AND_THE_FROZEN_REUSABLE_ADAPTER_REQUIRES_DISTINCT_RAW_AND_MANIFEST_LINEAGES"},
        {"gate_id":"REUSABLE_ORDINARY_FT_ADAPTER_HISTORICAL_SCHEMA","outcome":"BLOCKED","status":PRIMARY_STATUS,"reason":"THE_SOLE_DISTINCT_RAW_PAIR_IS_REJECTED_BY_THE_FROZEN_PR89_STRUCTURAL_CHAIN_BECAUSE_HISTORICAL_PAYLOAD_HALFS_KEYS_ESCAPE_THE_REVIEWED_SCHEMA"},
        {"gate_id":"HISTORICAL_RESULT_ROW_MATERIALIZATION","outcome":"NOT_REACHED","status":None,"reason":"PR99_REQUIRES_EVERY_ADMITTED_RESULT_TO_PASS_THE_REUSABLE_ADAPTER_SO_ZERO_HISTORY_ROWS_ARE_AUTHORIZED"},
        {"gate_id":"PR80_CONSTRUCTOR_HANDOFF","outcome":"NOT_REACHED","status":None,"reason":"SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_ARE_NOT_APPROVED"},
    ]
    return {
        "schema_version":1,
        "dataset_name":DATASET_NAME,
        "assessment_scope":ASSESSMENT_SCOPE,
        "assessment_state":ASSESSMENT_STATE,
        "repository_main_anchor":REPOSITORY_MAIN_ANCHOR,
        "protocols":{"pr81":{"canonical_sha256":PR81_SHA256,"canonical_size_bytes":PR81_SIZE},"pr99":{"canonical_sha256":PR99_SHA256,"canonical_size_bytes":PR99_SIZE}},
        "upstream_qualifications":{"pr108_mapping_receipt_sha256":PR108_RECEIPT_SHA256,"pr110_special_result_receipt_sha256":PR110_RECEIPT_SHA256,"pr112_chronology_receipt_sha256":PR112_RECEIPT_SHA256,"pr114_initialization_receipt_sha256":PR114_RECEIPT_SHA256},
        "source_evidence":{"artifact_id":ARTIFACT_ID,"artifact_name":ARTIFACT_NAME,"artifact_sha256":ARTIFACT_SHA256,"artifact_size_bytes":ARTIFACT_SIZE,"research_cache_sha256":CACHE_SHA256,"research_cache_size_bytes":CACHE_SIZE,"request_timezone":"UTC","ccode3":"NGA","start_date":CAMPAIGN_START.isoformat(),"end_date":CAMPAIGN_END.isoformat()},
        "campaign_checks":{
            "request_date_count":EXPECTED_DATE_COUNT,"capture_manifest_count":EXPECTED_CAPTURE_COUNT,
            "distinct_manifest_pair_count":distinct_manifest_pairs,"minimum_pair_separation_microseconds":min(separation_us),
            "maximum_pair_separation_microseconds":max(separation_us),"target_family_fixture_date_pair_count":target_pairs,
            "target_family_raw_capture_row_count":target_raw_rows,"preboundary_ordinary_ft_fixture_date_occurrence_count":preboundary_ordinary,
            "reviewed_ordinary_ft_candidate_count_on_or_after_floor":ordinary_after_floor,"special_state_occurrence_count_on_or_after_floor":special_after_floor,
            "same_date_target_relevant_field_conflict_count":pair_conflicts,"source_display_time_basis":SOURCE_DISPLAY_TIME_BASIS,
            "source_display_time_basis_mismatch_count":time_basis_mismatches,"ordinary_ft_candidates_by_model_league":dict(sorted(by_league.items())),
        },
        "adapter_compatibility":{
            "derived_source_key":DERIVED_SOURCE_KEY,"reviewed_adapter_blob_sha":REVIEWED_ADAPTER_BLOB_SHA,
            "capture_pair_count":EXPECTED_DATE_COUNT,"identical_raw_sha256_pair_count":identical_raw_pairs,
            "distinct_raw_sha256_pair_count":len(distinct_raw_dates),"distinct_raw_sha256_pair_dates":distinct_raw_dates,
            "target_family_fixture_date_pairs_on_distinct_raw_dates":target_pairs_on_distinct_raw_dates,
            "ordinary_ft_candidates_on_or_after_floor_on_distinct_raw_dates":ordinary_on_distinct_raw_dates,
            "ordinary_ft_candidates_blocked_by_identical_raw_lineage_requirement":ordinary_after_floor,
            "identical_raw_exemplar_adapter_status":identical_exemplar_status,"identical_raw_exemplar_error_message":identical_exemplar_message,
            "distinct_raw_pair_adapter_results":distinct_pair_adapter_results,
        },
        "assessment_executed":True,"network_acquisition_performed":False,
        "source_history_adapter_approved":False,"source_history_completeness_proven":False,
        "historical_coverage_proven":False,"history_rows_materialized":0,"ordinary_ft_history_rows_authorized":False,
        "primary_status":PRIMARY_STATUS,"remaining_blockers":[PRIMARY_STATUS,"BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"],
        "gate_results":gates,"next_required_boundary":NEXT_REQUIRED_BOUNDARY,
        "safety":{key:False for key in SAFETY_KEYS},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    receipt = build_receipt(args.artifact)
    raw = canonical(receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    print(f"receipt_sha256={hashlib.sha256(raw).hexdigest()}")
    print(f"receipt_size={len(raw)}")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
