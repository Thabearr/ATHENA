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
        "failed_requirements": list(failed),
        "failed_requirement_detail": _checked_text(
            candidate.get("failed_requirement_detail"),
            "failed_requirement_detail",
            optional=primary == REPLAY_COMPLETE,
        ),
        "offline_repairability": _checked_text(
            candidate.get("offline_repairability"), "offline_repairability"
        ),
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
        gap for row in rows for gap in row.get("failed_requirements", [])
    )
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
            "acceptance_contract_amendment_proposed": False,
        },
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
    "CLASSIFICATIONS",
    "POLICY_ID",
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
    "build_source_audit",
    "candidate_gap_classifications",
    "canonical_json_bytes",
    "canonical_sha256",
    "classify_candidate",
    "validate_source_audit",
    "write_source_audit",
)
