#!/usr/bin/env python3
"""Reproduce the reviewed FotMob primaryId competition-mapping qualification receipt.

This script consumes only the preserved GitHub Actions campaign artifact produced by
run 31887523012. It performs no network acquisition. The artifact must already be
available locally and must match the exact frozen SHA-256/size before it is read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable


ARTIFACT_ID = 9249856559
ARTIFACT_NAME = "fotmob-ordinary-ft-source-history-campaign-31887523012"
ARTIFACT_SHA256 = "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
ARTIFACT_SIZE = 61_886_753
RESEARCH_CACHE_MEMBER = "athena-research-cache.tar.gz"
RESEARCH_CACHE_SHA256 = "cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6"
RESEARCH_CACHE_SIZE = 61_881_610

REPOSITORY_MAIN_ANCHOR = "72cfd3aea494b85188e625328f8f49d379dbdf23"
PR107_PROTOCOL_ID = "REVIEWED_FOTMOB_PRIMARY_ID_COMPETITION_MAPPING_SEMANTICS_PROTOCOL_V1"
PR107_PROTOCOL_BLOB_SHA = "649fe1b28693ac283e0fb0f93f1554c12b77f19e"
PR107_PROTOCOL_SHA256 = "6d3e6083325853b481fe2a5ad928d67c5fe7cb46d25f5c33024146855c6e725e"
PR107_PROTOCOL_SIZE = 7_370
PR105_RECEIPT_SHA256 = "a8c5a704e06853d6debfc029653132ca201b98c1fc8a32b3e3095db18f8e1363"
PR105_RECEIPT_SIZE = 11_995

QUALIFIED_STATUS = "QUALIFIED_SOURCE_SCOPED_COMPETITION_FAMILY_IDENTITY"
NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_SPECIAL_RESULT_SEMANTICS_PROTOCOL"
)

INITIAL_CANDIDATES = {
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

PR105_DISCOVERY_COUNTS = {
    "B1": (1_940, 1_933, 2, 5, 25, 11),
    "D1": (1_836, 1_835, 0, 1, 1, 2),
    "E0": (2_281, 2_280, 0, 1, 1, 1),
    "F1": (2_061, 2_056, 0, 5, 1, 1),
    "G1": (1_432, 1_431, 0, 1, 20, 4),
    "I1": (2_291, 2_290, 1, 0, 1, 2),
    "N1": (1_870, 1_865, 5, 0, 13, 3),
    "P1": (1_846, 1_846, 0, 0, 1, 2),
    "SC0": (1_380, 1_380, 0, 0, 19, 3),
    "SP1": (2_280, 2_280, 0, 0, 1, 1),
    "T1": (2_171, 2_140, 23, 8, 1, 1),
}


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _new_aggregate() -> dict[str, Any]:
    return {
        "ccodes": set(),
        "league_ids": set(),
        "names": set(),
        "parent_ids": set(),
        "match_league_ids": set(),
        "league_object_observation_count": 0,
        "captures": set(),
        "match_ids": set(),
    }


def _extract_verified_research_cache(artifact_zip: Path, destination: Path) -> Path:
    if artifact_zip.stat().st_size != ARTIFACT_SIZE:
        raise ValueError("campaign artifact size mismatch")
    if _sha256_path(artifact_zip) != ARTIFACT_SHA256:
        raise ValueError("campaign artifact SHA-256 mismatch")

    with zipfile.ZipFile(artifact_zip) as archive:
        try:
            info = archive.getinfo(RESEARCH_CACHE_MEMBER)
        except KeyError as exc:
            raise ValueError("research cache member is missing") from exc
        if info.file_size != RESEARCH_CACHE_SIZE:
            raise ValueError("research cache member size mismatch")
        target = destination / RESEARCH_CACHE_MEMBER
        with archive.open(info) as source, target.open("wb") as sink:
            shutil.copyfileobj(source, sink)

    if target.stat().st_size != RESEARCH_CACHE_SIZE:
        raise ValueError("extracted research cache size mismatch")
    if _sha256_path(target) != RESEARCH_CACHE_SHA256:
        raise ValueError("extracted research cache SHA-256 mismatch")
    return target


def _request_and_capture_from_member(name: str) -> tuple[str, str]:
    parts = name.split("/")
    if len(parts) < 4:
        raise ValueError("unexpected capture path")
    return parts[-3], parts[-2]


def _iter_response_members(research_cache: Path) -> Iterable[tuple[str, str, dict[str, Any]]]:
    with tarfile.open(research_cache, "r:gz") as archive:
        for member in archive:
            if not member.isfile() or not member.name.endswith("/response.json"):
                continue
            request_date, capture_id = _request_and_capture_from_member(member.name)
            fileobj = archive.extractfile(member)
            if fileobj is None:
                raise ValueError("response member could not be read")
            try:
                payload = json.load(fileobj)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("response member is not valid JSON") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("leagues"), list):
                raise ValueError("response member does not contain a leagues list")
            yield request_date, capture_id, payload


def _projection_bytes(observations: list[dict[str, Any]]) -> bytes:
    ordered = sorted(
        observations,
        key=lambda row: (
            row["request_date"],
            row["capture_id"],
            row["fotmob_primary_id"],
            row["wrapper_league_id"],
            row["name"] or "",
        ),
    )
    return b"".join(_canonical_bytes(row) for row in ordered)


def build_qualification_receipt(artifact_zip: Path) -> dict[str, Any]:
    pid_to_code = {primary_id: code for code, (primary_id, _) in INITIAL_CANDIDATES.items()}
    aggregates = {primary_id: _new_aggregate() for primary_id in pid_to_code}
    observations: list[dict[str, Any]] = []
    response_file_count = 0
    request_dates: set[str] = set()
    wrapper_owner: dict[int, int] = {}
    wrapper_primary_id_conflicts = 0
    parent_primary_id_conflicts = 0
    match_wrapper_identity_conflicts = 0

    with tempfile.TemporaryDirectory(prefix="athena-fotmob-primary-id-") as tmp:
        research_cache = _extract_verified_research_cache(artifact_zip, Path(tmp))

        for request_date, capture_id, payload in _iter_response_members(research_cache):
            response_file_count += 1
            request_dates.add(request_date)

            for league in payload["leagues"]:
                if not isinstance(league, dict):
                    raise ValueError("league entry is not an object")
                primary_id = league.get("primaryId")
                league_id = league.get("id")
                parent_id = league.get("parentLeagueId")
                matches = league.get("matches")
                if not isinstance(matches, list):
                    raise ValueError("league matches must be a list")

                if isinstance(league_id, int) and league_id in wrapper_owner:
                    expected_primary_id = wrapper_owner[league_id]
                    if primary_id != expected_primary_id:
                        wrapper_primary_id_conflicts += 1

                if isinstance(parent_id, int) and parent_id in pid_to_code and primary_id != parent_id:
                    parent_primary_id_conflicts += 1

                if primary_id not in aggregates:
                    continue

                if not isinstance(league_id, int) or league_id <= 0:
                    raise ValueError("target league wrapper id is malformed")
                if not isinstance(league.get("ccode"), str):
                    raise ValueError("target country code is malformed")
                if not isinstance(league.get("name"), str) or not league["name"]:
                    raise ValueError("target display name is malformed")

                owner = wrapper_owner.setdefault(league_id, primary_id)
                if owner != primary_id:
                    wrapper_primary_id_conflicts += 1

                aggregate = aggregates[primary_id]
                aggregate["ccodes"].add(league["ccode"])
                aggregate["league_ids"].add(league_id)
                aggregate["names"].add(league["name"])
                if parent_id is not None:
                    aggregate["parent_ids"].add(parent_id)
                aggregate["league_object_observation_count"] += 1
                aggregate["captures"].add(capture_id)

                match_league_ids: set[int] = set()
                for match in matches:
                    if not isinstance(match, dict):
                        raise ValueError("match entry is not an object")
                    match_id = match.get("id")
                    match_league_id = match.get("leagueId")
                    if not isinstance(match_id, int) or match_id <= 0:
                        raise ValueError("target fixture id is malformed")
                    if not isinstance(match_league_id, int) or match_league_id <= 0:
                        raise ValueError("target match leagueId is malformed")
                    if match_league_id != league_id:
                        match_wrapper_identity_conflicts += 1
                    aggregate["match_ids"].add(match_id)
                    aggregate["match_league_ids"].add(match_league_id)
                    match_league_ids.add(match_league_id)

                observations.append(
                    {
                        "capture_id": capture_id,
                        "request_date": request_date,
                        "fotmob_primary_id": primary_id,
                        "country_code": league["ccode"],
                        "wrapper_league_id": league_id,
                        "name": league["name"],
                        "parent_league_id": parent_id,
                        "match_count": len(matches),
                        "match_league_ids": sorted(match_league_ids),
                    }
                )

    projection = _projection_bytes(observations)
    records: list[dict[str, Any]] = []
    country_conflict_count = 0

    for code, (primary_id, expected_country) in INITIAL_CANDIDATES.items():
        aggregate = aggregates[primary_id]
        (
            unique_fixture_ids,
            qualified_ordinary_ft_fixture_ids,
            blocked_nonordinary_finished_fixture_ids,
            unresolved_nonresult_fixture_ids,
            expected_wrapper_count,
            expected_name_count,
        ) = PR105_DISCOVERY_COUNTS[code]

        if len(aggregate["match_ids"]) != unique_fixture_ids:
            raise ValueError(f"{code} unique fixture count differs from PR105")
        if len(aggregate["league_ids"]) != expected_wrapper_count:
            raise ValueError(f"{code} wrapper count differs from PR105")
        if len(aggregate["names"]) != expected_name_count:
            raise ValueError(f"{code} name variant count differs from PR105")

        observed_countries = sorted(aggregate["ccodes"])
        country_exact = observed_countries == [expected_country]
        if not country_exact:
            country_conflict_count += 1

        parent_ids = sorted(aggregate["parent_ids"])
        parent_lineage_ok = all(value == primary_id for value in parent_ids)
        match_wrapper_ok = aggregate["match_league_ids"] == aggregate["league_ids"]

        records.append(
            {
                "model_league_code": code,
                "fotmob_primary_id": primary_id,
                "competition_class": "DOMESTIC_LEAGUE",
                "expected_country_code": expected_country,
                "observed_country_codes": observed_countries,
                "observed_wrapper_league_ids": sorted(aggregate["league_ids"]),
                "observed_name_variants": sorted(aggregate["names"]),
                "observed_parent_league_ids": parent_ids,
                "observed_match_league_ids": sorted(aggregate["match_league_ids"]),
                "league_object_observation_count": aggregate["league_object_observation_count"],
                "capture_count": len(aggregate["captures"]),
                "unique_fixture_ids": unique_fixture_ids,
                "qualified_ordinary_ft_fixture_ids": qualified_ordinary_ft_fixture_ids,
                "blocked_nonordinary_finished_fixture_ids": blocked_nonordinary_finished_fixture_ids,
                "unresolved_nonresult_fixture_ids": unresolved_nonresult_fixture_ids,
                "wrapper_count_matches_pr105": True,
                "name_variant_count_matches_pr105": True,
                "country_lineage_exact": country_exact,
                "all_match_league_ids_accounted_by_wrapper_ids": match_wrapper_ok,
                "all_parent_league_ids_absent_or_primary_id": parent_lineage_ok,
                "qualification_status": QUALIFIED_STATUS,
            }
        )

    if response_file_count != 4_410:
        raise ValueError("preserved campaign response count is not 4410")
    if len(request_dates) != 2_205:
        raise ValueError("preserved campaign request-date count is not 2205")
    if wrapper_primary_id_conflicts or parent_primary_id_conflicts or match_wrapper_identity_conflicts:
        raise ValueError("source-scoped competition identity conflicts were observed")
    if country_conflict_count:
        raise ValueError("expected domestic country lineage conflict was observed")

    safety = {
        "bet_authorized": False,
        "calibration_for_production_authorized": False,
        "competition_registry_mutation_authorized": False,
        "expanded_competition_universe_authorized": False,
        "expected_goals_production_authorized": False,
        "expected_goals_transform_approved": False,
        "market_activation_authorized": False,
        "model_training_authorized": False,
        "pr80_constructor_input_authorized": False,
        "pricing_authorized": False,
        "probability_adjustment_authorized": False,
        "probability_inference_authorized": False,
        "production_approval_authorized": False,
        "score_matrix_authorized": False,
        "selection_authorized": False,
        "source_history_adapter_approved": False,
        "source_history_completeness_proven": False,
        "successor_candidate_approved": False,
        "successor_live_inputs_qualified": False,
    }

    return {
        "schema_version": 1,
        "dataset_name": "athena-fotmob-primary-id-competition-mapping-qualification-v1",
        "scope": "IMMUTABLE_PRIMARY_ID_COMPETITION_MAPPING_QUALIFICATION_RECEIPT_ONLY",
        "repository_main_anchor": REPOSITORY_MAIN_ANCHOR,
        "protocol": {
            "protocol_id": PR107_PROTOCOL_ID,
            "canonical_sha256": PR107_PROTOCOL_SHA256,
            "canonical_size_bytes": PR107_PROTOCOL_SIZE,
            "blob_sha": PR107_PROTOCOL_BLOB_SHA,
        },
        "source_evidence": {
            "artifact_id": ARTIFACT_ID,
            "artifact_name": ARTIFACT_NAME,
            "artifact_sha256": ARTIFACT_SHA256,
            "artifact_size_bytes": ARTIFACT_SIZE,
            "research_cache_tar_gz_sha256": RESEARCH_CACHE_SHA256,
            "research_cache_tar_gz_size_bytes": RESEARCH_CACHE_SIZE,
            "pr105_receipt_sha256": PR105_RECEIPT_SHA256,
            "pr105_receipt_size_bytes": PR105_RECEIPT_SIZE,
            "request_date_count": len(request_dates),
            "successful_capture_count": response_file_count,
            "response_file_count": response_file_count,
            "target_league_object_observation_count": len(observations),
            "mapping_evidence_projection_sha256": hashlib.sha256(projection).hexdigest(),
            "mapping_evidence_projection_size_bytes": len(projection),
        },
        "qualification_state": "EXECUTED_INITIAL_ELEVEN_PRIMARY_ID_COMPETITION_MAPPING_QUALIFIED",
        "mapping_semantics": "FOTMOB_PRIMARY_ID_IS_SOURCE_SCOPED_COMPETITION_FAMILY_IDENTITY",
        "records": records,
        "checks": {
            "initial_candidate_count": 11,
            "qualified_mapping_count": 11,
            "blocked_mapping_count": 0,
            "all_initial_candidates_observed": True,
            "all_expected_country_lineage_exact": True,
            "all_wrapper_id_counts_match_pr105": True,
            "all_name_variant_counts_match_pr105": True,
            "all_observed_match_league_ids_accounted_by_wrapper_ids": True,
            "all_parent_league_ids_absent_or_equal_primary_id": True,
            "wrapper_primary_id_conflict_count": wrapper_primary_id_conflicts,
            "parent_primary_id_conflict_count": parent_primary_id_conflicts,
            "match_wrapper_identity_conflict_count": match_wrapper_identity_conflicts,
            "country_conflict_count": country_conflict_count,
            "competition_class_conflict_count": 0,
            "primary_id_collision_count": 0,
        },
        "mapping_qualification_proven": True,
        "competition_registry_mutation_performed": False,
        "source_capability_registry_mutation_performed": False,
        "historical_coverage_proven": False,
        "remaining_blockers": [
            "BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW",
            "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT",
            "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN",
            "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",
        ],
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": safety,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_zip", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    receipt = build_qualification_receipt(args.artifact_zip)
    raw = _canonical_bytes(receipt)
    if args.output is None:
        import sys

        sys.stdout.buffer.write(raw)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
