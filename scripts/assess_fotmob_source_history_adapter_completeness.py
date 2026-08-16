#!/usr/bin/env python3
"""Execute the reviewed FotMob source-history adapter/completeness boundary.

This execution is intentionally fail-closed.  It binds the exact PR81/PR99
contracts and the PR108/PR110/PR112/PR114 qualifications to the preserved
PR105/PR101 campaign, then asks whether that campaign can actually satisfy the
already-reviewed reusable ordinary-FT finished-score adapter.

No network acquisition is performed here.  No source/history registry is
mutated, no model feature is constructed, and no betting path is authorized.
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
ASSESSMENT_STATE = "EXECUTED_FAIL_CLOSED_REUSABLE_ADAPTER_PAIR_LINEAGE_INCOMPATIBLE"
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
EXPECTED_DISTINCT_RAW_PAIR_COUNT = 1
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
NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_HISTORICAL_STATIC_CAPTURE_PAIR_LINEAGE_SEMANTICS_PROTOCOL"
)

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
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


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
        schema_version=value["schema_version"],
        dataset_name=value["dataset_name"],
        request_date=value["request_date"],
        timezone=value["timezone"],
        ccode3=value["ccode3"],
        host=value["host"],
        request_target=value["request_target"],
        request_headers=tuple(tuple(item) for item in value["request_headers"]),
        x_mas_included=value["x_mas_included"],
        status=value["status"],
        content_type=value["content_type"],
        content_length=value["content_length"],
        observed_at=parse_utc_timestamp(value["observed_at"], "observed_at"),
        network_acquisition_performed=value["network_acquisition_performed"],
        raw_file_name=value["raw_file_name"],
        raw_sha256=value["raw_sha256"],
        raw_size=value["raw_size"],
        safety=value["safety"],
    )


def safe_extract_cache(artifact: pathlib.Path, destination: pathlib.Path) -> pathlib.Path:
    if artifact.stat().st_size != ARTIFACT_SIZE or sha256_file(artifact) != ARTIFACT_SHA256:
        fail("preserved campaign artifact identity changed")
    with zipfile.ZipFile(artifact) as archive:
        names = set(archive.namelist())
        if "athena-research-cache.tar.gz" not in names:
            fail("preserved campaign cache member is missing")
        cache = archive.read("athena-research-cache.tar.gz")
    if len(cache) != CACHE_SIZE or hashlib.sha256(cache).hexdigest() != CACHE_SHA256:
        fail("preserved campaign research cache identity changed")

    root = destination.resolve()
    with tarfile.open(fileobj=io.BytesIO(cache), mode="r:gz") as tar:
        for member in tar.getmembers():
            target = (root / member.name).resolve()
            if root != target and root not in target.parents:
                fail("campaign cache contains unsafe path traversal")
        tar.extractall(destination)
    captures = destination / ".cache" / "athena-research" / "fotmob-data-matches-captures"
    if not captures.is_dir():
        fail("campaign capture directory is missing")
    return captures


def iter_dates() -> list[str]:
    result: list[str] = []
    current = CAMPAIGN_START
    while current <= CAMPAIGN_END:
        result.append(current.strftime("%Y%m%d"))
        current += dt.timedelta(days=1)
    if len(result) != EXPECTED_DATE_COUNT:
        fail("internal expected campaign date count changed")
    return result


def load_pair(date_dir: pathlib.Path, request_date: str) -> list[tuple[FotMobDataMatchesCaptureManifest, bytes, dict[str, Any], str]]:
    capture_dirs = sorted(path for path in date_dir.iterdir() if path.is_dir())
    if len(capture_dirs) != 2:
        fail(f"{request_date} does not contain exactly two capture directories")
    result = []
    for capture_dir in capture_dirs:
        manifest_path = capture_dir / "manifest.json"
        response_path = capture_dir / "response.json"
        if not manifest_path.is_file() or not response_path.is_file():
            fail(f"{request_date} capture pair is incomplete")
        manifest_raw = manifest_path.read_bytes()
        manifest_value = json.loads(manifest_raw)
        if manifest_raw != canonical(manifest_value):
            fail(f"{request_date} manifest is not canonical JSON")
        manifest = manifest_from_dict(manifest_value)
        response = response_path.read_bytes()
        if manifest.request_date != request_date or manifest.timezone != "UTC" or manifest.ccode3 != "NGA":
            fail(f"{request_date} request identity changed")
        if hashlib.sha256(response).hexdigest() != manifest.raw_sha256 or len(response) != manifest.raw_size:
            fail(f"{request_date} response lineage disagrees with manifest")
        result.append((manifest, response, json.loads(response), hashlib.sha256(manifest_raw).hexdigest()))
    result.sort(key=lambda item: item[0].observed_at)
    return result


def target_index(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    leagues = payload.get("leagues")
    if not isinstance(leagues, list):
        fail("data-matches payload no longer contains leagues list")
    for league in leagues:
        if not isinstance(league, dict):
            fail("data-matches league entry changed shape")
        primary_id = league.get("primaryId")
        model_code = PRIMARY_TO_MODEL.get(primary_id)
        if model_code is None:
            continue
        wrapper_id = league.get("id")
        matches = league.get("matches")
        if type(wrapper_id) is not int or not isinstance(matches, list):
            fail("mapped league wrapper shape changed")
        for match in matches:
            if not isinstance(match, dict):
                fail("mapped match shape changed")
            fixture_id = match.get("id")
            if type(fixture_id) is not int or fixture_id < 1 or fixture_id in result:
                fail("mapped fixture identity is invalid or duplicated within one response")
            status = match.get("status")
            home = match.get("home")
            away = match.get("away")
            if not all(isinstance(item, dict) for item in (status, home, away)):
                fail("mapped match components changed shape")
            if match.get("leagueId") != wrapper_id:
                fail("match leagueId no longer agrees with mapped wrapper")
            kickoff_text = status.get("utcTime")
            display_time = match.get("time")
            if not isinstance(kickoff_text, str) or not isinstance(display_time, str):
                fail("mapped fixture kickoff fields are missing")
            kickoff = parse_utc_timestamp(kickoff_text, "kickoff_utc")
            try:
                source_local = dt.datetime.strptime(display_time, "%d.%m.%Y %H:%M")
            except ValueError as exc:
                raise AssessmentError("mapped source display time format changed") from exc
            oslo = kickoff.astimezone(ZoneInfo(SOURCE_DISPLAY_TIME_BASIS)).replace(
                tzinfo=None, second=0, microsecond=0
            )
            result[fixture_id] = {
                "fixture_id": fixture_id,
                "model_league_code": model_code,
                "primary_id": primary_id,
                "wrapper_league_id": wrapper_id,
                "home_team_id": home.get("id"),
                "away_team_id": away.get("id"),
                "home_score": home.get("score"),
                "away_score": away.get("score"),
                "home_pen_score_present": "penScore" in home,
                "away_pen_score_present": "penScore" in away,
                "kickoff_utc": kickoff,
                "kickoff_text": kickoff_text,
                "source_local": source_local,
                "source_local_matches_oslo": source_local == oslo,
                "finished": status.get("finished"),
                "started": status.get("started"),
                "cancelled": status.get("cancelled"),
                "awarded": status.get("awarded"),
                "reason": status.get("reason"),
            }
    return result


def relevant_tuple(item: dict[str, Any]) -> tuple[Any, ...]:
    reason = item["reason"]
    reason_tuple = None
    if isinstance(reason, dict):
        reason_tuple = tuple((key, reason.get(key)) for key in ("short", "shortKey", "long", "longKey"))
    return (
        item["model_league_code"],
        item["primary_id"],
        item["wrapper_league_id"],
        item["home_team_id"],
        item["away_team_id"],
        item["kickoff_text"],
        item["source_local"].isoformat(),
        item["home_score"],
        item["away_score"],
        item["home_pen_score_present"],
        item["away_pen_score_present"],
        item["finished"],
        item["started"],
        item["cancelled"],
        item["awarded"],
        reason_tuple,
    )


def is_potential_ordinary(item: dict[str, Any]) -> bool:
    return (
        item["finished"] is True
        and item["started"] is True
        and item["cancelled"] is False
        and item["awarded"] in (None, False)
        and item["reason"] == ORDINARY_REASON
        and type(item["home_score"]) is int
        and item["home_score"] >= 0
        and type(item["away_score"]) is int
        and item["away_score"] >= 0
        and not item["home_pen_score_present"]
        and not item["away_pen_score_present"]
    )


def verify_upstream() -> dict[str, Any]:
    p81 = pr81.build_prospective_successor_source_history_completeness_protocol()
    p81_raw = pr81.canonical_prospective_successor_source_history_completeness_protocol_bytes(p81)
    if (hashlib.sha256(p81_raw).hexdigest(), len(p81_raw)) != (PR81_SHA256, PR81_SIZE):
        fail("PR81 source-history protocol identity changed")

    p99 = pr99.build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol()
    p99_raw = pr99.canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol_bytes(p99)
    if (hashlib.sha256(p99_raw).hexdigest(), len(p99_raw)) != (PR99_SHA256, PR99_SIZE):
        fail("PR99 derived-source completeness protocol identity changed")

    receipts = {}
    for label, module, expected_sha, expected_size in (
        ("pr108", pr108, PR108_RECEIPT_SHA256, PR108_RECEIPT_SIZE),
        ("pr110", pr110, PR110_RECEIPT_SHA256, PR110_RECEIPT_SIZE),
        ("pr112", pr112, PR112_RECEIPT_SHA256, PR112_RECEIPT_SIZE),
        ("pr114", pr114, PR114_RECEIPT_SHA256, PR114_RECEIPT_SIZE),
    ):
        receipt = exact_json(module.RECEIPT_PATH, expected_sha, expected_size)
        receipts[label] = receipt

    if receipts["pr108"].get("mapping_qualification_proven") is not True:
        fail("PR108 competition mapping is no longer qualified")
    if receipts["pr110"].get("special_result_semantics_qualified") is not True:
        fail("PR110 special-result semantics are no longer qualified")
    if receipts["pr112"].get("rearrangement_chronology_qualified") is not True:
        fail("PR112 chronology is no longer qualified")
    if receipts["pr114"].get("initialization_boundary_qualified") is not True:
        fail("PR114 initialization boundary is no longer qualified")
    if receipts["pr114"].get("remaining_blockers") != ["BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"]:
        fail("PR114 remaining-blocker ancestry changed")
    return receipts


def build_receipt(artifact: pathlib.Path) -> dict[str, Any]:
    receipts = verify_upstream()
    with tempfile.TemporaryDirectory(prefix="athena-pr115-") as temp:
        captures_root = safe_extract_cache(artifact, pathlib.Path(temp))
        expected_dates = iter_dates()
        actual_dates = sorted(path.name for path in captures_root.iterdir() if path.is_dir())
        if actual_dates != expected_dates:
            fail("campaign daily date coverage is not exact and contiguous")

        identical_raw_pair_count = 0
        distinct_raw_pair_dates: list[str] = []
        distinct_manifest_pair_count = 0
        separation_us: list[int] = []
        pair_conflict_count = 0
        source_local_basis_mismatch_count = 0
        target_pair_count = 0
        target_raw_rows = 0
        preboundary_ordinary = 0
        ordinary_on_or_after_floor = 0
        special_on_or_after_floor = 0
        compatible_target_pair_count = 0
        compatible_ordinary_on_or_after_floor = 0
        potential_ordinary_by_league: Counter[str] = Counter()
        exemplar_adapter_status: str | None = None
        distinct_pair_adapter_results: list[dict[str, Any]] = []
        first_identical_pair: tuple[bytes, FotMobDataMatchesCaptureManifest, bytes, FotMobDataMatchesCaptureManifest] | None = None

        for request_date in expected_dates:
            pair = load_pair(captures_root / request_date, request_date)
            first_manifest, first_raw, first_payload, first_manifest_file_sha = pair[0]
            second_manifest, second_raw, second_payload, second_manifest_file_sha = pair[1]
            if sha256_data_matches_capture_manifest(first_manifest) != first_manifest_file_sha:
                fail("first manifest file/hash canonical lineage changed")
            if sha256_data_matches_capture_manifest(second_manifest) != second_manifest_file_sha:
                fail("second manifest file/hash canonical lineage changed")
            if first_manifest_file_sha == second_manifest_file_sha:
                fail("capture pair unexpectedly reuses one manifest lineage")
            distinct_manifest_pair_count += 1
            delta = second_manifest.observed_at - first_manifest.observed_at
            microseconds = int(delta.total_seconds() * 1_000_000)
            if second_manifest.observed_at <= first_manifest.observed_at or microseconds < 300_000_000:
                fail("capture pair observation order/separation violates frozen acquisition protocol")
            separation_us.append(microseconds)

            raw_identical = first_manifest.raw_sha256 == second_manifest.raw_sha256
            if raw_identical:
                identical_raw_pair_count += 1
                if first_identical_pair is None:
                    first_identical_pair = (first_raw, first_manifest, second_raw, second_manifest)
            else:
                distinct_raw_pair_dates.append(request_date)

            first_index = target_index(first_payload)
            second_index = target_index(second_payload)
            if set(first_index) != set(second_index):
                pair_conflict_count += 1
                fail(f"{request_date} target fixture membership differs across capture pair")
            for fixture_id in sorted(first_index):
                first_item = first_index[fixture_id]
                second_item = second_index[fixture_id]
                target_pair_count += 1
                target_raw_rows += 2
                if relevant_tuple(first_item) != relevant_tuple(second_item):
                    pair_conflict_count += 1
                    fail(f"{request_date}/{fixture_id} target relevant fields conflict")
                if not first_item["source_local_matches_oslo"] or not second_item["source_local_matches_oslo"]:
                    source_local_basis_mismatch_count += 1
                ordinary = is_potential_ordinary(first_item)
                floor = MODEL_FLOORS[first_item["model_league_code"]]
                kickoff_date = first_item["kickoff_utc"].date().isoformat()
                if ordinary and kickoff_date < floor:
                    preboundary_ordinary += 1
                elif ordinary:
                    ordinary_on_or_after_floor += 1
                    potential_ordinary_by_league[first_item["model_league_code"]] += 1
                    if not raw_identical:
                        compatible_ordinary_on_or_after_floor += 1
                else:
                    special_on_or_after_floor += 1
                if not raw_identical:
                    compatible_target_pair_count += 1

            if not raw_identical:
                adapter_result = reviewed_adapter.adapt_fotmob_data_matches_ordinary_ft_finished_scores(
                    first_raw,
                    first_manifest,
                    second_raw,
                    second_manifest,
                )
                distinct_pair_adapter_results.append(
                    {
                        "request_date": request_date,
                        "pair_status": adapter_result.pair_status.value,
                        "terminal_candidate_union_count": adapter_result.terminal_candidate_union_count,
                        "qualified_count": adapter_result.qualified_count,
                        "adapter_result_sha256": reviewed_adapter.sha256_fotmob_data_matches_ordinary_ft_finished_score_adapter_result(adapter_result),
                    }
                )

        if first_identical_pair is None:
            fail("expected an identical-raw historical capture pair exemplar")
        try:
            reviewed_adapter.adapt_fotmob_data_matches_ordinary_ft_finished_scores(*first_identical_pair)
        except reviewed_adapter.FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError as exc:
            exemplar_adapter_status = exc.status.value
        else:
            fail("frozen reusable adapter unexpectedly accepted an identical-raw capture pair")

    if target_pair_count != EXPECTED_TARGET_PAIR_COUNT or target_raw_rows != EXPECTED_TARGET_RAW_ROW_COUNT:
        fail("target-family campaign accounting changed")
    if preboundary_ordinary != EXPECTED_PREBOUNDARY_ORDINARY:
        fail("pre-boundary ordinary-FT count changed")
    if ordinary_on_or_after_floor != EXPECTED_ORDINARY_ON_OR_AFTER_FLOOR:
        fail("ordinary-FT candidate count on/after family floors changed")
    if special_on_or_after_floor != EXPECTED_SPECIAL_ON_OR_AFTER_FLOOR:
        fail("special-state occurrence count on/after family floors changed")
    if target_pair_count != preboundary_ordinary + ordinary_on_or_after_floor + special_on_or_after_floor:
        fail("target-family accounting no longer closes exactly")
    if identical_raw_pair_count != EXPECTED_IDENTICAL_RAW_PAIR_COUNT:
        fail("identical-raw capture-pair count changed")
    if len(distinct_raw_pair_dates) != EXPECTED_DISTINCT_RAW_PAIR_COUNT or tuple(distinct_raw_pair_dates) != EXPECTED_DISTINCT_RAW_PAIR_DATES:
        fail("distinct-raw capture-pair membership changed")
    if distinct_manifest_pair_count != EXPECTED_DATE_COUNT:
        fail("manifest lineage distinctness changed")
    if pair_conflict_count != 0 or source_local_basis_mismatch_count != 0:
        fail("target-family stability or source display-time relation changed")
    if compatible_target_pair_count != 0 or compatible_ordinary_on_or_after_floor != 0:
        fail("the sole adapter-compatible raw pair unexpectedly contains a frozen target-family row")
    if exemplar_adapter_status != reviewed_adapter.AdapterPairStatus.BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY.value:
        fail("identical-raw exemplar no longer fails at the frozen adapter lineage gate")

    expected_by_league = {row[0]: row[5] for row in pr114.EXPECTED_FAMILY_SUMMARY}
    if dict(sorted(potential_ordinary_by_league.items())) != dict(sorted(expected_by_league.items())):
        fail("per-league ordinary-FT candidate counts changed from PR114")

    safety = {key: False for key in SAFETY_KEYS}
    gates = [
        {
            "gate_id": "DERIVED_SCORE_CAPABILITY",
            "outcome": "PASSED",
            "status": None,
            "reason": "PR99_DERIVED_SOURCE_REVALIDATES_SCOPED_ORDINARY_FT_FINISHED_SCORE_AND_FIXTURE_IDENTITY",
        },
        {
            "gate_id": "REQUIRED_DAILY_CAPTURE_COVERAGE",
            "outcome": "PASSED",
            "status": None,
            "reason": "ALL_2205_UTC_REQUEST_DATES_HAVE_EXACTLY_TWO_VALID_NGA_CAPTURE_MANIFESTS_WITH_REQUIRED_SEPARATION",
        },
        {
            "gate_id": "ELEVEN_LEAGUE_MAPPING",
            "outcome": "PASSED",
            "status": None,
            "reason": "PR108_QUALIFIED_ALL_ELEVEN_SOURCE_SCOPED_PRIMARY_ID_COMPETITION_FAMILIES",
        },
        {
            "gate_id": "NON_ORDINARY_RESULT_DISPOSITION",
            "outcome": "PASSED",
            "status": None,
            "reason": "PR110_QUALIFIED_SPECIAL_RESULT_SEMANTICS_AND_PRESERVATION_DISPOSITIONS",
        },
        {
            "gate_id": "IDENTITY_AND_REARRANGEMENT_CHRONOLOGY",
            "outcome": "PASSED",
            "status": None,
            "reason": "PR112_QUALIFIED_THE_EXACT_250_REARRANGED_SOURCE_FIXTURE_LINEAGES",
        },
        {
            "gate_id": "ELO_INITIALIZATION_BOUNDARY",
            "outcome": "PASSED",
            "status": None,
            "reason": "PR114_QUALIFIED_PR69_EQUIVALENT_EMPTY_1500_INITIALIZATION_FLOORS_FOR_ALL_ELEVEN_FAMILIES",
        },
        {
            "gate_id": "SOURCE_DISPLAY_TIME_BASIS",
            "outcome": "PASSED_FOR_FROZEN_CORPUS_ONLY",
            "status": None,
            "reason": "ALL_43280_TARGET_RAW_ROWS_MATCH_UTC_KICKOFF_CONVERTED_TO_EUROPE_OSLO_AT_MINUTE_PRECISION_NO_GLOBAL_PROVIDER_TIMEZONE_CLAIM",
        },
        {
            "gate_id": "REUSABLE_ORDINARY_FT_ADAPTER_PAIR_LINEAGE",
            "outcome": "BLOCKED",
            "status": PRIMARY_STATUS,
            "reason": "2204_OF_2205_HISTORICAL_CAPTURE_PAIRS_HAVE_BYTE_IDENTICAL_RAW_RESPONSES_AND_THE_FROZEN_REUSABLE_ADAPTER_REQUIRES_DISTINCT_RAW_SHA256_LINEAGES",
        },
        {
            "gate_id": "HISTORICAL_RESULT_ROW_MATERIALIZATION",
            "outcome": "NOT_REACHED",
            "status": None,
            "reason": "PR99_REQUIRES_EVERY_ADMITTED_RESULT_TO_PASS_THE_REUSABLE_ADAPTER_SO_ZERO_HISTORY_ROWS_ARE_AUTHORIZED_WHILE_PAIR_LINEAGE_GATE_IS_BLOCKED",
        },
        {
            "gate_id": "PR80_CONSTRUCTOR_HANDOFF",
            "outcome": "NOT_REACHED",
            "status": None,
            "reason": "SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_ARE_NOT_APPROVED",
        },
    ]

    return {
        "schema_version": 1,
        "dataset_name": DATASET_NAME,
        "assessment_scope": ASSESSMENT_SCOPE,
        "assessment_state": ASSESSMENT_STATE,
        "repository_main_anchor": REPOSITORY_MAIN_ANCHOR,
        "protocols": {
            "pr81": {"canonical_sha256": PR81_SHA256, "canonical_size_bytes": PR81_SIZE},
            "pr99": {"canonical_sha256": PR99_SHA256, "canonical_size_bytes": PR99_SIZE},
        },
        "upstream_qualifications": {
            "pr108_mapping_receipt_sha256": PR108_RECEIPT_SHA256,
            "pr110_special_result_receipt_sha256": PR110_RECEIPT_SHA256,
            "pr112_chronology_receipt_sha256": PR112_RECEIPT_SHA256,
            "pr114_initialization_receipt_sha256": PR114_RECEIPT_SHA256,
        },
        "source_evidence": {
            "artifact_id": ARTIFACT_ID,
            "artifact_name": ARTIFACT_NAME,
            "artifact_sha256": ARTIFACT_SHA256,
            "artifact_size_bytes": ARTIFACT_SIZE,
            "research_cache_sha256": CACHE_SHA256,
            "research_cache_size_bytes": CACHE_SIZE,
            "request_timezone": "UTC",
            "ccode3": "NGA",
            "start_date": CAMPAIGN_START.isoformat(),
            "end_date": CAMPAIGN_END.isoformat(),
        },
        "campaign_checks": {
            "request_date_count": EXPECTED_DATE_COUNT,
            "capture_manifest_count": EXPECTED_CAPTURE_COUNT,
            "distinct_manifest_pair_count": distinct_manifest_pair_count,
            "minimum_pair_separation_microseconds": min(separation_us),
            "maximum_pair_separation_microseconds": max(separation_us),
            "target_family_fixture_date_pair_count": target_pair_count,
            "target_family_raw_capture_row_count": target_raw_rows,
            "preboundary_ordinary_ft_fixture_date_occurrence_count": preboundary_ordinary,
            "reviewed_ordinary_ft_candidate_count_on_or_after_floor": ordinary_on_or_after_floor,
            "special_state_occurrence_count_on_or_after_floor": special_on_or_after_floor,
            "same_date_target_relevant_field_conflict_count": pair_conflict_count,
            "source_display_time_basis": SOURCE_DISPLAY_TIME_BASIS,
            "source_display_time_basis_mismatch_count": source_local_basis_mismatch_count,
            "ordinary_ft_candidates_by_model_league": dict(sorted(potential_ordinary_by_league.items())),
        },
        "adapter_pair_compatibility": {
            "derived_source_key": DERIVED_SOURCE_KEY,
            "reviewed_adapter_blob_sha": REVIEWED_ADAPTER_BLOB_SHA,
            "frozen_adapter_requires_distinct_raw_sha256": True,
            "capture_pair_count": EXPECTED_DATE_COUNT,
            "identical_raw_sha256_pair_count": identical_raw_pair_count,
            "distinct_raw_sha256_pair_count": len(distinct_raw_pair_dates),
            "distinct_raw_sha256_pair_dates": distinct_raw_pair_dates,
            "target_family_fixture_date_pairs_on_distinct_raw_dates": compatible_target_pair_count,
            "ordinary_ft_candidates_on_or_after_floor_on_distinct_raw_dates": compatible_ordinary_on_or_after_floor,
            "ordinary_ft_candidates_blocked_by_pair_lineage_requirement": ordinary_on_or_after_floor,
            "identical_raw_exemplar_adapter_status": exemplar_adapter_status,
            "distinct_raw_pair_adapter_results": distinct_pair_adapter_results,
        },
        "assessment_executed": True,
        "network_acquisition_performed": False,
        "source_history_adapter_approved": False,
        "source_history_completeness_proven": False,
        "historical_coverage_proven": False,
        "history_rows_materialized": 0,
        "ordinary_ft_history_rows_authorized": False,
        "primary_status": PRIMARY_STATUS,
        "remaining_blockers": [PRIMARY_STATUS, "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"],
        "gate_results": gates,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": safety,
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
