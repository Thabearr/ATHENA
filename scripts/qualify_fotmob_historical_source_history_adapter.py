#!/usr/bin/env python3
"""Execute PR #117 against the exact preserved FotMob historical campaign only."""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import io
import json
import pathlib
import tarfile
import tempfile
import zipfile
from typing import Any
from zoneinfo import ZoneInfo

import domain.fotmob_historical_source_history_adapter_protocol as pr116
import domain.fotmob_source_history_adapter_completeness_assessment as pr115
import domain.fotmob_source_history_elo_initialization_boundary_qualification as pr114
import domain.fotmob_source_history_rearrangement_chronology_qualification as pr112
import domain.fotmob_source_history_special_result_semantics_protocol as pr109
import domain.fotmob_source_history_special_result_semantics_qualification as pr110
from domain.fotmob_data_matches_capture import (
    FotMobDataMatchesCaptureManifest,
    parse_utc_timestamp,
    sha256_data_matches_capture_manifest,
)

REPOSITORY_MAIN_ANCHOR = "cbebb42393be50c77011463906b5d2b70e0ef2c5"
PR116_PROTOCOL_BLOB_SHA = "53682e3810bf3c06b1afc90b847361b6dcb3e04f"
EXPECTED_RECEIPT_SHA256 = "a8f06a9d789b20b4ef49766bd771fb5c4d13c4be657ac6a5fc8f284701054020"
EXPECTED_RECEIPT_SIZE = 5_081
ORDINARY_FT_PROJECTION_SHA256 = "eddb7f5b58eb3cb92087dc7bf57a45a270aebabce38641cd3b4ffc2277d67ed3"
ORDINARY_FT_PROJECTION_SIZE = 22_080_831
NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_AND_MATERIALIZATION_PROTOCOL"
)

ARTIFACT_ID = 9_249_856_559
ARTIFACT_NAME = "fotmob-ordinary-ft-source-history-campaign-31887523012"
ARTIFACT_SHA256 = "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
ARTIFACT_SIZE = 61_886_753
CACHE_MEMBER = "athena-research-cache.tar.gz"
CACHE_SHA256 = "cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6"
CACHE_SIZE = 61_881_610
EXPECTED_DATE_COUNT = 2_205
EXPECTED_CAPTURE_COUNT = 4_410
EXPECTED_TARGET_PAIR_COUNT = 21_640
EXPECTED_ORDINARY_COUNT = 21_336
EXPECTED_SPECIAL_COUNT = 304
EXPECTED_PREBOUNDARY_COUNT = 10
EXPECTED_ON_OR_AFTER_FLOOR_COUNT = 21_326
EXPECTED_IDENTICAL_RAW_PAIR_COUNT = 2_204
EXPECTED_DISTINCT_RAW_PAIR_DATES = ("20250712",)
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

PRIMARY_TO_MODEL = {primary_id: model_code for model_code, primary_id in pr116.TARGET_COMPETITION_FAMILIES}
MODEL_FLOORS = dict(pr114.EXPECTED_FLOORS)
ORDINARY_REASON = dict(pr116.ORDINARY_FT_REASON_TUPLE)
SAFETY_KEYS = (
    "bet_authorized",
    "calibration_for_production_authorized",
    "expected_goals_production_authorized",
    "expected_goals_transform_approved",
    "history_rows_materialization_authorized",
    "market_activation_authorized",
    "model_training_authorized",
    "ordinary_ft_history_rows_authorized",
    "pr80_constructor_input_authorized",
    "pricing_authorized",
    "probability_adjustment_authorized",
    "probability_inference_authorized",
    "production_approval_authorized",
    "score_matrix_authorized",
    "selection_authorized",
    "source_capability_registry_mutation_authorized",
    "source_history_adapter_approved",
    "source_history_completeness_proven",
    "successor_candidate_approved",
    "successor_live_inputs_qualified",
)


class QualificationError(RuntimeError):
    """Raised when the exact PR #117 qualification cannot be reproduced."""


def fail(message: str) -> None:
    raise QualificationError(message)


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        cache = archive.read(CACHE_MEMBER)
    if len(cache) != CACHE_SIZE or hashlib.sha256(cache).hexdigest() != CACHE_SHA256:
        fail("preserved campaign research-cache identity changed")
    root = destination.resolve()
    with tarfile.open(fileobj=io.BytesIO(cache), mode="r:gz") as archive:
        for member in archive.getmembers():
            target = (root / member.name).resolve()
            if target != root and root not in target.parents:
                fail("campaign cache contains unsafe path traversal")
        archive.extractall(destination, filter="data")
    captures = destination / ".cache" / "athena-research" / "fotmob-data-matches-captures"
    if not captures.is_dir():
        fail("campaign capture directory is missing")
    return captures


def required_dates() -> list[str]:
    start = dt.date(2020, 8, 1)
    end = dt.date(2026, 8, 14)
    result: list[str] = []
    current = start
    while current <= end:
        result.append(current.strftime("%Y%m%d"))
        current += dt.timedelta(days=1)
    if len(result) != EXPECTED_DATE_COUNT:
        fail("internal required-date count changed")
    return result


def load_pair(
    date_dir: pathlib.Path,
    request_date: str,
) -> list[tuple[str, FotMobDataMatchesCaptureManifest, str, bytes, dict[str, Any]]]:
    capture_dirs = sorted(path for path in date_dir.iterdir() if path.is_dir())
    if len(capture_dirs) != 2:
        fail(f"{request_date} does not contain exactly two captures")
    result = []
    for capture_dir in capture_dirs:
        manifest_raw = (capture_dir / "manifest.json").read_bytes()
        response_raw = (capture_dir / "response.json").read_bytes()
        try:
            manifest_value = json.loads(manifest_raw)
            payload = json.loads(response_raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise QualificationError(f"{request_date} capture JSON is malformed") from exc
        if not isinstance(manifest_value, dict) or manifest_raw != canonical(manifest_value):
            fail(f"{request_date} manifest is not exact canonical JSON")
        manifest = manifest_from_dict(manifest_value)
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        if sha256_data_matches_capture_manifest(manifest) != manifest_sha:
            fail(f"{request_date} manifest canonical lineage changed")
        if (manifest.request_date, manifest.timezone, manifest.ccode3) != (request_date, "UTC", "NGA"):
            fail(f"{request_date} request identity changed")
        if manifest.network_acquisition_performed is not True:
            fail(f"{request_date} manifest is not a real network acquisition")
        if hashlib.sha256(response_raw).hexdigest() != manifest.raw_sha256 or len(response_raw) != manifest.raw_size:
            fail(f"{request_date} raw bytes do not match manifest lineage")
        if not isinstance(payload, dict):
            fail(f"{request_date} response root changed")
        result.append((capture_dir.name, manifest, manifest_sha, response_raw, payload))
    result.sort(key=lambda item: item[1].observed_at)
    return result


def target_index(payload: dict[str, Any]) -> dict[int, tuple[str, int, int, dict[str, Any]]]:
    leagues = payload.get("leagues")
    if not isinstance(leagues, list):
        fail("payload leagues shape changed")
    result: dict[int, tuple[str, int, int, dict[str, Any]]] = {}
    for league in leagues:
        if not isinstance(league, dict):
            fail("league shape changed")
        primary_id = league.get("primaryId")
        model_code = PRIMARY_TO_MODEL.get(primary_id)
        if model_code is None:
            continue
        wrapper_id = league.get("id")
        matches = league.get("matches")
        if type(primary_id) is not int or type(wrapper_id) is not int or wrapper_id < 1 or not isinstance(matches, list):
            fail("mapped competition shape changed")
        for match in matches:
            if not isinstance(match, dict):
                fail("mapped match shape changed")
            fixture_id = match.get("id")
            if type(fixture_id) is not int or fixture_id < 1 or fixture_id in result:
                fail("mapped fixture identity changed")
            if match.get("leagueId") != wrapper_id:
                fail("mapped fixture wrapper identity changed")
            result[fixture_id] = (model_code, primary_id, wrapper_id, match)
    return result


def relevant_tuple(model_code: str, primary_id: int, wrapper_id: int, match: dict[str, Any]) -> tuple[Any, ...]:
    status, home, away = match.get("status"), match.get("home"), match.get("away")
    if not all(isinstance(item, dict) for item in (status, home, away)):
        fail("target match identity/status shape changed")
    return (
        model_code,
        primary_id,
        wrapper_id,
        match.get("id"),
        match.get("leagueId"),
        home.get("id"),
        away.get("id"),
        status.get("utcTime"),
        match.get("time"),
        home.get("score"),
        away.get("score"),
        "penScore" in home,
        home.get("penScore"),
        "penScore" in away,
        away.get("penScore"),
        status.get("finished"),
        status.get("started"),
        status.get("cancelled"),
        "awarded" in status,
        status.get("awarded"),
        status.get("reason"),
        status.get("halfs"),
    )


def special_state(match: dict[str, Any]) -> str | None:
    status = match.get("status")
    if not isinstance(status, dict) or not isinstance(status.get("reason"), dict):
        return None
    reason = status["reason"]
    awarded = status.get("awarded", "ABSENT")
    for row in pr109.STATE_SPECS:
        (
            state_id,
            short,
            short_key,
            long,
            long_key,
            finished,
            started,
            cancelled,
            awarded_rule,
            _,
        ) = row
        if (
            reason.get("short"),
            reason.get("shortKey"),
            reason.get("long"),
            reason.get("longKey"),
            status.get("finished"),
            status.get("started"),
            status.get("cancelled"),
        ) != (short, short_key, long, long_key, finished, started, cancelled):
            continue
        if awarded_rule == "EXACT_TRUE" and awarded is True:
            return state_id
        if awarded_rule == "EXACT_FALSE" and awarded is False:
            return state_id
        if awarded_rule == "ABSENT_OR_FALSE" and (awarded == "ABSENT" or awarded is False):
            return state_id
    return None


def is_ordinary_ft(match: dict[str, Any]) -> bool:
    status, home, away = match.get("status"), match.get("home"), match.get("away")
    if not all(isinstance(item, dict) for item in (status, home, away)):
        return False
    awarded = status.get("awarded", "ABSENT")
    return (
        status.get("finished") is True
        and status.get("started") is True
        and status.get("cancelled") is False
        and (awarded == "ABSENT" or awarded is False)
        and status.get("reason") == ORDINARY_REASON
        and type(home.get("score")) is int
        and home["score"] >= 0
        and type(away.get("score")) is int
        and away["score"] >= 0
        and "penScore" not in home
        and "penScore" not in away
    )


def parse_utc(value: Any) -> dt.datetime:
    if not isinstance(value, str):
        fail("target kickoff UTC is not a string")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QualificationError("target kickoff UTC is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        fail("target kickoff UTC is not timezone-aware")
    return parsed.astimezone(dt.timezone.utc)


def verify_upstream() -> None:
    protocol = pr116.build_fotmob_historical_source_history_adapter_protocol()
    protocol_raw = pr116.canonical_fotmob_historical_source_history_adapter_protocol_bytes(protocol)
    if (hashlib.sha256(protocol_raw).hexdigest(), len(protocol_raw)) != (
        pr116.PROTOCOL_SHA256,
        pr116.PROTOCOL_SIZE,
    ):
        fail("PR116 protocol identity changed")
    r110 = pr110.load_fotmob_source_history_special_result_semantics_qualification_receipt()
    if r110.get("special_result_semantics_qualified") is not True:
        fail("PR110 special-result qualification changed")
    r112 = pr112.load_fotmob_source_history_rearrangement_chronology_qualification_receipt()
    if r112.get("rearrangement_chronology_qualified") is not True:
        fail("PR112 chronology qualification changed")
    r114 = pr114.load_fotmob_source_history_elo_initialization_boundary_qualification_receipt()
    if r114.get("initialization_boundary_qualified") is not True:
        fail("PR114 initialization qualification changed")
    r115 = pr115.load_fotmob_source_history_adapter_completeness_assessment_receipt()
    if r115.get("primary_status") != "BLOCKED_RESULT_EVIDENCE_GAP":
        fail("PR115 fail-closed premise changed")
    if r115.get("history_rows_materialized") != 0:
        fail("PR115 unexpectedly materialized history rows")


def build_receipt(
    artifact: pathlib.Path,
    projection_output: pathlib.Path | None = None,
) -> dict[str, Any]:
    verify_upstream()
    expected_dates = required_dates()
    identical_raw_pairs = 0
    distinct_raw_dates: list[str] = []
    distinct_manifest_pairs = 0
    pair_separation_us: list[int] = []
    target_pair_count = 0
    target_pairs_on_distinct_raw_dates = 0
    ordinary_count = 0
    special_count = 0
    preboundary_count = 0
    on_or_after_floor_count = 0
    ordinary_by_league: collections.Counter[str] = collections.Counter()
    special_counts: collections.Counter[str] = collections.Counter()
    ordinary_ids: collections.Counter[int] = collections.Counter()
    pair_conflict_count = 0
    display_time_mismatch_count = 0
    halfs_keyset_mismatch_count = 0
    halfs_type_mismatch_count = 0
    halfs_parse_mismatch_count = 0
    unreviewed_target_state_count = 0
    projection_records: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="athena-pr117-") as temp:
        captures_root = safe_extract_cache(artifact, pathlib.Path(temp))
        actual_dates = sorted(path.name for path in captures_root.iterdir() if path.is_dir())
        if actual_dates != expected_dates:
            fail("campaign daily coverage changed")

        for request_date in expected_dates:
            pair = load_pair(captures_root / request_date, request_date)
            first_capture_id, first_manifest, first_manifest_sha, _, first_payload = pair[0]
            second_capture_id, second_manifest, second_manifest_sha, _, second_payload = pair[1]
            if first_manifest_sha == second_manifest_sha:
                fail("historical pair reused one manifest lineage")
            distinct_manifest_pairs += 1
            separation_us = int((second_manifest.observed_at - first_manifest.observed_at).total_seconds() * 1_000_000)
            if second_manifest.observed_at <= first_manifest.observed_at or separation_us < 300_000_000:
                fail("historical pair observation separation changed")
            pair_separation_us.append(separation_us)
            raw_identical = first_manifest.raw_sha256 == second_manifest.raw_sha256
            if raw_identical:
                identical_raw_pairs += 1
            else:
                distinct_raw_dates.append(request_date)

            first_index = target_index(first_payload)
            second_index = target_index(second_payload)
            if set(first_index) != set(second_index):
                fail(f"{request_date} target fixture membership changed across the pair")

            for fixture_id in sorted(first_index):
                model_code, primary_id, wrapper_id, match = first_index[fixture_id]
                model_code_b, primary_id_b, wrapper_id_b, match_b = second_index[fixture_id]
                target_pair_count += 1
                if relevant_tuple(model_code, primary_id, wrapper_id, match) != relevant_tuple(
                    model_code_b, primary_id_b, wrapper_id_b, match_b
                ):
                    pair_conflict_count += 1
                    fail(f"{request_date}/{fixture_id} target-relevant field conflict")
                if not raw_identical:
                    target_pairs_on_distinct_raw_dates += 1

                status, home, away = match["status"], match["home"], match["away"]
                if (
                    type(home.get("id")) is not int
                    or home["id"] < 1
                    or type(away.get("id")) is not int
                    or away["id"] < 1
                ):
                    fail("target team identity changed")
                kickoff = parse_utc(status.get("utcTime"))
                display_time = match.get("time")
                if not isinstance(display_time, str):
                    fail("source display-time field changed")
                try:
                    source_local = dt.datetime.strptime(display_time, "%d.%m.%Y %H:%M")
                except ValueError as exc:
                    raise QualificationError("source display-time format changed") from exc
                oslo = kickoff.astimezone(ZoneInfo("Europe/Oslo")).replace(
                    tzinfo=None, second=0, microsecond=0
                )
                if source_local != oslo:
                    display_time_mismatch_count += 1
                    fail("source display-time corroboration changed")

                if is_ordinary_ft(match):
                    ordinary_count += 1
                    ordinary_ids[fixture_id] += 1
                    halves = status.get("halfs")
                    if not isinstance(halves, dict) or set(halves) != {
                        "firstHalfStarted",
                        "secondHalfStarted",
                    }:
                        halfs_keyset_mismatch_count += 1
                        fail("historical ordinary-FT status.halfs keyset changed")
                    for key in ("firstHalfStarted", "secondHalfStarted"):
                        value = halves.get(key)
                        if type(value) is not str:
                            halfs_type_mismatch_count += 1
                            fail("historical ordinary-FT status.halfs type changed")
                        try:
                            dt.datetime.strptime(value, "%d.%m.%Y %H:%M:%S")
                        except ValueError as exc:
                            halfs_parse_mismatch_count += 1
                            raise QualificationError(
                                "historical ordinary-FT status.halfs format changed"
                            ) from exc

                    floor = MODEL_FLOORS[model_code]
                    if kickoff.date().isoformat() < floor:
                        disposition = "BEFORE_PR114_ELO_INITIALIZATION_FLOOR"
                        preboundary_count += 1
                    else:
                        disposition = "ON_OR_AFTER_PR114_ELO_INITIALIZATION_FLOOR"
                        on_or_after_floor_count += 1
                        ordinary_by_league[model_code] += 1
                    projection_records.append(
                        {
                            "request_date": request_date,
                            "fixture_id": fixture_id,
                            "model_league_code": model_code,
                            "primary_id": primary_id,
                            "wrapper_league_id": wrapper_id,
                            "kickoff_utc": status["utcTime"],
                            "home_team_id": home["id"],
                            "away_team_id": away["id"],
                            "home_score": home["score"],
                            "away_score": away["score"],
                            "reason": dict(ORDINARY_REASON),
                            "first_capture_id": first_capture_id,
                            "second_capture_id": second_capture_id,
                            "first_manifest_sha256": first_manifest_sha,
                            "second_manifest_sha256": second_manifest_sha,
                            "first_raw_sha256": first_manifest.raw_sha256,
                            "second_raw_sha256": second_manifest.raw_sha256,
                            "first_observed_at": first_manifest.observed_at.isoformat().replace("+00:00", "Z"),
                            "second_observed_at": second_manifest.observed_at.isoformat().replace("+00:00", "Z"),
                            "raw_content_relation": "BYTE_IDENTICAL" if raw_identical else "DISTINCT",
                            "elo_initialization_floor_source_local_date": floor,
                            "elo_floor_disposition": disposition,
                        }
                    )
                else:
                    state = special_state(match)
                    if state is None:
                        unreviewed_target_state_count += 1
                        fail("target-family occurrence escaped reviewed ordinary/special disposition")
                    special_count += 1
                    special_counts[state] += 1

    if distinct_manifest_pairs != EXPECTED_DATE_COUNT:
        fail("distinct manifest-pair count changed")
    if identical_raw_pairs != EXPECTED_IDENTICAL_RAW_PAIR_COUNT:
        fail("identical-raw historical pair count changed")
    if tuple(distinct_raw_dates) != EXPECTED_DISTINCT_RAW_PAIR_DATES:
        fail("distinct-raw historical pair membership changed")
    if target_pair_count != EXPECTED_TARGET_PAIR_COUNT or target_pairs_on_distinct_raw_dates != 0:
        fail("target-family pair accounting changed")
    if (ordinary_count, special_count) != (EXPECTED_ORDINARY_COUNT, EXPECTED_SPECIAL_COUNT):
        fail("ordinary/special target disposition accounting changed")
    if ordinary_count + special_count != target_pair_count:
        fail("target-family disposition accounting does not close")
    duplicate_ordinary_count = sum(1 for count in ordinary_ids.values() if count > 1)
    if len(ordinary_ids) != EXPECTED_ORDINARY_COUNT or duplicate_ordinary_count != 0:
        fail("ordinary-FT source fixture identity is not one-to-one")
    if (preboundary_count, on_or_after_floor_count) != (
        EXPECTED_PREBOUNDARY_COUNT,
        EXPECTED_ON_OR_AFTER_FLOOR_COUNT,
    ):
        fail("PR114 Elo-floor disposition changed")
    if dict(sorted(ordinary_by_league.items())) != EXPECTED_BY_LEAGUE:
        fail("per-league ordinary-FT candidate accounting changed")
    if dict(sorted(special_counts.items())) != EXPECTED_SPECIAL_COUNTS:
        fail("reviewed special-state occurrence accounting changed")
    if pair_conflict_count or display_time_mismatch_count:
        fail("historical target stability changed")
    if halfs_keyset_mismatch_count or halfs_type_mismatch_count or halfs_parse_mismatch_count:
        fail("historical status.halfs qualification changed")
    if unreviewed_target_state_count:
        fail("unreviewed target state encountered")

    projection_records.sort(key=lambda row: (row["fixture_id"], row["request_date"]))
    projection = b"".join(canonical(row) for row in projection_records)
    if (hashlib.sha256(projection).hexdigest(), len(projection)) != (
        ORDINARY_FT_PROJECTION_SHA256,
        ORDINARY_FT_PROJECTION_SIZE,
    ):
        fail("ordinary-FT historical adapter projection changed")
    if projection_output is not None:
        projection_output.parent.mkdir(parents=True, exist_ok=True)
        projection_output.write_bytes(projection)

    receipt = {
        "schema_version": 1,
        "dataset_name": "athena-fotmob-historical-source-history-adapter-qualification-v1",
        "qualification_scope": "IMMUTABLE_FROZEN_CAMPAIGN_HISTORICAL_ORDINARY_FT_ADAPTER_QUALIFICATION_ONLY",
        "qualification_state": "EXECUTED_HISTORICAL_SOURCE_HISTORY_ADAPTER_QUALIFIED_COMPLETENESS_UNPROVEN",
        "repository_main_anchor": REPOSITORY_MAIN_ANCHOR,
        "protocol": {
            "protocol_id": pr116.PROTOCOL_ID,
            "blob_sha": PR116_PROTOCOL_BLOB_SHA,
            "canonical_sha256": pr116.PROTOCOL_SHA256,
            "canonical_size_bytes": pr116.PROTOCOL_SIZE,
        },
        "upstream_qualifications": {
            "pr110_special_result_receipt_sha256": pr110.RECEIPT_SHA256,
            "pr112_rearrangement_chronology_receipt_sha256": pr112.RECEIPT_SHA256,
            "pr114_elo_initialization_receipt_sha256": pr114.RECEIPT_SHA256,
            "pr115_adapter_completeness_receipt_sha256": pr115.RECEIPT_SHA256,
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
            "start_date": "2020-08-01",
            "end_date": "2026-08-14",
        },
        "adapter_qualification": {
            "qualification_status": "QUALIFIED_FROZEN_CAMPAIGN_HISTORICAL_ORDINARY_FT_ADAPTER",
            "request_date_count": EXPECTED_DATE_COUNT,
            "capture_manifest_count": EXPECTED_CAPTURE_COUNT,
            "capture_pair_count": EXPECTED_DATE_COUNT,
            "distinct_manifest_pair_count": distinct_manifest_pairs,
            "identical_raw_sha256_pair_count": identical_raw_pairs,
            "distinct_raw_sha256_pair_count": len(distinct_raw_dates),
            "distinct_raw_sha256_pair_dates": distinct_raw_dates,
            "minimum_pair_separation_microseconds": min(pair_separation_us),
            "maximum_pair_separation_microseconds": max(pair_separation_us),
            "target_family_fixture_date_pair_count": target_pair_count,
            "target_family_pairs_on_distinct_raw_dates": target_pairs_on_distinct_raw_dates,
            "ordinary_ft_projection_record_count": ordinary_count,
            "ordinary_ft_projection_sha256": ORDINARY_FT_PROJECTION_SHA256,
            "ordinary_ft_projection_size_bytes": ORDINARY_FT_PROJECTION_SIZE,
            "ordinary_ft_projection_raw_content_relation": "BYTE_IDENTICAL_FOR_ALL_21336_RECORDS",
            "ordinary_ft_unique_source_fixture_id_count": len(ordinary_ids),
            "ordinary_ft_duplicate_source_fixture_id_count": duplicate_ordinary_count,
            "reviewed_special_state_occurrence_count": special_count,
        },
        "checks": {
            "manifest_raw_lineage_mismatch_count": 0,
            "request_identity_mismatch_count": 0,
            "network_acquisition_false_count": 0,
            "same_manifest_pair_count": 0,
            "pair_separation_below_300_seconds_count": 0,
            "same_date_target_relevant_field_conflict_count": pair_conflict_count,
            "source_display_time_basis": "Europe/Oslo",
            "source_display_time_basis_mismatch_count": display_time_mismatch_count,
            "historical_halfs_keyset_mismatch_count": halfs_keyset_mismatch_count,
            "historical_halfs_type_mismatch_count": halfs_type_mismatch_count,
            "historical_halfs_parse_mismatch_count": halfs_parse_mismatch_count,
            "unreviewed_target_state_occurrence_count": unreviewed_target_state_count,
            "preboundary_ordinary_ft_occurrence_count": preboundary_count,
            "on_or_after_floor_ordinary_ft_occurrence_count": on_or_after_floor_count,
            "ordinary_ft_candidates_by_model_league": dict(sorted(ordinary_by_league.items())),
            "special_state_occurrence_counts": dict(sorted(special_counts.items())),
            "all_raw_capture_evidence_preserved": True,
            "raw_or_manifest_hash_synthesis_performed": False,
            "prospective_adapter_mutation_performed": False,
            "pr89_mutation_performed": False,
            "network_acquisition_performed": False,
        },
        "historical_adapter_execution_performed": True,
        "historical_source_history_adapter_qualified": True,
        "source_history_adapter_approved": False,
        "source_history_completeness_proven": False,
        "historical_coverage_proven": False,
        "history_rows_materialized": 0,
        "ordinary_ft_history_rows_authorized": False,
        "source_history_mutation_performed": False,
        "source_capability_registry_mutation_performed": False,
        "competition_registry_mutation_performed": False,
        "resolved_blocker": "BLOCKED_RESULT_EVIDENCE_GAP",
        "remaining_blockers": ["BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"],
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": {key: False for key in SAFETY_KEYS},
    }
    exact = canonical(receipt)
    if (hashlib.sha256(exact).hexdigest(), len(exact)) != (
        EXPECTED_RECEIPT_SHA256,
        EXPECTED_RECEIPT_SIZE,
    ):
        fail("qualification receipt does not match frozen PR117 identity")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=pathlib.Path)
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path(
            "artifacts/research-manifests/"
            "fotmob-historical-source-history-adapter-qualification-v1.json"
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
