#!/usr/bin/env python3
"""Reproduce PR #112 from the exact preserved PR #105 campaign artifact only."""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import domain.fotmob_data_matches_status_reason_semantics_protocol as pr90
import domain.fotmob_primary_id_competition_mapping_qualification as pr108
import domain.fotmob_source_history_rearrangement_chronology_semantics_protocol as pr111
import domain.fotmob_source_history_special_result_semantics_protocol as pr109
import domain.fotmob_source_history_special_result_semantics_qualification as pr110

ARTIFACT_SHA256 = "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
ARTIFACT_SIZE = 61_886_753
CACHE_MEMBER = "athena-research-cache.tar.gz"
CACHE_SHA256 = "cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6"
CACHE_SIZE = 61_881_610
REPOSITORY_MAIN_ANCHOR = "9c156e6022b0034dfe16e0d9446b4e1890f53753"
PR111_BLOB_SHA = "58eb56a6c55048cb163b7611da7ef85468c91f9a"
EXPECTED_RECEIPT_SHA256 = "58c7a275580cc74489269a66de2836544e78ca232693d5283f1813ee817d3fc0"
EXPECTED_RECEIPT_SIZE = 7_980
REARRANGED_HISTORY_PROJECTION_SHA256 = "9fa899ebeb0e42154832c1ca9dc040685a359add2a4cf7c1029fd13b7d56dbe8"
REARRANGED_HISTORY_PROJECTION_SIZE = 349_277
EDGE_PROJECTION_SHA256 = "2c85f3ccfa4fd34af928c339ec6ebc79048ed3a5252f88bb195b77fb61bb13b9"
EDGE_PROJECTION_SIZE = 90_086
NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_ELO_INITIALIZATION_BOUNDARY_PROTOCOL"
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_cache(artifact: Path, destination: Path) -> Path:
    if artifact.stat().st_size != ARTIFACT_SIZE or _sha256(artifact) != ARTIFACT_SHA256:
        raise ValueError("campaign artifact identity mismatch")
    with zipfile.ZipFile(artifact) as archive:
        info = archive.getinfo(CACHE_MEMBER)
        if info.file_size != CACHE_SIZE:
            raise ValueError("research-cache size mismatch")
        target = destination / CACHE_MEMBER
        with archive.open(info) as source, target.open("wb") as sink:
            shutil.copyfileobj(source, sink)
    if target.stat().st_size != CACHE_SIZE or _sha256(target) != CACHE_SHA256:
        raise ValueError("research-cache identity mismatch")
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
    )


def _row(
    request_date: str,
    capture_id: str,
    league: dict[str, Any],
    match: dict[str, Any],
) -> dict[str, Any]:
    status, home, away = match["status"], match["home"], match["away"]
    reason = status.get("reason") or {}
    state = _special_state(match) or ("ORDINARY_FT" if _ordinary_ft(match) else "OTHER")
    return {
        "request_date": request_date,
        "capture_id": capture_id,
        "fixture_id": match["id"],
        "state_id": state,
        "primary_id": league.get("primaryId"),
        "wrapper_league_id": league.get("id"),
        "country_code": league.get("ccode"),
        "league_name": league.get("name"),
        "home_team_id": home.get("id"),
        "away_team_id": away.get("id"),
        "kickoff_utc": status.get("utcTime"),
        "status_id": match.get("statusId"),
        "reason": {
            "short": reason.get("short"),
            "shortKey": reason.get("shortKey"),
            "long": reason.get("long"),
            "longKey": reason.get("longKey"),
        },
        "finished": status.get("finished"),
        "started": status.get("started"),
        "cancelled": status.get("cancelled"),
        "awarded": status.get("awarded", None),
        "awarded_present": "awarded" in status,
        "home_score": home.get("score"),
        "away_score": away.get("score"),
        "home_pen_score": home.get("penScore"),
        "home_pen_score_present": "penScore" in home,
        "away_pen_score": away.get("penScore"),
        "away_pen_score_present": "penScore" in away,
        "eliminated_team_id": match.get("eliminatedTeamId"),
        "tournament_stage": match.get("tournamentStage"),
    }


def _utc_request_date(kickoff_utc: str) -> str:
    parsed = dt.datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).strftime("%Y%m%d")


def _parse_utc(kickoff_utc: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def build_receipt(artifact: Path) -> dict[str, Any]:
    protocol = pr111.build_fotmob_source_history_rearrangement_chronology_semantics_protocol()
    protocol_raw = (
        pr111.canonical_fotmob_source_history_rearrangement_chronology_semantics_protocol_bytes(
            protocol
        )
    )
    if (len(protocol_raw), hashlib.sha256(protocol_raw).hexdigest()) != (
        pr111.PROTOCOL_SIZE,
        pr111.PROTOCOL_SHA256,
    ):
        raise ValueError("PR111 protocol identity changed")

    pr110_receipt = pr110.load_fotmob_source_history_special_result_semantics_qualification_receipt()
    pr110_raw = (
        pr110.canonical_fotmob_source_history_special_result_semantics_qualification_receipt_bytes()
    )
    if (len(pr110_raw), hashlib.sha256(pr110_raw).hexdigest()) != (
        pr110.RECEIPT_SIZE,
        pr110.RECEIPT_SHA256,
    ):
        raise ValueError("PR110 receipt identity changed")
    chronology = pr110_receipt["chronology_handoff"]
    if chronology["chronology_resolved"] is not False or chronology["rearranged_fixture_id_count"] != 250:
        raise ValueError("PR110 chronology premise changed")

    mapping = pr108.load_fotmob_primary_id_competition_mapping_qualification_receipt()
    target_primary_ids = {item["fotmob_primary_id"] for item in mapping["records"]}
    special_states = {row[0] for row in pr109.STATE_SPECS}

    all_rows: list[dict[str, Any]] = []
    dates: set[str] = set()
    response_count = 0
    with tempfile.TemporaryDirectory(prefix="athena-fotmob-chronology-") as tmp:
        cache = _extract_cache(artifact, Path(tmp))
        with tarfile.open(cache, "r:gz") as archive:
            for member in archive:
                if not member.isfile() or not member.name.endswith("/response.json"):
                    continue
                request_date, capture_id = member.name.split("/")[-3:-1]
                payload = json.load(archive.extractfile(member))
                response_count += 1
                dates.add(request_date)
                for league in payload["leagues"]:
                    if league.get("primaryId") not in target_primary_ids:
                        continue
                    for match in league["matches"]:
                        all_rows.append(_row(request_date, capture_id, league, match))

    if response_count != 4_410 or len(dates) != 2_205:
        raise ValueError("campaign coverage changed")

    special_ids = {
        row["fixture_id"] for row in all_rows if row["state_id"] in special_states
    }
    if len(special_ids) != 295:
        raise ValueError("special-fixture membership changed")

    grouped: dict[tuple[str, int], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in all_rows:
        if row["fixture_id"] in special_ids:
            grouped[(row["request_date"], row["fixture_id"])].append(row)

    collapsed: list[dict[str, Any]] = []
    pair_cardinality_mismatch = 0
    pair_conflict_count = 0
    for key in sorted(grouped):
        rows = grouped[key]
        if len(rows) != 2:
            pair_cardinality_mismatch += 1
            continue
        left = {k: v for k, v in rows[0].items() if k != "capture_id"}
        right = {k: v for k, v in rows[1].items() if k != "capture_id"}
        if _canonical(left) != _canonical(right):
            pair_conflict_count += 1
            continue
        left["capture_ids"] = sorted([rows[0]["capture_id"], rows[1]["capture_id"]])
        collapsed.append(left)

    if pair_cardinality_mismatch or pair_conflict_count:
        raise ValueError("same-date campaign pair evidence drift")
    if len(collapsed) != 547 or any(row["state_id"] == "OTHER" for row in collapsed):
        raise ValueError("special-fixture history shape changed")

    full_history_projection = b"".join(
        _canonical(row)
        for row in sorted(
            collapsed,
            key=lambda row: (row["fixture_id"], row["request_date"], row["state_id"]),
        )
    )
    pr110_source = pr110_receipt["source_evidence"]
    if (
        len(full_history_projection),
        hashlib.sha256(full_history_projection).hexdigest(),
    ) != (
        pr110_source["special_fixture_history_projection_size_bytes"],
        pr110_source["special_fixture_history_projection_sha256"],
    ):
        raise ValueError("PR110 special-fixture history projection changed")

    sequences: dict[int, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in sorted(collapsed, key=lambda row: (row["fixture_id"], row["request_date"])):
        sequences[row["fixture_id"]].append(row)
    rearranged = {
        fixture_id: rows
        for fixture_id, rows in sequences.items()
        if len(rows) > 1
        and len({(row["state_id"], row["kickoff_utc"]) for row in rows}) > 1
    }
    if len(rearranged) != 250:
        raise ValueError("rearranged fixture membership changed")

    rearranged_rows = [row for rows in rearranged.values() for row in rows]
    rearranged_projection = b"".join(
        _canonical(row)
        for row in sorted(
            rearranged_rows,
            key=lambda row: (row["fixture_id"], row["request_date"], row["state_id"]),
        )
    )
    if (
        len(rearranged_projection),
        hashlib.sha256(rearranged_projection).hexdigest(),
    ) != (REARRANGED_HISTORY_PROJECTION_SIZE, REARRANGED_HISTORY_PROJECTION_SHA256):
        raise ValueError("rearranged history projection changed")

    static_fields = (
        "primary_id",
        "wrapper_league_id",
        "home_team_id",
        "away_team_id",
    )
    static_identity_drift_count = 0
    request_date_mismatch_count = 0
    non_forward_count = 0
    edge_rows: list[dict[str, Any]] = []
    transition_membership: dict[tuple[str, ...], list[int]] = collections.defaultdict(list)
    occurrence_state_counts: collections.Counter[str] = collections.Counter()

    for fixture_id, rows in sorted(rearranged.items()):
        pattern = tuple(row["state_id"] for row in rows)
        transition_membership[pattern].append(fixture_id)
        occurrence_state_counts.update(pattern)
        baseline = {field: rows[0][field] for field in static_fields}
        for row in rows:
            if any(row[field] != baseline[field] for field in static_fields):
                static_identity_drift_count += 1
            if _utc_request_date(row["kickoff_utc"]) != row["request_date"]:
                request_date_mismatch_count += 1
        for edge_index, (left, right) in enumerate(zip(rows, rows[1:]), start=1):
            left_utc = _parse_utc(left["kickoff_utc"])
            right_utc = _parse_utc(right["kickoff_utc"])
            if not right_utc > left_utc:
                non_forward_count += 1
            edge_rows.append(
                {
                    "fixture_id": fixture_id,
                    "edge_index": edge_index,
                    "primary_id": left["primary_id"],
                    "wrapper_league_id": left["wrapper_league_id"],
                    "home_team_id": left["home_team_id"],
                    "away_team_id": left["away_team_id"],
                    "from_request_date": left["request_date"],
                    "to_request_date": right["request_date"],
                    "from_kickoff_utc": left["kickoff_utc"],
                    "to_kickoff_utc": right["kickoff_utc"],
                    "from_state_id": left["state_id"],
                    "to_state_id": right["state_id"],
                    "kickoff_delta_seconds": int((right_utc - left_utc).total_seconds()),
                }
            )

    edge_projection = b"".join(_canonical(row) for row in edge_rows)
    if (len(edge_projection), hashlib.sha256(edge_projection).hexdigest()) != (
        EDGE_PROJECTION_SIZE,
        EDGE_PROJECTION_SHA256,
    ):
        raise ValueError("rearrangement edge projection changed")

    expected_patterns = {
        tuple(spec[1]): spec[2] for spec in pr111.TRANSITION_SPECS
    }
    actual_patterns = {
        pattern: len(fixture_ids) for pattern, fixture_ids in transition_membership.items()
    }
    unknown_pattern_count = sum(
        count for pattern, count in actual_patterns.items() if pattern not in expected_patterns
    )
    if actual_patterns != expected_patterns or unknown_pattern_count:
        raise ValueError("transition pattern evidence changed")
    if static_identity_drift_count or request_date_mismatch_count or non_forward_count:
        raise ValueError("chronology integrity check failed")
    if len(rearranged_rows) != 502 or len(edge_rows) != 252:
        raise ValueError("chronology occurrence or edge count changed")

    expected_state_counts = {
        "POSTPONED": 239,
        "ABANDONED": 7,
        "CANCELLED": 5,
        "ORDINARY_FT": 243,
        "AWARDED_WIN": 8,
    }
    if dict(occurrence_state_counts) != expected_state_counts:
        raise ValueError("chronology state-occurrence counts changed")

    transition_records = []
    for spec in pr111.TRANSITION_SPECS:
        pattern_id, pattern, fixture_count, _, terminal_disposition = spec
        fixture_ids = sorted(transition_membership[tuple(pattern)])
        transition_records.append(
            {
                "pattern_id": pattern_id,
                "pattern": list(pattern),
                "fixture_id_count": fixture_count,
                "fixture_ids": fixture_ids,
                "transition_edge_count": fixture_count * (len(pattern) - 1),
                "terminal_state": pattern[-1],
                "terminal_disposition": terminal_disposition,
            }
        )

    ordinary_terminal = sum(
        record["fixture_id_count"]
        for record in transition_records
        if record["terminal_state"] == "ORDINARY_FT"
    )
    awarded_terminal = sum(
        record["fixture_id_count"]
        for record in transition_records
        if record["terminal_state"] == "AWARDED_WIN"
    )
    if (ordinary_terminal, awarded_terminal) != (243, 7):
        raise ValueError("terminal chronology counts changed")

    awarded_repeat = transition_membership[("AWARDED_WIN", "AWARDED_WIN")]
    if awarded_repeat != [3_932_603]:
        raise ValueError("duplicate awarded fixture changed")
    duplicate_rows = rearranged[3_932_603]
    if [row["request_date"] for row in duplicate_rows] != ["20230220", "20230305"]:
        raise ValueError("duplicate awarded request dates changed")

    safety = {
        key: False
        for key in sorted(
            {
                "bet_authorized",
                "calibration_for_production_authorized",
                "competition_registry_mutation_authorized",
                "expected_goals_production_authorized",
                "expected_goals_transform_approved",
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
                "special_result_history_rows_authorized",
                "successor_candidate_approved",
                "successor_live_inputs_qualified",
            }
        )
    }

    receipt = {
        "schema_version": 1,
        "dataset_name": "athena-fotmob-source-history-rearrangement-chronology-qualification-v1",
        "scope": "IMMUTABLE_REARRANGEMENT_CHRONOLOGY_QUALIFICATION_RECEIPT_ONLY",
        "repository_main_anchor": REPOSITORY_MAIN_ANCHOR,
        "protocol": {
            "protocol_id": pr111.PROTOCOL_ID,
            "blob_sha": PR111_BLOB_SHA,
            "canonical_sha256": pr111.PROTOCOL_SHA256,
            "canonical_size_bytes": pr111.PROTOCOL_SIZE,
        },
        "source_evidence": {
            "artifact_id": pr110_source["artifact_id"],
            "artifact_name": pr110_source["artifact_name"],
            "artifact_sha256": ARTIFACT_SHA256,
            "artifact_size_bytes": ARTIFACT_SIZE,
            "research_cache_tar_gz_sha256": CACHE_SHA256,
            "research_cache_tar_gz_size_bytes": CACHE_SIZE,
            "pr110_receipt_sha256": pr110.RECEIPT_SHA256,
            "pr110_receipt_size_bytes": pr110.RECEIPT_SIZE,
            "pr110_special_fixture_history_projection_sha256": pr110_source[
                "special_fixture_history_projection_sha256"
            ],
            "pr110_special_fixture_history_projection_size_bytes": pr110_source[
                "special_fixture_history_projection_size_bytes"
            ],
            "request_date_count": pr110_source["request_date_count"],
            "response_file_count": pr110_source["response_file_count"],
            "rearranged_fixture_history_projection_sha256": REARRANGED_HISTORY_PROJECTION_SHA256,
            "rearranged_fixture_history_projection_size_bytes": REARRANGED_HISTORY_PROJECTION_SIZE,
            "rearrangement_edge_projection_sha256": EDGE_PROJECTION_SHA256,
            "rearrangement_edge_projection_size_bytes": EDGE_PROJECTION_SIZE,
        },
        "qualification_state": (
            "EXECUTED_REARRANGEMENT_CHRONOLOGY_QUALIFIED_HISTORY_MATERIALIZATION_UNREVIEWED"
        ),
        "chronology_semantics_execution_performed": True,
        "rearrangement_chronology_qualified": True,
        "resolved_blocker": "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT",
        "remaining_blockers": [
            "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN",
            "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",
        ],
        "checks": {
            "rearranged_fixture_id_count": 250,
            "rearranged_fixture_date_occurrence_count": 502,
            "raw_same_date_capture_observation_count": 1004,
            "same_date_pair_count": 502,
            "same_date_pair_capture_count_mismatch_count": pair_cardinality_mismatch,
            "same_date_pair_relevant_field_conflict_count": pair_conflict_count,
            "cross_date_transition_edge_count": 252,
            "cross_date_static_identity_drift_count": static_identity_drift_count,
            "request_date_kickoff_utc_date_mismatch_count": request_date_mismatch_count,
            "non_forward_kickoff_revision_edge_count": non_forward_count,
            "unknown_transition_pattern_count": unknown_pattern_count,
            "exact_six_transition_patterns_observed": True,
            "exact_terminal_state_counts_observed": True,
            "all_raw_and_fixture_date_evidence_preserved": True,
            "destructive_collapse_performed": False,
            "real_world_resume_replay_restart_continuation_inference_performed": False,
        },
        "occurrence_state_counts": expected_state_counts,
        "transition_records": transition_records,
        "terminal_summary": {
            "ordinary_ft_fixture_count": ordinary_terminal,
            "awarded_win_fixture_count": awarded_terminal,
            "ordinary_ft_history_rows_authorized": False,
            "awarded_win_history_rows_authorized": False,
            "duplicate_terminal_awarded_fixture": {
                "fixture_id": 3_932_603,
                "request_dates": ["20230220", "20230305"],
            },
        },
        "source_history_mutation_performed": False,
        "historical_coverage_proven": False,
        "source_capability_registry_mutation_performed": False,
        "competition_registry_mutation_performed": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": safety,
    }

    exact = _canonical(receipt)
    if len(exact) != EXPECTED_RECEIPT_SIZE or hashlib.sha256(exact).hexdigest() != EXPECTED_RECEIPT_SHA256:
        raise ValueError("qualification receipt does not match frozen PR112 identity")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/research-manifests/"
            "fotmob-source-history-rearrangement-chronology-qualification-v1.json"
        ),
    )
    args = parser.parse_args()
    receipt = build_receipt(args.artifact)
    exact = _canonical(receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(exact)
    print(
        f"wrote {args.output} size={len(exact)} "
        f"sha256={hashlib.sha256(exact).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
