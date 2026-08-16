#!/usr/bin/env python3
"""Execute the reviewed FotMob Elo-initialization boundary qualification.

The execution is intentionally research-only and fail closed. It combines:
1. a fresh rebuild of the exact 66 football-data.co.uk source files used by PR69;
2. the exact preserved PR105 FotMob campaign artifact; and
3. the frozen PR113 initialization protocol.

It emits one canonical JSON receipt and authorizes nothing downstream.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import shutil
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import domain.fotmob_data_matches_status_reason_semantics_protocol as pr90
import domain.fotmob_source_history_elo_initialization_boundary_protocol as pr113
import domain.fotmob_source_history_rearrangement_chronology_qualification as pr112
import domain.fotmob_source_history_special_result_semantics_protocol as pr109
import domain.historical_model_feature_replay_candidate as pr69
from scripts.import_football_data_uk import official_csv_url

REPOSITORY_MAIN_ANCHOR = "7b0ed65347020c839802700be547ceb304aeddfd"
ARTIFACT_ID = 9249856559
ARTIFACT_NAME = "fotmob-ordinary-ft-source-history-campaign-31887523012"
ARTIFACT_SHA256 = "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
ARTIFACT_SIZE = 61_886_753
CACHE_MEMBER = "athena-research-cache.tar.gz"
CACHE_SHA256 = "cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6"
CACHE_SIZE = 61_881_610
PR69_SOURCE_CORPUS_SHA256 = "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0"
PR69_CANONICAL_REPLAY_SHA256 = "b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3"
PR69_CANONICAL_REPLAY_SIZE = 39_952_730
PR69_SOURCE_TOTAL_BYTES = 10_006_877
PR69_SOURCE_FIXTURE_COUNT = 21_226
PR69_SOURCE_FILE_COUNT = 66
SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26")
LEAGUES = tuple(item[0] for item in pr113.FROZEN_MODEL_FAMILIES)
PRIMARY_BY_LEAGUE = {item[0]: item[1] for item in pr113.FROZEN_MODEL_FAMILIES}
LEAGUE_BY_PRIMARY = {item[1]: item[0] for item in pr113.FROZEN_MODEL_FAMILIES}
COUNTRY_BY_LEAGUE = {item[0]: item[2] for item in pr113.FROZEN_MODEL_FAMILIES}
QUALIFICATION_STATE = "EXECUTED_PR69_EQUIVALENT_ELO_INITIALIZATION_BOUNDARY_QUALIFIED"
QUALIFIED_STATUS = "QUALIFIED_PR69_EQUIVALENT_EMPTY_1500_INITIALIZATION_BOUNDARY"
RESOLVED_BLOCKER = "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN"
REMAINING_BLOCKERS = ["BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"]
NEXT_REQUIRED_BOUNDARY = "EXECUTE_REVIEWED_SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_ASSESSMENT"
_DOWNLOAD_ATTEMPTS = 3

SAFETY_KEYS = (
    "initialization_boundary_proven_for_research_receipt_only",
    "ordinary_ft_history_rows_authorized",
    "special_result_history_rows_authorized",
    "source_history_adapter_approved",
    "source_history_completeness_proven",
    "historical_coverage_proven",
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


def _canonical(value: Any) -> bytes:
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


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_source(season: str, league: str, cache_dir: Path) -> bytes:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{season}_{league}.csv"
    if target.is_file():
        return target.read_bytes()
    url = official_csv_url(season, league)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ATHENA PR114 exact historical replay revalidator"},
    )
    error: Exception | None = None
    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()
            if not raw:
                raise ValueError("empty official CSV response")
            target.write_bytes(raw)
            return raw
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            error = exc
            if attempt < _DOWNLOAD_ATTEMPTS:
                time.sleep(2 * attempt)
    raise RuntimeError(f"failed to acquire exact official CSV {season} {league}: {error}")


def _rebuild_pr69(cache_dir: Path) -> tuple[pr69.HistoricalReplayCorpus, bytes, dict[str, str], dict[str, Any]]:
    inputs: list[pr69.HistoricalReplaySourceInput] = []
    raw_total = 0
    file_hashes: dict[str, str] = {}
    for season in SEASONS:
        for league in LEAGUES:
            raw = _download_source(season, league, cache_dir)
            raw_total += len(raw)
            file_hashes[f"{season}/{league}"] = hashlib.sha256(raw).hexdigest()
            inputs.append(pr69.HistoricalReplaySourceInput(season, league, raw))

    corpus = pr69.build_historical_model_feature_replay_corpus(tuple(inputs))
    replay = pr69.canonical_historical_model_feature_replay_corpus_bytes(corpus)
    checks = {
        "source_file_count": len(corpus.source_files),
        "source_total_bytes": raw_total,
        "fixture_count": corpus.fixture_count,
        "source_corpus_sha256": corpus.source_corpus_sha256,
        "canonical_replay_sha256": hashlib.sha256(replay).hexdigest(),
        "canonical_replay_size_bytes": len(replay),
    }
    expected = {
        "source_file_count": PR69_SOURCE_FILE_COUNT,
        "source_total_bytes": PR69_SOURCE_TOTAL_BYTES,
        "fixture_count": PR69_SOURCE_FIXTURE_COUNT,
        "source_corpus_sha256": PR69_SOURCE_CORPUS_SHA256,
        "canonical_replay_sha256": PR69_CANONICAL_REPLAY_SHA256,
        "canonical_replay_size_bytes": PR69_CANONICAL_REPLAY_SIZE,
    }
    if checks != expected:
        raise ValueError(f"PR69 exact source rebuild changed: observed={checks!r}")

    floors: dict[str, str] = {}
    floor_witness: dict[str, Any] = {}
    for league in LEAGUES:
        fixtures = [
            item
            for item in corpus.fixtures
            if item.season == "2020-21" and item.identity_league == league
        ]
        if not fixtures:
            raise ValueError(f"no 2020-21 PR69 fixture evidence for {league}")
        first_date = min(item.source_local_date for item in fixtures)
        floor = first_date.isoformat()
        floors[league] = floor
        first = sorted(
            (item for item in fixtures if item.source_local_date == first_date),
            key=lambda item: item.fixture_identifier,
        )[0]
        floor_witness[league] = {
            "reference_floor_source_local_date": floor,
            "source_fixture_identifier": first.fixture_identifier,
            "source_file_sha256": first.source_file_sha256,
            "source_row_number": first.source_row_number,
            "source_local_kickoff": (
                first.source_local_kickoff.isoformat() if first.source_local_kickoff else None
            ),
            "home_team_name": first.home_team_name,
            "away_team_name": first.away_team_name,
        }
    return corpus, replay, floors, {
        "checks": checks,
        "source_file_sha256": dict(sorted(file_hashes.items())),
        "reference_floor_witness": floor_witness,
    }


def _extract_cache(artifact: Path, destination: Path) -> Path:
    if artifact.stat().st_size != ARTIFACT_SIZE or _sha256_path(artifact) != ARTIFACT_SHA256:
        raise ValueError("FotMob campaign artifact identity mismatch")
    with zipfile.ZipFile(artifact) as archive:
        info = archive.getinfo(CACHE_MEMBER)
        if info.file_size != CACHE_SIZE:
            raise ValueError("embedded FotMob research-cache size mismatch")
        target = destination / CACHE_MEMBER
        with archive.open(info) as source, target.open("wb") as sink:
            shutil.copyfileobj(source, sink)
    if target.stat().st_size != CACHE_SIZE or _sha256_path(target) != CACHE_SHA256:
        raise ValueError("embedded FotMob research-cache identity mismatch")
    return target


def _special_state(match: dict[str, Any]) -> str | None:
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
        ) != (
            short,
            short_key,
            long,
            long_key,
            finished,
            started,
            cancelled,
        ):
            continue
        if awarded_rule == "EXACT_TRUE" and awarded is True:
            return state_id
        if awarded_rule == "EXACT_FALSE" and awarded is False:
            return state_id
        if awarded_rule == "ABSENT_OR_FALSE" and (awarded == "ABSENT" or awarded is False):
            return state_id
    return None


def _ordinary_ft(match: dict[str, Any]) -> bool:
    status, home, away = match.get("status"), match.get("home"), match.get("away")
    if not all(isinstance(item, dict) for item in (status, home, away)):
        return False
    reason = status.get("reason")
    if not isinstance(reason, dict):
        return False
    awarded = status.get("awarded", "ABSENT")
    return (
        reason == dict(pr90.ORDINARY_FT_REASON_TUPLE)
        and status.get("finished") is True
        and status.get("started") is True
        and status.get("cancelled") is False
        and (awarded == "ABSENT" or awarded is False)
        and "penScore" not in home
        and "penScore" not in away
        and type(home.get("score")) is int
        and type(away.get("score")) is int
        and home.get("score") >= 0
        and away.get("score") >= 0
    )


def _row(request_date: str, capture_id: str, league: dict[str, Any], match: dict[str, Any]) -> dict[str, Any]:
    status, home, away = match.get("status"), match.get("home"), match.get("away")
    if not all(isinstance(item, dict) for item in (status, home, away)):
        raise ValueError("target-family FotMob row lacks status/home/away objects")
    state = _special_state(match) or ("ORDINARY_FT" if _ordinary_ft(match) else "OTHER")
    return {
        "request_date": request_date,
        "capture_id": capture_id,
        "fixture_id": match.get("id"),
        "state_id": state,
        "primary_id": league.get("primaryId"),
        "wrapper_league_id": league.get("id"),
        "country_code": league.get("ccode"),
        "home_team_id": home.get("id"),
        "away_team_id": away.get("id"),
        "kickoff_utc": status.get("utcTime"),
        "home_score": home.get("score"),
        "away_score": away.get("score"),
    }


def _scan_fotmob(artifact: Path, floors: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    target_ids = set(LEAGUE_BY_PRIMARY)
    rows: list[dict[str, Any]] = []
    response_count = 0
    dates: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="athena-pr114-fotmob-") as tmp:
        cache = _extract_cache(artifact, Path(tmp))
        with tarfile.open(cache, "r:gz") as archive:
            for member in archive:
                if not member.isfile() or not member.name.endswith("/response.json"):
                    continue
                parts = member.name.split("/")
                if len(parts) < 3:
                    raise ValueError("unexpected campaign response path")
                request_date, capture_id = parts[-3:-1]
                payload = json.load(archive.extractfile(member))
                response_count += 1
                dates.add(request_date)
                leagues = payload.get("leagues")
                if not isinstance(leagues, list):
                    raise ValueError("FotMob campaign response lacks leagues list")
                for league in leagues:
                    if not isinstance(league, dict) or league.get("primaryId") not in target_ids:
                        continue
                    matches = league.get("matches")
                    if not isinstance(matches, list):
                        raise ValueError("target FotMob league lacks matches list")
                    for match in matches:
                        if not isinstance(match, dict):
                            raise ValueError("target FotMob match row is not an object")
                        rows.append(_row(request_date, capture_id, league, match))

    if response_count != 4_410 or len(dates) != 2_205:
        raise ValueError("FotMob campaign coverage envelope changed")

    grouped: dict[tuple[str, int], list[dict[str, Any]]] = collections.defaultdict(list)
    malformed_identity = 0
    for row in rows:
        if type(row["fixture_id"]) is not int or row["fixture_id"] <= 0:
            malformed_identity += 1
            continue
        grouped[(row["request_date"], row["fixture_id"])].append(row)

    pair_cardinality_mismatch = 0
    pair_conflicts = 0
    collapsed: list[dict[str, Any]] = []
    for key in sorted(grouped):
        pair = grouped[key]
        if len(pair) != 2:
            pair_cardinality_mismatch += 1
            continue
        left = {k: v for k, v in pair[0].items() if k != "capture_id"}
        right = {k: v for k, v in pair[1].items() if k != "capture_id"}
        if _canonical(left) != _canonical(right):
            pair_conflicts += 1
            continue
        left["capture_ids"] = sorted([pair[0]["capture_id"], pair[1]["capture_id"]])
        collapsed.append(left)

    if malformed_identity or pair_cardinality_mismatch or pair_conflicts:
        raise ValueError(
            "FotMob target-family same-date evidence is not exact: "
            f"malformed={malformed_identity} cardinality={pair_cardinality_mismatch} conflicts={pair_conflicts}"
        )

    projection = b"".join(
        _canonical(row)
        for row in sorted(collapsed, key=lambda x: (x["primary_id"], x["request_date"], x["fixture_id"]))
    )

    per_family: dict[str, Any] = {}
    preboundary_total = 0
    first_seed_total = 0
    reused_team_state_total = 0
    special_excluded_total = 0
    ordinary_candidate_total = 0
    team_identity_violation_count = 0
    static_fixture_identity_drift_count = 0

    by_fixture: dict[int, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in collapsed:
        by_fixture[row["fixture_id"]].append(row)
    for fixture_id, history in by_fixture.items():
        static = {(x["primary_id"], x["home_team_id"], x["away_team_id"]) for x in history}
        if len(static) != 1:
            static_fixture_identity_drift_count += 1

    for league in LEAGUES:
        primary = PRIMARY_BY_LEAGUE[league]
        floor_iso = floors[league]
        floor_key = floor_iso.replace("-", "")
        family_rows = [row for row in collapsed if row["primary_id"] == primary]
        before = [row for row in family_rows if row["request_date"] < floor_key]
        after = [row for row in family_rows if row["request_date"] >= floor_key]
        preboundary_total += len(before)

        reviewed_after: list[dict[str, Any]] = []
        for row in after:
            if row["state_id"] == "ORDINARY_FT":
                if (
                    type(row["home_team_id"]) is not int
                    or row["home_team_id"] <= 0
                    or type(row["away_team_id"]) is not int
                    or row["away_team_id"] <= 0
                    or row["home_team_id"] == row["away_team_id"]
                ):
                    team_identity_violation_count += 1
                    continue
                reviewed_after.append(row)
            elif row["state_id"] != "OTHER":
                special_excluded_total += 1
        if not reviewed_after:
            raise ValueError(f"no reviewed ordinary-FT FotMob evidence at/after PR69 floor for {league}")

        reviewed_after.sort(
            key=lambda x: (
                str(x["kickoff_utc"] or ""),
                x["request_date"],
                x["fixture_id"],
            )
        )
        first = reviewed_after[0]
        ordinary_candidate_total += len(reviewed_after)

        state: dict[int, dict[str, int]] = {}
        first_seed_count = 0
        reused_count = 0
        for row in reviewed_after:
            for team_key in ("home_team_id", "away_team_id"):
                team_id = row[team_key]
                if team_id not in state:
                    state[team_id] = {"rating": 1500, "matches": 0}
                    first_seed_count += 1
                else:
                    reused_count += 1
            home_state = state[row["home_team_id"]]
            away_state = state[row["away_team_id"]]
            home_state["matches"] += 1
            away_state["matches"] += 1

        first_seed_total += first_seed_count
        reused_team_state_total += reused_count
        per_family[league] = {
            "model_league_code": league,
            "fotmob_primary_id": primary,
            "expected_country_code": COUNTRY_BY_LEAGUE[league],
            "pr69_reference_floor_source_local_date": floor_iso,
            "fotmob_preboundary_fixture_date_occurrence_count": len(before),
            "fotmob_preboundary_raw_capture_row_count": len(before) * 2,
            "fotmob_preboundary_unique_fixture_id_count": len({row["fixture_id"] for row in before}),
            "reviewed_ordinary_ft_candidate_count_on_or_after_floor": len(reviewed_after),
            "first_reviewed_ordinary_ft_candidate": {
                "request_date": first["request_date"],
                "fixture_id": first["fixture_id"],
                "kickoff_utc": first["kickoff_utc"],
                "home_team_id": first["home_team_id"],
                "away_team_id": first["away_team_id"],
                "home_score": first["home_score"],
                "away_score": first["away_score"],
            },
            "source_scoped_team_id_count_in_candidate_stream": len(state),
            "first_seen_team_seed_count": first_seed_count,
            "reused_team_state_observation_count": reused_count,
            "preboundary_rows_used_to_seed_or_update_state": 0,
            "special_or_nonordinary_rows_used_to_seed_or_update_state": 0,
            "season_reset_count": 0,
            "initial_rating": 1500,
            "initial_matches": 0,
            "qualification_status": QUALIFIED_STATUS,
        }

    checks = {
        "request_date_count": len(dates),
        "response_file_count": response_count,
        "target_family_raw_capture_row_count": len(rows),
        "target_family_fixture_date_pair_count": len(collapsed),
        "target_family_projection_sha256": hashlib.sha256(projection).hexdigest(),
        "target_family_projection_size_bytes": len(projection),
        "same_date_pair_cardinality_mismatch_count": pair_cardinality_mismatch,
        "same_date_pair_relevant_field_conflict_count": pair_conflicts,
        "malformed_fixture_identity_count": malformed_identity,
        "static_fixture_identity_drift_count": static_fixture_identity_drift_count,
        "team_identity_violation_count": team_identity_violation_count,
        "preboundary_fixture_date_occurrence_count": preboundary_total,
        "preboundary_state_leakage_count": 0,
        "special_or_nonordinary_state_update_count": 0,
        "out_of_universe_state_update_count": 0,
        "season_reset_count": 0,
        "first_seen_team_seed_count": first_seed_total,
        "reused_team_state_observation_count": reused_team_state_total,
        "reviewed_ordinary_ft_candidate_count_on_or_after_floor": ordinary_candidate_total,
        "special_state_occurrence_count_on_or_after_floor": special_excluded_total,
        "all_eleven_reference_floors_have_reviewed_result_evidence": len(per_family) == 11,
    }
    if any(
        checks[key] != 0
        for key in (
            "same_date_pair_cardinality_mismatch_count",
            "same_date_pair_relevant_field_conflict_count",
            "malformed_fixture_identity_count",
            "static_fixture_identity_drift_count",
            "team_identity_violation_count",
            "preboundary_state_leakage_count",
            "special_or_nonordinary_state_update_count",
            "out_of_universe_state_update_count",
            "season_reset_count",
        )
    ):
        raise ValueError("initialization boundary violation detected")
    if checks["all_eleven_reference_floors_have_reviewed_result_evidence"] is not True:
        raise ValueError("not every model family has reviewed result evidence at/after its floor")
    return collapsed, {
        "checks": checks,
        "families": [per_family[league] for league in LEAGUES],
    }


def build_receipt(artifact: Path, football_data_cache: Path) -> dict[str, Any]:
    protocol = pr113.build_fotmob_source_history_elo_initialization_boundary_protocol()
    protocol_raw = pr113.canonical_fotmob_source_history_elo_initialization_boundary_protocol_bytes(protocol)
    if (len(protocol_raw), hashlib.sha256(protocol_raw).hexdigest()) != (
        pr113.PROTOCOL_SIZE,
        pr113.PROTOCOL_SHA256,
    ):
        raise ValueError("PR113 protocol identity changed")
    if pr113.NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_ELO_INITIALIZATION_BOUNDARY_QUALIFICATION"
    ):
        raise ValueError("PR113 execution boundary changed")

    pr112_receipt = pr112.load_fotmob_source_history_rearrangement_chronology_qualification_receipt()
    pr112_raw = pr112.canonical_fotmob_source_history_rearrangement_chronology_qualification_receipt_bytes()
    if (len(pr112_raw), hashlib.sha256(pr112_raw).hexdigest()) != (
        pr112.RECEIPT_SIZE,
        pr112.RECEIPT_SHA256,
    ):
        raise ValueError("PR112 receipt identity changed")
    if pr112_receipt.get("rearrangement_chronology_qualified") is not True:
        raise ValueError("PR112 chronology is no longer qualified")
    if pr112_receipt.get("remaining_blockers") != [
        "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN",
        "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",
    ]:
        raise ValueError("PR112 blocker ancestry changed")

    corpus, replay, floors, pr69_evidence = _rebuild_pr69(football_data_cache)
    _, fotmob_evidence = _scan_fotmob(artifact, floors)

    return {
        "schema_version": 1,
        "dataset_name": "athena-fotmob-source-history-elo-initialization-boundary-qualification-v1",
        "scope": "IMMUTABLE_PR69_EQUIVALENT_ELO_INITIALIZATION_BOUNDARY_QUALIFICATION_RECEIPT_ONLY",
        "repository_main_anchor": REPOSITORY_MAIN_ANCHOR,
        "protocol": {
            "protocol_id": pr113.PROTOCOL_ID,
            "canonical_sha256": pr113.PROTOCOL_SHA256,
            "canonical_size_bytes": pr113.PROTOCOL_SIZE,
        },
        "upstream": {
            "pr112_receipt_sha256": pr112.RECEIPT_SHA256,
            "pr112_receipt_size_bytes": pr112.RECEIPT_SIZE,
            "pr69_source_corpus_sha256": corpus.source_corpus_sha256,
            "pr69_canonical_replay_sha256": hashlib.sha256(replay).hexdigest(),
            "pr69_canonical_replay_size_bytes": len(replay),
        },
        "source_evidence": {
            "fotmob_artifact_id": ARTIFACT_ID,
            "fotmob_artifact_name": ARTIFACT_NAME,
            "fotmob_artifact_sha256": ARTIFACT_SHA256,
            "fotmob_artifact_size_bytes": ARTIFACT_SIZE,
            "fotmob_research_cache_tar_gz_sha256": CACHE_SHA256,
            "fotmob_research_cache_tar_gz_size_bytes": CACHE_SIZE,
            "football_data_source_file_count": PR69_SOURCE_FILE_COUNT,
            "football_data_source_total_bytes": PR69_SOURCE_TOTAL_BYTES,
            "football_data_source_fixture_count": PR69_SOURCE_FIXTURE_COUNT,
        },
        "qualification_state": QUALIFICATION_STATE,
        "initialization_boundary_execution_performed": True,
        "initialization_boundary_qualified": True,
        "qualification_status": QUALIFIED_STATUS,
        "reference_floor_granularity": "PR69_SOURCE_LOCAL_CALENDAR_DATE_VS_FOTMOB_REQUEST_DATE_ONLY",
        "pr69_rebuild": pr69_evidence,
        "fotmob_boundary_assessment": fotmob_evidence,
        "resolved_blocker": RESOLVED_BLOCKER,
        "remaining_blockers": list(REMAINING_BLOCKERS),
        "source_history_mutation_performed": False,
        "ordinary_ft_history_rows_authorized": False,
        "historical_coverage_proven": False,
        "source_capability_registry_mutation_performed": False,
        "competition_registry_mutation_performed": False,
        "cross_source_fixture_identity_inferred": False,
        "cross_source_team_identity_inferred": False,
        "cross_source_numeric_elo_equivalence_claimed": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": {key: False for key in SAFETY_KEYS},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--football-data-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = build_receipt(args.artifact, args.football_data_cache)
    raw = _canonical(receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    print(f"receipt_sha256={hashlib.sha256(raw).hexdigest()}")
    print(f"receipt_size={len(raw)}")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
