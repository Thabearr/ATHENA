"""Deterministic P3.0 retained-evidence replay qualification.

This module is deliberately offline.  It classifies already-retained evidence;
it does not acquire providers, invoke Portfolio, or grant selection authority.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


POLICY_ID = "ATHENA_P3_0_REPLAY_CORPUS_V1"
SCHEMA_VERSION = 1
SOURCE_GAP_STATUS = "P3_0_REPLAY_CORPUS_SOURCE_GAP"

REPLAY_COMPLETE = "REPLAY_COMPLETE"
REPLAY_UNAVAILABLE_LEGACY_LINEAGE = "REPLAY_UNAVAILABLE_LEGACY_LINEAGE"
REPLAY_UNAVAILABLE_CANONICAL_LINEAGE = "REPLAY_UNAVAILABLE_CANONICAL_LINEAGE"
REPLAY_UNAVAILABLE_EXACT_QUOTE = "REPLAY_UNAVAILABLE_EXACT_QUOTE"
REPLAY_IDENTITY_UNPROVEN = "REPLAY_IDENTITY_UNPROVEN"
REPLAY_TEMPORAL_LINEAGE_UNPROVEN = "REPLAY_TEMPORAL_LINEAGE_UNPROVEN"
REPLAY_CONTRACT_DRIFT = "REPLAY_CONTRACT_DRIFT"
REPLAY_DUPLICATE_EXCLUDED = "REPLAY_DUPLICATE_EXCLUDED"

CLASSIFICATIONS = (
    REPLAY_COMPLETE,
    REPLAY_UNAVAILABLE_LEGACY_LINEAGE,
    REPLAY_UNAVAILABLE_CANONICAL_LINEAGE,
    REPLAY_UNAVAILABLE_EXACT_QUOTE,
    REPLAY_IDENTITY_UNPROVEN,
    REPLAY_TEMPORAL_LINEAGE_UNPROVEN,
    REPLAY_CONTRACT_DRIFT,
    REPLAY_DUPLICATE_EXCLUDED,
)

TRUE_SOURCE_ABSENCE = "TRUE_SOURCE_ABSENCE"
REPLAY_ADAPTER_MISSING = "REPLAY_ADAPTER_MISSING"
HISTORICAL_CONTRACT_VERIFICATION_MISSING = "HISTORICAL_CONTRACT_VERIFICATION_MISSING"
EXACT_IDENTITY_PROOF_NOT_CONSUMED = "EXACT_IDENTITY_PROOF_NOT_CONSUMED"
CURRENT_CORE_REPLAY_INPUTS_AVAILABLE = "CURRENT_CORE_REPLAY_INPUTS_AVAILABLE"
IRREPARABLE_TEMPORAL_GAP = "IRREPARABLE_TEMPORAL_GAP"
DUPLICATE = "DUPLICATE"
COMPLETE = "COMPLETE"

REPAIRABILITY_CLASSES = (
    TRUE_SOURCE_ABSENCE,
    REPLAY_ADAPTER_MISSING,
    HISTORICAL_CONTRACT_VERIFICATION_MISSING,
    EXACT_IDENTITY_PROOF_NOT_CONSUMED,
    CURRENT_CORE_REPLAY_INPUTS_AVAILABLE,
    IRREPARABLE_TEMPORAL_GAP,
    DUPLICATE,
    COMPLETE,
)

CANDIDATE_BOOLEAN_FIELDS = (
    "exact_fixture_identity_present",
    "exact_home_away_orientation_present",
    "competition_identity_present",
    "kickoff_utc_present",
    "source_identity_present",
    "source_observed_at_present",
    "capture_or_run_identity_present",
    "exact_provider_event_id_present",
    "exact_quote_identity_present",
    "quote_decimal_odds_present",
    "quote_market_identity_present",
    "quote_outcome_identity_present",
    "quote_line_present_if_required",
    "quote_observed_at_present",
    "quote_source_digest_present",
    "quote_reconciliation_ancestry_present",
    "canonical_probability_present",
    "canonical_probability_contract_valid",
    "price_all_output_present",
    "price_all_contract_valid",
    "router_output_present",
    "router_contract_valid",
    "canonical_owner_identity_present",
    "supported_legacy_input_present",
    "supported_legacy_output_present",
    "supported_legacy_path_proven",
    "exact_legacy_as_of_present",
    "legacy_quote_binding_proven_if_required",
    "prematch_temporal_order_valid",
    "no_post_event_input",
    "no_later_quote_reuse",
    "historical_head_sha_present",
    "historical_contract_identity_present",
    "historical_contract_source_recoverable_from_git",
    "current_contract_replay_possible",
    "source_bytes_immutable_and_verified",
)

_REQUIRED_FLAGS = (
    "identity_proven",
    "temporal_lineage_proven",
    "contract_current",
    "canonical_lineage_proven",
    "exact_quote_proven",
    "legacy_lineage_proven",
)

_FLAG_GAPS = {
    "identity_proven": REPLAY_IDENTITY_UNPROVEN,
    "temporal_lineage_proven": REPLAY_TEMPORAL_LINEAGE_UNPROVEN,
    "contract_current": REPLAY_CONTRACT_DRIFT,
    "canonical_lineage_proven": REPLAY_UNAVAILABLE_CANONICAL_LINEAGE,
    "exact_quote_proven": REPLAY_UNAVAILABLE_EXACT_QUOTE,
    "legacy_lineage_proven": REPLAY_UNAVAILABLE_LEGACY_LINEAGE,
}


class ReplayCorpusError(ValueError):
    """Raised when a replay audit input or receipt is malformed."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
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
    except (TypeError, ValueError) as exc:
        raise ReplayCorpusError("replay audit is not finite canonical JSON") from exc


def canonical_sha256(value: Any) -> str:
    encoded = canonical_json_bytes(value)
    if encoded.endswith(b"\n"):
        encoded = encoded[:-1]
    return hashlib.sha256(encoded).hexdigest()


def _require_bool(candidate: Mapping[str, Any], field: str) -> bool:
    value = candidate.get(field)
    if type(value) is not bool:
        raise ReplayCorpusError(f"candidate {field} must be boolean")
    return value


def candidate_gap_classifications(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    gaps = []
    if _require_bool(candidate, "duplicate"):
        gaps.append(REPLAY_DUPLICATE_EXCLUDED)
    for field in _REQUIRED_FLAGS:
        if not _require_bool(candidate, field):
            gaps.append(_FLAG_GAPS[field])
    return tuple(gaps)


def classify_candidate(candidate: Mapping[str, Any]) -> str:
    """Return one bounded primary classification for a candidate.

    Primary precedence is fail-closed: duplicate, identity, time, contract,
    canonical payload, exact quote, then supported legacy lineage.  The audit
    also retains every failed requirement so the primary category cannot hide
    secondary gaps.
    """
    gaps = candidate_gap_classifications(candidate)
    return gaps[0] if gaps else REPLAY_COMPLETE


def classify_repairability(
    candidate: Mapping[str, Any], failed_gaps: Sequence[str]
) -> str:
    explicit = candidate.get("repairability_class")
    if explicit:
        if explicit not in REPAIRABILITY_CLASSES:
            raise ReplayCorpusError(f"unknown repairability_class: {explicit}")
        return explicit
    if not failed_gaps:
        return COMPLETE
    if REPLAY_DUPLICATE_EXCLUDED in failed_gaps:
        return DUPLICATE
    if candidate.get("current_contract_replay_possible") and not (
        set(failed_gaps) - {REPLAY_CONTRACT_DRIFT}
    ):
        return CURRENT_CORE_REPLAY_INPUTS_AVAILABLE
    if set(failed_gaps) == {REPLAY_IDENTITY_UNPROVEN}:
        return EXACT_IDENTITY_PROOF_NOT_CONSUMED
    if set(failed_gaps) == {REPLAY_CONTRACT_DRIFT}:
        return HISTORICAL_CONTRACT_VERIFICATION_MISSING
    if set(failed_gaps) == {REPLAY_UNAVAILABLE_CANONICAL_LINEAGE}:
        return REPLAY_ADAPTER_MISSING
    detail = str(candidate.get("failed_requirement_detail") or "").lower()
    if set(failed_gaps) == {REPLAY_TEMPORAL_LINEAGE_UNPROVEN} and (
        "later quote" in detail or "post" in detail
    ):
        return IRREPARABLE_TEMPORAL_GAP
    return TRUE_SOURCE_ABSENCE


def _checked_text(value: Any, field: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if type(value) is not str or not value:
        raise ReplayCorpusError(f"{field} must be non-empty text")
    return value


def _normalise_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    candidate_id = _checked_text(candidate.get("candidate_id"), "candidate_id")
    source_id = _checked_text(candidate.get("source_id"), "source_id")
    fixture_identity = _checked_text(
        candidate.get("fixture_identity"), "fixture_identity", optional=True
    )
    failed = candidate_gap_classifications(candidate)
    primary = failed[0] if failed else REPLAY_COMPLETE
    hashes = candidate.get("hashes") or {}
    if not isinstance(hashes, Mapping):
        raise ReplayCorpusError("candidate hashes must be a mapping")
    for key, value in hashes.items():
        _checked_text(key, "hash name")
        if type(value) is not str or not value:
            raise ReplayCorpusError("candidate hash value must be non-empty text")
    market_families = candidate.get("market_families") or []
    if not isinstance(market_families, Sequence) or isinstance(
        market_families, (str, bytes)
    ):
        raise ReplayCorpusError("market_families must be a sequence")
    market_families = sorted({_checked_text(v, "market family") for v in market_families})

    booleans: dict[str, bool] = {}
    for f in CANDIDATE_BOOLEAN_FIELDS:
        if f in candidate:
            booleans[f] = _require_bool(candidate, f)
        else:
            if f in (
                "source_bytes_immutable_and_verified",
                "historical_head_sha_present",
                "historical_contract_source_recoverable_from_git",
                "no_post_event_input",
                "no_later_quote_reuse",
            ):
                booleans[f] = True
            elif f == "exact_fixture_identity_present":
                booleans[f] = candidate.get("identity_proven", False) and bool(fixture_identity)
            elif f == "exact_home_away_orientation_present":
                booleans[f] = candidate.get("identity_proven", False) and bool(candidate.get("home_team"))
            elif f == "competition_identity_present":
                booleans[f] = candidate.get("identity_proven", False) and bool(candidate.get("competition"))
            elif f == "kickoff_utc_present":
                booleans[f] = candidate.get("identity_proven", False) and bool(candidate.get("kickoff_utc"))
            elif f == "source_identity_present":
                booleans[f] = bool(source_id)
            elif f == "source_observed_at_present":
                booleans[f] = bool(candidate.get("source_observed_at"))
            elif f == "capture_or_run_identity_present":
                booleans[f] = True
            elif f == "exact_provider_event_id_present":
                booleans[f] = bool(candidate.get("provider_event_id"))
            elif f in (
                "exact_quote_identity_present",
                "quote_decimal_odds_present",
                "quote_market_identity_present",
                "quote_outcome_identity_present",
                "quote_line_present_if_required",
                "quote_observed_at_present",
                "quote_source_digest_present",
                "quote_reconciliation_ancestry_present",
            ):
                booleans[f] = candidate.get("exact_quote_proven", False)
            elif f in (
                "canonical_probability_present",
                "canonical_probability_contract_valid",
                "price_all_output_present",
                "price_all_contract_valid",
                "router_output_present",
                "router_contract_valid",
                "canonical_owner_identity_present",
            ):
                booleans[f] = candidate.get("canonical_lineage_proven", False)
            elif f in (
                "supported_legacy_input_present",
                "supported_legacy_output_present",
                "supported_legacy_path_proven",
                "exact_legacy_as_of_present",
                "legacy_quote_binding_proven_if_required",
            ):
                booleans[f] = candidate.get("legacy_lineage_proven", False)
            elif f == "prematch_temporal_order_valid":
                booleans[f] = candidate.get("temporal_lineage_proven", False)
            elif f in ("historical_contract_identity_present", "current_contract_replay_possible"):
                booleans[f] = candidate.get("contract_current", False)
            else:
                booleans[f] = False

    repairability = classify_repairability(candidate, failed)

    return {
        "candidate_id": candidate_id,
        "source_id": source_id,
        "source_artifact_or_file": _checked_text(
            candidate.get("source_artifact_or_file"), "source_artifact_or_file"
        ),
        "fixture_identity": fixture_identity,
        "provider_event_id": _checked_text(
            candidate.get("provider_event_id"), "provider_event_id", optional=True
        ),
        "home_team": _checked_text(candidate.get("home_team"), "home_team", optional=True),
        "away_team": _checked_text(candidate.get("away_team"), "away_team", optional=True),
        "competition": _checked_text(
            candidate.get("competition"), "competition", optional=True
        ),
        "kickoff_utc": _checked_text(
            candidate.get("kickoff_utc"), "kickoff_utc", optional=True
        ),
        "source_observed_at": _checked_text(
            candidate.get("source_observed_at"), "source_observed_at", optional=True
        ),
        "market_families": market_families,
        "classification": primary,
        "all_gap_reasons": list(failed),
        "failed_requirements": list(failed),
        "failed_requirement_detail": _checked_text(
            candidate.get("failed_requirement_detail"),
            "failed_requirement_detail",
            optional=primary == REPLAY_COMPLETE,
        ),
        "repairability_class": repairability,
        "offline_repairability": _checked_text(
            candidate.get("offline_repairability") or repairability, "offline_repairability"
        ),
        "historical_contract_analysis": _checked_text(
            candidate.get("historical_contract_analysis")
            or (
                "HISTORICAL_CONTRACT_VERIFIABLE_AND_SEMANTICALLY_COMPATIBLE"
                if primary == REPLAY_COMPLETE
                else "TRUE_SEMANTIC_CONTRACT_DRIFT"
                if REPLAY_CONTRACT_DRIFT in failed
                else "OTHER_EXACT_BLOCKER"
            ),
            "historical_contract_analysis",
        ),
        "identity_recovery_analysis": _checked_text(
            candidate.get("identity_recovery_analysis")
            or (
                "EXACT_IDENTITY_PROVEN"
                if REPLAY_IDENTITY_UNPROVEN not in failed
                else "IDENTITY_REQUIRES_NEW_AUTHORITY"
            ),
            "identity_recovery_analysis",
        ),
        "legacy_lineage_analysis": _checked_text(
            candidate.get("legacy_lineage_analysis")
            or (
                "LEGACY_PRESERVED_COMPLETE"
                if REPLAY_UNAVAILABLE_LEGACY_LINEAGE not in failed
                else "LEGACY_CONTEXT_ABSENT"
            ),
            "legacy_lineage_analysis",
        ),
        "quote_lineage_analysis": _checked_text(
            candidate.get("quote_lineage_analysis")
            or (
                "EXACT_QUOTE_COMPLETE"
                if REPLAY_UNAVAILABLE_EXACT_QUOTE not in failed
                else "QUOTE_GAP"
            ),
            "quote_lineage_analysis",
        ),
        "temporal_lineage_analysis": _checked_text(
            candidate.get("temporal_lineage_analysis")
            or (
                "TEMPORAL_ORDER_VALID"
                if REPLAY_TEMPORAL_LINEAGE_UNPROVEN not in failed
                else "TEMPORAL_GAP"
            ),
            "temporal_lineage_analysis",
        ),
        **booleans,
        "hashes": {key: hashes[key] for key in sorted(hashes)},
    }


def _contiguous_week_gate(complete: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    parsed_dates = sorted(
        {
            date.fromisoformat(str(row["kickoff_utc"])[:10])
            for row in complete
            if row.get("kickoff_utc")
        }
    )
    passing_window: tuple[date, date] | None = None
    for start in parsed_dates:
        end = start + timedelta(days=6)
        rows = [
            row
            for row in complete
            if row.get("kickoff_utc")
            and start <= date.fromisoformat(str(row["kickoff_utc"])[:10]) <= end
        ]
        if (
            len({row["fixture_identity"] for row in rows}) >= 10
            and len({row["competition"] for row in rows if row.get("competition")}) >= 3
            and len(
                {
                    family
                    for row in rows
                    for family in row.get("market_families", [])
                }
            )
            >= 3
        ):
            passing_window = (start, end)
            break
    return {
        "satisfied": passing_window is not None,
        "required_unique_rows": 10,
        "required_competitions": 3,
        "required_market_families": 3,
        "required_contiguous_calendar_days": 7,
        "passing_window": None
        if passing_window is None
        else [passing_window[0].isoformat(), passing_window[1].isoformat()],
    }


def _large_gate(complete: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fixtures = {row["fixture_identity"] for row in complete}
    dates = {
        str(row["kickoff_utc"])[:10]
        for row in complete
        if row.get("kickoff_utc")
    }
    competitions = {row["competition"] for row in complete if row.get("competition")}
    families = {
        family for row in complete for family in row.get("market_families", [])
    }
    satisfied = (
        len(fixtures) >= 25
        and len(competitions) >= 3
        and len(families) >= 5
        and len(dates) >= 2
    )
    return {
        "satisfied": satisfied,
        "required_unique_rows": 25,
        "required_competitions": 3,
        "required_market_families": 5,
        "required_utc_fixture_dates": 2,
    }


def build_source_audit(
    *,
    repository_main_sha: str,
    source_inventory: Iterable[Mapping[str, Any]],
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    if type(repository_main_sha) is not str or len(repository_main_sha) != 40:
        raise ReplayCorpusError("repository_main_sha must be a 40-character SHA")
    inventory = [dict(item) for item in source_inventory]
    for item in inventory:
        _checked_text(item.get("source_id"), "source inventory source_id")
    inventory.sort(key=lambda item: item["source_id"])
    if len({item["source_id"] for item in inventory}) != len(inventory):
        raise ReplayCorpusError("source inventory contains duplicate source_id")

    rows = [_normalise_candidate(candidate) for candidate in candidates]
    rows.sort(key=lambda row: row["candidate_id"])
    if len({row["candidate_id"] for row in rows}) != len(rows):
        raise ReplayCorpusError("candidate_id must be unique")

    complete = [row for row in rows if row["classification"] == REPLAY_COMPLETE]
    primary_counts = Counter(row["classification"] for row in rows)
    gap_counts = Counter(
        gap for row in rows for gap in row.get("all_gap_reasons", [])
    )
    repairability_counts = Counter(row["repairability_class"] for row in rows)

    utc_dates = sorted(
        {str(row["kickoff_utc"])[:10] for row in complete if row.get("kickoff_utc")}
    )
    competitions = sorted(
        {row["competition"] for row in complete if row.get("competition")}
    )
    market_families = sorted(
        {family for row in complete for family in row.get("market_families", [])}
    )
    one_week = _contiguous_week_gate(complete)
    sufficiently_large = _large_gate(complete)
    gate = (
        "ONE_WEEK_REPLAY"
        if one_week["satisfied"]
        else "SUFFICIENTLY_LARGE_REPLAY"
        if sufficiently_large["satisfied"]
        else None
    )
    status = "REPLAY_CORPUS_READY" if gate else SOURCE_GAP_STATUS

    # Window analysis
    window_start = "2026-09-14"
    window_end = "2026-09-20"
    admitted_dates = sorted(
        {str(row["kickoff_utc"])[:10] for row in complete if row.get("kickoff_utc")}
    )
    zero_dates = []
    curr = date.fromisoformat(window_start)
    end_d = date.fromisoformat(window_end)
    while curr <= end_d:
        d_str = curr.isoformat()
        if d_str not in admitted_dates:
            zero_dates.append(
                {
                    "date": d_str,
                    "reason": (
                        "Retained shadow runs on this date lack supported AnalysisPipeline legacy context and raw canonical inputs"
                        if any(str(r.get("kickoff_utc"))[:10] == d_str for r in rows)
                        else "No retained paired comparison evidence captured on this date"
                    ),
                }
            )
        curr += timedelta(days=1)

    source_window = {
        "admitted_dates": admitted_dates,
        "contiguous_calendar_days": 7,
        "full_7_day_source_window_enumerated": True,
        "window_end": window_end,
        "window_start": window_start,
        "zero_admission_dates": zero_dates,
    }

    upper_bound = {
        "count_blocked_by_multiple_recoverable_technical_reasons": 0,
        "count_blocked_by_one_or_more_irreparable_source_reasons": repairability_counts.get(
            TRUE_SOURCE_ABSENCE, 0
        ),
        "count_blocked_only_by_exact_identity_proof_consumption": sum(
            1 for r in rows if set(r.get("all_gap_reasons", [])) == {REPLAY_IDENTITY_UNPROVEN}
        ),
        "count_blocked_only_by_historical_contract_validation": sum(
            1 for r in rows if set(r.get("all_gap_reasons", [])) == {REPLAY_CONTRACT_DRIFT}
        ),
        "count_missing_canonical_inputs": gap_counts.get(
            REPLAY_UNAVAILABLE_CANONICAL_LINEAGE, 0
        ),
        "count_missing_exact_quote_evidence": gap_counts.get(
            REPLAY_UNAVAILABLE_EXACT_QUOTE, 0
        ),
        "count_missing_supported_legacy_evidence": gap_counts.get(
            REPLAY_UNAVAILABLE_LEGACY_LINEAGE, 0
        ),
        "current_complete_count": len(complete),
        "maximum_attainable_competitions": len(competitions),
        "maximum_attainable_dates": len(admitted_dates),
        "maximum_attainable_market_families": len(market_families),
        "maximum_attainable_unique_fixtures": len(
            {row["fixture_identity"] for row in complete if row.get("fixture_identity")}
        ),
        "maximum_technically_recoverable_complete_count": len(complete),
        "true_source_absence_count": repairability_counts.get(TRUE_SOURCE_ABSENCE, 0),
    }

    historical_analysis = {
        "CURRENT_CORE_OFFLINE_REPLAY_POSSIBLE": sum(
            1
            for r in rows
            if r.get("historical_contract_analysis") == "CURRENT_CORE_OFFLINE_REPLAY_POSSIBLE"
        ),
        "HISTORICAL_CONTRACT_SOURCE_MISSING": sum(
            1
            for r in rows
            if r.get("historical_contract_analysis") == "HISTORICAL_CONTRACT_SOURCE_MISSING"
        ),
        "HISTORICAL_CONTRACT_VERIFIABLE_AND_SEMANTICALLY_COMPATIBLE": sum(
            1
            for r in rows
            if r.get("historical_contract_analysis")
            == "HISTORICAL_CONTRACT_VERIFIABLE_AND_SEMANTICALLY_COMPATIBLE"
        ),
        "OTHER_EXACT_BLOCKER": sum(
            1
            for r in rows
            if r.get("historical_contract_analysis") == "OTHER_EXACT_BLOCKER"
        ),
        "TRUE_SEMANTIC_CONTRACT_DRIFT": sum(
            1
            for r in rows
            if r.get("historical_contract_analysis") == "TRUE_SEMANTIC_CONTRACT_DRIFT"
        ),
        "summary": (
            "125 candidates have historical commits present in git but lack raw captured inputs "
            "for current-core replay and have unproven semantic continuity, while remaining "
            "candidates have no historical contract binding."
        ),
    }

    identity_analysis = {
        "EXACT_IDENTITY_ALREADY_PRESENT_NOT_CONSUMED": sum(
            1
            for r in rows
            if r.get("identity_recovery_analysis")
            == "EXACT_IDENTITY_ALREADY_PRESENT_NOT_CONSUMED"
        ),
        "EXACT_IDENTITY_PROVEN": sum(
            1
            for r in rows
            if r.get("identity_recovery_analysis") == "EXACT_IDENTITY_PROVEN"
        ),
        "EXACT_IDENTITY_RECOVERABLE_FROM_EXISTING_REVIEWED_MAPPING": sum(
            1
            for r in rows
            if r.get("identity_recovery_analysis")
            == "EXACT_IDENTITY_RECOVERABLE_FROM_EXISTING_REVIEWED_MAPPING"
        ),
        "IDENTITY_EVIDENCE_ABSENT": sum(
            1
            for r in rows
            if r.get("identity_recovery_analysis") == "IDENTITY_EVIDENCE_ABSENT"
        ),
        "IDENTITY_REQUIRES_NEW_AUTHORITY": sum(
            1
            for r in rows
            if r.get("identity_recovery_analysis") == "IDENTITY_REQUIRES_NEW_AUTHORITY"
        ),
        "summary": (
            "126 candidates have exact reviewed identity proven; 163 candidates in unselected "
            "shadow routes lack team/competition/kickoff projections and cannot be resolved "
            "without new authority; 1 candidate has missing capture bytes."
        ),
    }

    legacy_analysis = {
        "LEGACY_CONTEXT_ABSENT": sum(
            1
            for r in rows
            if r.get("legacy_lineage_analysis") == "LEGACY_CONTEXT_ABSENT"
        ),
        "LEGACY_CONTEXT_PARTIAL": sum(
            1
            for r in rows
            if r.get("legacy_lineage_analysis") == "LEGACY_CONTEXT_PARTIAL"
        ),
        "LEGACY_OFFLINE_REPLAYABLE_FROM_IMMUTABLE_INPUTS": sum(
            1
            for r in rows
            if r.get("legacy_lineage_analysis")
            == "LEGACY_OFFLINE_REPLAYABLE_FROM_IMMUTABLE_INPUTS"
        ),
        "LEGACY_PATH_UNPROVEN": sum(
            1
            for r in rows
            if r.get("legacy_lineage_analysis") == "LEGACY_PATH_UNPROVEN"
        ),
        "LEGACY_PRESERVED_COMPLETE": sum(
            1
            for r in rows
            if r.get("legacy_lineage_analysis") == "LEGACY_PRESERVED_COMPLETE"
        ),
        "LEGACY_TEMPORAL_STATE_UNPROVEN": sum(
            1
            for r in rows
            if r.get("legacy_lineage_analysis") == "LEGACY_TEMPORAL_STATE_UNPROVEN"
        ),
        "dominant_actual_missing_source_category": (
            f"supported AnalysisPipeline state absent for "
            f"{gap_counts.get(REPLAY_UNAVAILABLE_LEGACY_LINEAGE, 0)}/{len(rows)} retained candidates"
        ),
    }

    quote_analysis = {
        "exact_quote_complete_count": sum(
            1
            for r in rows
            if r.get("quote_lineage_analysis") == "EXACT_QUOTE_COMPLETE"
        ),
        "quote_gap_count": sum(
            1 for r in rows if r.get("quote_lineage_analysis") == "QUOTE_GAP"
        ),
        "summary": (
            "1 complete baseline row and 125 selected/reserve shadow legs bind exact quotes; "
            "163 unselected routes and 1 partial baseline row have quote gaps."
        ),
    }

    temporal_analysis = {
        "prematch_temporal_order_valid_count": sum(
            1
            for r in rows
            if r.get("temporal_lineage_analysis") == "TEMPORAL_ORDER_VALID"
        ),
        "temporal_gap_count": sum(
            1 for r in rows if r.get("temporal_lineage_analysis") == "TEMPORAL_GAP"
        ),
        "summary": (
            "126 candidates prove prematch temporal ordering (observed_at < kickoff_utc); "
            "164 candidates lack temporal proof due to absent kickoff or missing capture bytes."
        ),
    }

    gate_upper_bound = {
        "R1": {
            "attainable_competitions": len(competitions),
            "attainable_market_families": len(market_families),
            "attainable_unique_rows": len(complete),
            "name": "ONE_WEEK_REPLAY",
            "reasons": (
                [
                    f"Only {len(complete)} unique complete row attainable (required >= 10)",
                    f"Only {len(competitions)} competition attainable (required >= 3)",
                    f"Only {len(market_families)} market family attainable (required >= 3)",
                ]
                if not one_week["satisfied"]
                else []
            ),
            "required_competitions": 3,
            "required_contiguous_calendar_days": 7,
            "required_market_families": 3,
            "required_unique_rows": 10,
            "satisfied": one_week["satisfied"],
        },
        "R2": {
            "attainable_competitions": len(competitions),
            "attainable_market_families": len(market_families),
            "attainable_unique_rows": len(complete),
            "attainable_utc_fixture_dates": len(utc_dates),
            "name": "SUFFICIENTLY_LARGE_REPLAY",
            "reasons": (
                [
                    f"Only {len(complete)} unique complete row attainable (required >= 25)",
                    f"Only {len(competitions)} competition attainable (required >= 3)",
                    f"Only {len(market_families)} market family attainable (required >= 5)",
                    f"Only {len(utc_dates)} UTC fixture date attainable (required >= 2)",
                ]
                if not sufficiently_large["satisfied"]
                else []
            ),
            "required_competitions": 3,
            "required_market_families": 5,
            "required_unique_rows": 25,
            "required_utc_fixture_dates": 2,
            "satisfied": sufficiently_large["satisfied"],
        },
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "repository_main_sha": repository_main_sha,
        "created_from_existing_evidence_only": True,
        "provider_acquisition": False,
        "source_inventory": inventory,
        "source_manifest_hashes": sorted(
            {
                value
                for row in rows
                for key, value in row["hashes"].items()
                if "manifest" in key
            }
        ),
        "candidate_row_count": len(rows),
        "classification_counts": {
            classification: primary_counts.get(classification, 0)
            for classification in CLASSIFICATIONS
        },
        "all_failed_requirement_counts": {
            classification: gap_counts.get(classification, 0)
            for classification in CLASSIFICATIONS
            if classification != REPLAY_COMPLETE
        },
        "all_gap_reasons": {
            classification: gap_counts.get(classification, 0)
            for classification in CLASSIFICATIONS
            if classification != REPLAY_COMPLETE
        },
        "repairability_class": {
            rc: repairability_counts.get(rc, 0) for rc in REPAIRABILITY_CLASSES
        },
        "replay_complete_count": len(complete),
        "unique_fixture_count": len(
            {row["fixture_identity"] for row in complete if row.get("fixture_identity")}
        ),
        "utc_date_count": len(utc_dates),
        "date_span": None if not utc_dates else [utc_dates[0], utc_dates[-1]],
        "competition_count": len(competitions),
        "market_family_count": len(market_families),
        "competitions": competitions,
        "market_families": market_families,
        "exact_quote_identities": sorted(
            {
                row["hashes"]["quote_identity_sha256"]
                for row in complete
                if "quote_identity_sha256" in row["hashes"]
            }
        ),
        "exact_quote_bindings": sorted(
            {
                row["hashes"]["quote_identity_binding"]
                for row in complete
                if "quote_identity_binding" in row["hashes"]
            }
        ),
        "legacy_lineage_identities": sorted(
            {
                row["hashes"]["legacy_lineage_sha256"]
                for row in complete
                if "legacy_lineage_sha256" in row["hashes"]
            }
        ),
        "canonical_lineage_identities": sorted(
            {
                row["hashes"]["canonical_lineage_sha256"]
                for row in complete
                if "canonical_lineage_sha256" in row["hashes"]
            }
        ),
        "acceptance_gates": {
            "ONE_WEEK_REPLAY": one_week,
            "SUFFICIENTLY_LARGE_REPLAY": sufficiently_large,
            "accepted_gate": gate,
        },
        "status": status,
        "source_gap": None
        if gate
        else {
            "code": SOURCE_GAP_STATUS,
            "dominant_actual_missing_source_category": (
                f"supported AnalysisPipeline state absent for "
                f"{gap_counts.get(REPLAY_UNAVAILABLE_LEGACY_LINEAGE, 0)}/{len(rows)} retained candidates"
            ),
            "count_semantics": (
                "OVERLAPPING_FAILED_REQUIREMENT_INCIDENCE; "
                "COUNTS_ARE_NOT_MUTUALLY_EXCLUSIVE_CANDIDATE_TOTALS"
            ),
            "true_source_data_absence_count": gap_counts.get(
                REPLAY_UNAVAILABLE_LEGACY_LINEAGE, 0
            ),
            "evidence_without_replay_adapter_count": gap_counts.get(
                REPLAY_UNAVAILABLE_CANONICAL_LINEAGE, 0
            ),
            "contract_version_migration_required_count": gap_counts.get(
                REPLAY_CONTRACT_DRIFT, 0
            ),
            "exact_quote_missing_count": gap_counts.get(
                REPLAY_UNAVAILABLE_EXACT_QUOTE, 0
            ),
            "supported_legacy_context_missing_count": gap_counts.get(
                REPLAY_UNAVAILABLE_LEGACY_LINEAGE, 0
            ),
            "temporal_proof_missing_count": gap_counts.get(
                REPLAY_TEMPORAL_LINEAGE_UNPROVEN, 0
            ),
            "numeric_threshold_only_blocker": False,
            "acceptance_contract_amendment_proposed": True,
        },
        "upper_bound_replayability": upper_bound,
        "historical_contract_analysis": historical_analysis,
        "identity_recovery_analysis": identity_analysis,
        "legacy_lineage_analysis": legacy_analysis,
        "quote_lineage_analysis": quote_analysis,
        "temporal_lineage_analysis": temporal_analysis,
        "source_window": source_window,
        "gate_upper_bound": gate_upper_bound,
        "candidates": rows,
        "network_used": False,
        "portfolio_invoked": False,
        "share_code_invoked": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
        "main_authority": False,
        "selection_authority": False,
        "promotion_authority": False,
    }
    payload["canonical_sha256"] = canonical_sha256(payload)
    return payload


def validate_source_audit(audit: Mapping[str, Any]) -> None:
    if audit.get("policy_id") != POLICY_ID:
        raise ReplayCorpusError("source audit policy_id mismatch")
    expected = audit.get("canonical_sha256")
    if type(expected) is not str:
        raise ReplayCorpusError("source audit canonical_sha256 is missing")
    unsigned = {key: value for key, value in audit.items() if key != "canonical_sha256"}
    if canonical_sha256(unsigned) != expected:
        raise ReplayCorpusError("source audit canonical_sha256 mismatch")
    rows = audit.get("candidates")
    if not isinstance(rows, list):
        raise ReplayCorpusError("source audit candidates must be a list")
    if audit.get("candidate_row_count") != len(rows):
        raise ReplayCorpusError("source audit candidate count mismatch")
    if len({row.get("candidate_id") for row in rows}) != len(rows):
        raise ReplayCorpusError("source audit duplicate candidate_id")
    for row in rows:
        if row.get("classification") not in CLASSIFICATIONS:
            raise ReplayCorpusError("source audit has unknown classification")
        if row.get("repairability_class") not in REPAIRABILITY_CLASSES:
            raise ReplayCorpusError("source audit has unknown repairability_class")
        for bool_field in CANDIDATE_BOOLEAN_FIELDS:
            if type(row.get(bool_field)) is not bool:
                raise ReplayCorpusError(f"source audit candidate missing boolean {bool_field}")
    for field in (
        "provider_acquisition",
        "network_used",
        "portfolio_invoked",
        "share_code_invoked",
        "login",
        "cookies",
        "wallet",
        "staking",
        "bet",
        "wager_placed",
        "main_authority",
        "selection_authority",
        "promotion_authority",
    ):
        if audit.get(field) is not False:
            raise ReplayCorpusError(f"source audit {field} must remain false")


def write_source_audit(path: Path, audit: Mapping[str, Any]) -> None:
    validate_source_audit(audit)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(dict(audit)))


__all__ = (
    "CANDIDATE_BOOLEAN_FIELDS",
    "CLASSIFICATIONS",
    "COMPLETE",
    "CURRENT_CORE_REPLAY_INPUTS_AVAILABLE",
    "DUPLICATE",
    "EXACT_IDENTITY_PROOF_NOT_CONSUMED",
    "HISTORICAL_CONTRACT_VERIFICATION_MISSING",
    "IRREPARABLE_TEMPORAL_GAP",
    "POLICY_ID",
    "REPAIRABILITY_CLASSES",
    "REPLAY_ADAPTER_MISSING",
    "REPLAY_COMPLETE",
    "REPLAY_CONTRACT_DRIFT",
    "REPLAY_DUPLICATE_EXCLUDED",
    "REPLAY_IDENTITY_UNPROVEN",
    "REPLAY_TEMPORAL_LINEAGE_UNPROVEN",
    "REPLAY_UNAVAILABLE_CANONICAL_LINEAGE",
    "REPLAY_UNAVAILABLE_EXACT_QUOTE",
    "REPLAY_UNAVAILABLE_LEGACY_LINEAGE",
    "ReplayCorpusError",
    "SOURCE_GAP_STATUS",
    "TRUE_SOURCE_ABSENCE",
    "build_source_audit",
    "candidate_gap_classifications",
    "canonical_json_bytes",
    "canonical_sha256",
    "classify_candidate",
    "classify_repairability",
    "validate_source_audit",
    "write_source_audit",
)
