#!/usr/bin/env python3
"""Reproduce PR #110 from the exact preserved PR #105 campaign artifact only."""
from __future__ import annotations

import argparse
import collections
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
import domain.fotmob_source_history_special_result_semantics_protocol as pr109

ARTIFACT_SHA256 = "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
ARTIFACT_SIZE = 61_886_753
CACHE_MEMBER = "athena-research-cache.tar.gz"
CACHE_SHA256 = "cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6"
CACHE_SIZE = 61_881_610
REPOSITORY_MAIN_ANCHOR = "2d66af0d176828e1a4efbea2abef6385b694330f"
PR109_BLOB_SHA = "9c9b10d34c9dacffc27ed4d480c71a241b52eff3"
EXPECTED_RECEIPT_SHA256 = "7d6bb5c86391c45abdbb588a27325c99ebf88c4753f75c108387e2c4d3dbb99d"
EXPECTED_RECEIPT_SIZE = 8_558
SPECIAL_PROJECTION_SHA256 = "ad2881eb67bec1988462953acc8d55d59366667b47f3b7c55e026d644b85c990"
SPECIAL_PROJECTION_SIZE = 211_526
HISTORY_PROJECTION_SHA256 = "459c94fd53430663562d9ce614ca2b52b518b6a8f06f6661b27b555c567c281d"
HISTORY_PROJECTION_SIZE = 380_539
NEXT_REQUIRED_BOUNDARY = "PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_REARRANGEMENT_CHRONOLOGY_SEMANTICS_PROTOCOL"


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


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
        state_id, short, short_key, long, long_key, finished, started, cancelled, awarded_rule, _ = row
        if (
            reason.get("short"), reason.get("shortKey"), reason.get("long"), reason.get("longKey"),
            status.get("finished"), status.get("started"), status.get("cancelled"),
        ) != (short, short_key, long, long_key, finished, started, cancelled):
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


def _row(request_date: str, capture_id: str, league: dict[str, Any], match: dict[str, Any]) -> dict[str, Any]:
    status, home, away = match["status"], match["home"], match["away"]
    reason = status.get("reason") or {}
    state = _special_state(match) or ("ORDINARY_FT" if _ordinary_ft(match) else "OTHER")
    return {
        "request_date": request_date, "capture_id": capture_id, "fixture_id": match["id"], "state_id": state,
        "primary_id": league.get("primaryId"), "wrapper_league_id": league.get("id"), "country_code": league.get("ccode"), "league_name": league.get("name"),
        "home_team_id": home.get("id"), "away_team_id": away.get("id"), "kickoff_utc": status.get("utcTime"), "status_id": match.get("statusId"),
        "reason": {"short": reason.get("short"), "shortKey": reason.get("shortKey"), "long": reason.get("long"), "longKey": reason.get("longKey")},
        "finished": status.get("finished"), "started": status.get("started"), "cancelled": status.get("cancelled"),
        "awarded": status.get("awarded", None), "awarded_present": "awarded" in status,
        "home_score": home.get("score"), "away_score": away.get("score"),
        "home_pen_score": home.get("penScore"), "home_pen_score_present": "penScore" in home,
        "away_pen_score": away.get("penScore"), "away_pen_score_present": "penScore" in away,
        "eliminated_team_id": match.get("eliminatedTeamId"), "tournament_stage": match.get("tournamentStage"),
    }


def build_receipt(artifact: Path) -> dict[str, Any]:
    pr109_value = pr109.build_fotmob_source_history_special_result_semantics_protocol()
    pr109_raw = pr109.canonical_fotmob_source_history_special_result_semantics_protocol_bytes(pr109_value)
    if (len(pr109_raw), hashlib.sha256(pr109_raw).hexdigest()) != (pr109.PROTOCOL_SIZE, pr109.PROTOCOL_SHA256):
        raise ValueError("PR109 protocol identity changed")
    mapping = pr108.load_fotmob_primary_id_competition_mapping_qualification_receipt()
    pr105_raw = pr108.PR105_RECEIPT_PATH.read_bytes()
    pr105 = json.loads(pr105_raw)
    target_primary_ids = {item["fotmob_primary_id"] for item in mapping["records"]}

    all_rows: list[dict[str, Any]] = []
    dates: set[str] = set()
    response_count = 0
    with tempfile.TemporaryDirectory(prefix="athena-fotmob-special-") as tmp:
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

    special_ids = {row["fixture_id"] for row in all_rows if row["state_id"] in {item[0] for item in pr109.STATE_SPECS}}
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in all_rows:
        if row["fixture_id"] in special_ids:
            grouped[(row["request_date"], row["fixture_id"])].append(row)
    collapsed: list[dict[str, Any]] = []
    for key in sorted(grouped):
        rows = grouped[key]
        if len(rows) != 2:
            raise ValueError("same-date capture cardinality changed")
        left = {k: v for k, v in rows[0].items() if k != "capture_id"}
        right = {k: v for k, v in rows[1].items() if k != "capture_id"}
        if _canonical(left) != _canonical(right):
            raise ValueError("same-date semantic evidence drift")
        left["capture_ids"] = sorted([rows[0]["capture_id"], rows[1]["capture_id"]])
        collapsed.append(left)
    if any(row["state_id"] == "OTHER" for row in collapsed):
        raise ValueError("unknown variant inside special-fixture history")

    special_states = {item[0] for item in pr109.STATE_SPECS}
    special_rows = [row for row in collapsed if row["state_id"] in special_states]
    special_projection = b"".join(_canonical(row) for row in sorted(special_rows, key=lambda r: (r["request_date"], r["fixture_id"], r["state_id"])))
    history_projection = b"".join(_canonical(row) for row in sorted(collapsed, key=lambda r: (r["fixture_id"], r["request_date"], r["state_id"])))
    if (len(special_projection), hashlib.sha256(special_projection).hexdigest()) != (SPECIAL_PROJECTION_SIZE, SPECIAL_PROJECTION_SHA256):
        raise ValueError("special-state projection changed")
    if (len(history_projection), hashlib.sha256(history_projection).hexdigest()) != (HISTORY_PROJECTION_SIZE, HISTORY_PROJECTION_SHA256):
        raise ValueError("special-fixture history projection changed")

    sequences: dict[int, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in sorted(collapsed, key=lambda r: (r["fixture_id"], r["request_date"])):
        sequences[row["fixture_id"]].append(row)
    rearranged = {fid: rows for fid, rows in sequences.items() if len(rows) > 1 and len({(row["state_id"], row["kickoff_utc"]) for row in rows}) > 1}
    patterns = collections.Counter(tuple(row["state_id"] for row in rows) for rows in rearranged.values())
    expected_patterns = {tuple(item["pattern"]): item["fixture_id_count"] for item in pr105["target_corpus"]["rearrangement_transition_summary"]}
    if dict(patterns) != expected_patterns or len(rearranged) != 250:
        raise ValueError("chronology transition evidence changed")

    terminal = {
        "AWARDED_WIN": pr105["special_result_blockers"]["awarded_win_fixture_ids"],
        "AFTER_EXTRA_TIME": pr105["special_result_blockers"]["after_extra_time_fixture_ids"],
        "AFTER_PENALTIES": pr105["special_result_blockers"]["after_penalties_fixture_ids"],
    }
    unresolved = {
        "ABANDONED": pr105["unresolved_source_states"]["abandoned_fixture_ids"],
        "CANCELLED": pr105["unresolved_source_states"]["cancelled_fixture_ids"],
        "POSTPONED": pr105["unresolved_source_states"]["postponed_fixture_ids"],
    }
    class_records = []
    for spec in pr109.STATE_SPECS:
        state_id, *_, score_semantics = spec
        rows = [row for row in special_rows if row["state_id"] == state_id]
        ids = {row["fixture_id"] for row in rows}
        frozen_terminal = terminal.get(state_id, [])
        frozen_unresolved = unresolved.get(state_id, [])
        if frozen_terminal and ids != set(frozen_terminal):
            raise ValueError(f"{state_id} PR105 terminal membership changed")
        if frozen_unresolved and ids - set(rearranged) != set(frozen_unresolved):
            raise ValueError(f"{state_id} PR105 unresolved membership changed")
        record = {
            "state_id": state_id, "observed_unique_fixture_ids": len(ids), "observed_date_fixture_occurrences": len(rows), "observed_capture_rows": len(rows) * 2,
            "status_ids": sorted({row["status_id"] for row in rows}), "frozen_pr105_terminal_fixture_ids": frozen_terminal, "frozen_pr105_unresolved_fixture_ids": frozen_unresolved,
            "frozen_membership_match": True, "transition_fixture_id_count": len(ids & set(rearranged)),
            "history_disposition": pr109.ORDINARY_HISTORY_DISPOSITION, "preservation_disposition": pr109.PRESERVATION_DISPOSITION, "score_semantics": score_semantics,
        }
        if state_id == "AFTER_PENALTIES":
            record["penalty_occurrences_with_both_pen_scores"] = sum(row["home_pen_score_present"] and row["away_pen_score_present"] for row in rows)
            record["penalty_occurrences_with_eliminated_team_id"] = sum(row["eliminated_team_id"] is not None for row in rows)
        if state_id in {"ABANDONED", "CANCELLED", "POSTPONED"}:
            record["nonzero_score_occurrence_count"] = sum((row["home_score"] or 0) != 0 or (row["away_score"] or 0) != 0 for row in rows)
        class_records.append(record)

    safety = {key: False for key in sorted({
        "bet_authorized", "calibration_for_production_authorized", "competition_registry_mutation_authorized", "expected_goals_production_authorized",
        "expected_goals_transform_approved", "market_activation_authorized", "model_training_authorized", "ordinary_ft_history_extension_authorized",
        "pr80_constructor_input_authorized", "pricing_authorized", "probability_adjustment_authorized", "probability_inference_authorized",
        "production_approval_authorized", "rearrangement_chronology_resolved", "score_matrix_authorized", "selection_authorized",
        "source_history_adapter_approved", "source_history_completeness_proven", "special_result_history_rows_authorized", "successor_candidate_approved",
        "successor_live_inputs_qualified",
    })}
    receipt = {
        "schema_version": 1, "dataset_name": "athena-fotmob-source-history-special-result-semantics-qualification-v1",
        "scope": "IMMUTABLE_SPECIAL_RESULT_SEMANTICS_QUALIFICATION_RECEIPT_ONLY", "repository_main_anchor": REPOSITORY_MAIN_ANCHOR,
        "protocol": {"protocol_id": pr109.PROTOCOL_ID, "blob_sha": PR109_BLOB_SHA, "canonical_sha256": pr109.PROTOCOL_SHA256, "canonical_size_bytes": pr109.PROTOCOL_SIZE},
        "source_evidence": {
            "artifact_id": pr105["artifact"]["artifact_id"], "artifact_name": pr105["artifact"]["artifact_name"], "artifact_sha256": ARTIFACT_SHA256, "artifact_size_bytes": ARTIFACT_SIZE,
            "research_cache_tar_gz_sha256": CACHE_SHA256, "research_cache_tar_gz_size_bytes": CACHE_SIZE,
            "pr105_receipt_sha256": pr109.PR105_RECEIPT_SHA256, "pr105_receipt_size_bytes": pr109.PR105_RECEIPT_SIZE,
            "pr108_receipt_sha256": pr109.PR108_RECEIPT_SHA256, "pr108_receipt_size_bytes": pr109.PR108_RECEIPT_SIZE,
            "pr105_special_projection_sha256": pr109.SPECIAL_PROJECTION_SHA256, "pr105_special_projection_size_bytes": pr109.SPECIAL_PROJECTION_SIZE,
            "pr105_unresolved_projection_sha256": pr109.UNRESOLVED_PROJECTION_SHA256, "pr105_unresolved_projection_size_bytes": pr109.UNRESOLVED_PROJECTION_SIZE,
            "request_date_count": len(dates), "response_file_count": response_count,
            "special_state_projection_sha256": SPECIAL_PROJECTION_SHA256, "special_state_projection_size_bytes": SPECIAL_PROJECTION_SIZE,
            "special_fixture_history_projection_sha256": HISTORY_PROJECTION_SHA256, "special_fixture_history_projection_size_bytes": HISTORY_PROJECTION_SIZE,
            "special_state_unique_fixture_id_count": len(special_ids), "special_state_date_fixture_occurrence_count": len(special_rows),
            "special_state_capture_observation_count": len(special_rows) * 2, "special_fixture_history_date_fixture_occurrence_count": len(collapsed),
        },
        "qualification_state": "EXECUTED_SPECIAL_RESULT_SEMANTICS_QUALIFIED_CHRONOLOGY_UNRESOLVED",
        "special_result_semantics_execution_performed": True, "special_result_semantics_qualified": True, "class_records": class_records,
        "checks": {
            "exact_six_reviewed_state_signatures_observed": True, "frozen_pr105_special_finished_membership_accounted": True,
            "frozen_pr105_unresolved_membership_accounted": True, "same_date_pair_count": len(special_rows),
            "same_date_pair_capture_count_mismatch_count": 0, "same_date_pair_semantic_or_relevant_field_conflict_count": 0,
            "unknown_variant_count_within_special_fixture_history": 0, "penalty_base_and_pen_score_fields_kept_separate": True,
            "nonresult_score_scalars_not_promoted": True, "special_states_excluded_from_ordinary_regulation_time_model_history": True,
        },
        "chronology_handoff": {
            "rearranged_fixture_id_count": len(rearranged), "chronology_resolved": False, "collapsed_to_final_observation": False,
            "duplicate_terminal_awarded_fixture": pr105["special_result_blockers"]["duplicate_terminal_awarded_fixture"],
            "transition_summary": pr105["target_corpus"]["rearrangement_transition_summary"],
        },
        "source_history_mutation_performed": False, "competition_registry_mutation_performed": False, "source_capability_registry_mutation_performed": False,
        "historical_coverage_proven": False, "resolved_blocker": "BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW",
        "remaining_blockers": ["BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT", "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN", "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"],
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY, "safety": safety,
    }
    raw = _canonical(receipt)
    if len(raw) != EXPECTED_RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != EXPECTED_RECEIPT_SHA256:
        raise ValueError("qualification receipt identity changed")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_zip", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = _canonical(build_receipt(args.artifact_zip))
    if args.output is None:
        import sys
        sys.stdout.buffer.write(raw)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
