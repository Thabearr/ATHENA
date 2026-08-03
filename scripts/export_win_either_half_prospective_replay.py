"""CLI exporter for Stage 5B2 prospective Win Either Half pricing observation replay.

Generates transactional 7-file evidence bundle measuring bookmaker quote availability
at predeclared decision offsets before kickoff without computing odds/model EV/bets.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Mapping, Optional, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from domain.markets import MARKET_REGISTRY, MarketId, OutcomeId
from domain.model_status import MODEL_STATUS_REGISTRY
from domain.win_either_half_pricing_source_qualification import (
    canonical_market_registry_snapshot,
)
from domain.win_either_half_prospective_replay import (
    ATTEMPT_WINDOW_SECONDS,
    DEFAULT_PROTOCOL_PATH,
    EXPECTED_ATTEMPTS_PER_FIXTURE,
    FROZEN_CANDIDATE_OFFSETS_SECONDS,
    MAXIMUM_QUOTE_AGE_SECONDS,
    PERMITTED_MARKETS,
    SCHEMA_VERSION,
    AttemptParseResult,
    AttemptResult,
    AvailabilityReason,
    AvailabilityStatus,
    EvaluationRecord,
    ObservationAttempt,
    ProspectiveQuote,
    QuoteParseResult,
    ValidatedSnapshot,
    assert_no_forbidden_fields,
    build_expected_protocol_contract,
    evaluate_prospective_replay,
    load_fixtures_dataset,
    load_provider_mappings_dataset,
    load_source_qualification,
    parse_observation_attempts,
    parse_prospective_quotes,
    validate_protocol_contract,
)
from scripts.freeze_evidence_baseline import get_code_state

OUTPUT_FILENAMES = {
    "normalized_attempts": "normalized-attempts-table-v1.csv",
    "valid_quotes": "valid-quotes-table-v1.csv",
    "rejected_quotes": "rejected-quotes-table-v1.csv",
    "validated_snapshots": "validated-snapshots-table-v1.csv",
    "evaluations": "evaluations-table-v1.csv",
    "summary": "prospective-replay-summary-v1.json",
    "manifest": "prospective-replay-manifest-v1.json",
}


class ProspectiveReplayExportError(Exception):
    """Raised when evidence export fails validation or contract safety."""


@dataclass(frozen=True)
class EvidenceBundle:
    files: dict[str, bytes]
    manifest: dict[str, Any]
    row_counts: dict[str, int]


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return str(value)


def format_csv(
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(
        buffer,
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_csv_cell(value) for value in row])
    return buffer.getvalue().encode("utf-8")


def read_jsonl_records(raw_bytes: bytes) -> list[dict[str, Any]]:
    records = []
    for line_num, line in enumerate(raw_bytes.decode("utf-8").splitlines(), start=1):
        line_str = line.strip()
        if not line_str:
            continue
        try:
            parsed = json.loads(line_str)
        except Exception as err:
            raise ProspectiveReplayExportError(f"Line {line_num} is invalid JSON: {err}") from err
        if not isinstance(parsed, dict):
            raise ProspectiveReplayExportError(f"Line {line_num} must be a JSON object")
        records.append(parsed)
    return records


def assert_no_odds_in_json(obj: Any) -> None:
    """Recursively verify no odds value fields are present in JSON output."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            lower_k = str(k).lower()
            if lower_k in ("decimal_odds", "odds", "price", "odds_value", "odds_values"):
                raise ProspectiveReplayExportError(f"Prohibited odds key in JSON: {k}")
            assert_no_odds_in_json(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            assert_no_odds_in_json(item)


def build_outputs(
    *,
    source_qual_raw: bytes,
    source_qual_payload: Mapping[str, Any],
    fixtures_raw: bytes,
    fixtures_payload: Mapping[str, Any],
    provider_mappings_raw: bytes,
    provider_mappings_payload: Mapping[str, Any],
    attempts_raw: bytes,
    raw_attempts: Sequence[Mapping[str, Any]],
    quotes_raw: bytes,
    raw_quotes: Sequence[Mapping[str, Any]],
    protocol_raw: bytes,
    protocol_payload: Mapping[str, Any],
    source_qual_path: Path,
    fixtures_path: Path,
    mappings_path: Path,
    attempts_path: Path,
    quotes_path: Path,
    protocol_path: Path,
    code_state: Optional[Mapping[str, Any]] = None,
) -> EvidenceBundle:
    """Build all 7 deterministic Stage 5B2 evidence artifacts."""
    if code_state is None:
        try:
            code_state = get_code_state(REPOSITORY_ROOT)
        except Exception as err:
            raise ProspectiveReplayExportError(f"Git-state lookup failed: {err}") from err

    if not code_state.get("tracked_worktree_clean"):
        raise ProspectiveReplayExportError("Tracked worktree is dirty")

    git_sha = code_state.get("evidence_git_head_sha")
    if not isinstance(git_sha, str) or len(git_sha) != 40 or any(ch not in "0123456789abcdefABCDEF" for ch in git_sha):
        raise ProspectiveReplayExportError("Invalid evidence Git SHA from get_code_state")
    git_sha = git_sha.lower()

    # 1. Validate Protocol against immutable committed path
    try:
        validate_protocol_contract(protocol_payload, protocol_raw, committed_path=DEFAULT_PROTOCOL_PATH)
    except ValueError as err:
        raise ProspectiveReplayExportError(f"Protocol contract validation failed: {err}") from err

    # 2. Validate Source Qualification (Stage 5B1)
    try:
        expected_provider = load_source_qualification(source_qual_payload)
    except ValueError as err:
        raise ProspectiveReplayExportError(f"Stage 5B1 qualification validation failed: {err}") from err

    # 3. Load Fixtures
    try:
        fixtures = load_fixtures_dataset(fixtures_payload)
    except ValueError as err:
        raise ProspectiveReplayExportError(f"Fixtures dataset validation failed: {err}") from err

    # 4. Load Provider Mappings with exact fixture/market/outcome coverage
    try:
        mappings = load_provider_mappings_dataset(provider_mappings_payload, expected_provider, fixtures)
    except ValueError as err:
        raise ProspectiveReplayExportError(f"Provider mappings validation failed: {err}") from err

    # 5. Parse Observation Attempts
    attempt_parse_results, valid_attempts_by_id, valid_attempts_by_key, invalid_attempts_by_key = parse_observation_attempts(
        raw_records=raw_attempts,
        fixtures=fixtures,
        mappings=mappings,
        expected_provider=expected_provider,
    )

    # 6. Parse Prospective Quotes
    quote_parse_results = parse_prospective_quotes(
        raw_records=raw_quotes,
        fixtures=fixtures,
        mappings=mappings,
        valid_attempts_by_id=valid_attempts_by_id,
        expected_provider=expected_provider,
    )

    quote_results_by_attempt_id: dict[str, list[QuoteParseResult]] = {}
    for result in quote_parse_results:
        aid = result.raw_record.get("attempt_id")
        if isinstance(aid, str) and aid.strip():
            quote_results_by_attempt_id.setdefault(aid.strip(), []).append(result)

    valid_quotes = [r.quote for r in quote_parse_results if r.is_valid and r.quote is not None]

    # 7. Evaluate Replay with raw quote results by attempt_id
    snapshots, evaluations = evaluate_prospective_replay(
        fixtures=fixtures,
        valid_attempts_by_key=valid_attempts_by_key,
        invalid_attempts_by_key=invalid_attempts_by_key,
        quote_results_by_attempt_id=quote_results_by_attempt_id,
    )

    expected_evaluation_count = len(fixtures) * EXPECTED_ATTEMPTS_PER_FIXTURE
    if len(evaluations) != expected_evaluation_count:
        raise ProspectiveReplayExportError(
            "Evaluation denominator mismatch: "
            f"expected={expected_evaluation_count}, actual={len(evaluations)}"
        )

    # Build CSV tables deterministically
    generated_files: dict[str, bytes] = {}
    row_counts: dict[str, int] = {}

    # Table 1: normalized_attempts
    att_cols = [
        "input_record_sha256",
        "attempt_id",
        "fixture_identifier",
        "market_id",
        "line",
        "provider_identifier",
        "source",
        "bookmaker_identifier",
        "provider_event_identifier",
        "provider_market_identifier",
        "offset_seconds_before_kickoff",
        "scheduled_at",
        "attempted_at",
        "result",
        "capture_method",
        "quote_snapshot_id",
        "is_valid",
        "rejection_reasons",
    ]
    sorted_attempt_results = sorted(
        attempt_parse_results,
        key=lambda r: (
            str(r.raw_record.get("fixture_identifier", "")),
            str(r.raw_record.get("market_id", "")),
            int(r.raw_record.get("offset_seconds_before_kickoff", 0))
            if type(r.raw_record.get("offset_seconds_before_kickoff")) is int
            else 0,
            str(r.raw_record.get("attempt_id", "")),
            r.input_record_sha256,
        ),
    )
    att_rows = []
    for r in sorted_attempt_results:
        rec = r.raw_record
        att_rows.append([
            r.input_record_sha256,
            rec.get("attempt_id"),
            rec.get("fixture_identifier"),
            rec.get("market_id"),
            rec.get("line"),
            rec.get("provider_identifier"),
            rec.get("source"),
            rec.get("bookmaker_identifier"),
            rec.get("provider_event_identifier"),
            rec.get("provider_market_identifier"),
            rec.get("offset_seconds_before_kickoff"),
            rec.get("scheduled_at"),
            rec.get("attempted_at"),
            rec.get("result"),
            rec.get("capture_method"),
            rec.get("quote_snapshot_id"),
            r.is_valid,
            list(r.rejection_reasons),
        ])
    generated_files["normalized_attempts"] = format_csv(att_cols, att_rows)
    row_counts["normalized_attempts"] = len(att_rows)

    # Table 2: valid_quotes (NO decimal_odds emitted)
    vq_cols = [
        "input_record_sha256",
        "attempt_id",
        "provider_identifier",
        "source",
        "bookmaker_identifier",
        "fixture_identifier",
        "market_id",
        "outcome_id",
        "quote_snapshot_id",
        "observed_at",
        "fixture_kickoff",
        "provider_event_identifier",
        "provider_market_identifier",
        "provider_selection_identifier",
    ]
    sorted_valid_quotes = sorted(
        valid_quotes,
        key=lambda q: (
            q.fixture_identifier,
            q.market_id.value,
            q.outcome_id.value,
            q.attempt_id,
            q.input_record_sha256,
        ),
    )
    vq_rows = [
        [
            q.input_record_sha256,
            q.attempt_id,
            q.provider_identifier,
            q.source,
            q.bookmaker_identifier,
            q.fixture_identifier,
            q.market_id.value,
            q.outcome_id.value,
            q.quote_snapshot_id,
            q.observed_at,
            q.fixture_kickoff,
            q.provider_event_identifier,
            q.provider_market_identifier,
            q.provider_selection_identifier,
        ]
        for q in sorted_valid_quotes
    ]
    generated_files["valid_quotes"] = format_csv(vq_cols, vq_rows)
    row_counts["valid_quotes"] = len(vq_rows)

    # Table 3: rejected_quotes
    rq_cols = [
        "input_record_sha256",
        "attempt_id",
        "fixture_identifier",
        "market_id",
        "outcome_id",
        "provider_identifier",
        "rejection_reasons",
    ]
    rejected_quote_results = [r for r in quote_parse_results if not r.is_valid]
    sorted_rejected_quotes = sorted(
        rejected_quote_results,
        key=lambda r: (
            str(r.raw_record.get("fixture_identifier", "")),
            str(r.raw_record.get("market_id", "")),
            str(r.raw_record.get("outcome_id", "")),
            str(r.raw_record.get("attempt_id", "")),
            r.input_record_sha256,
        ),
    )
    rq_rows = [
        [
            r.input_record_sha256,
            r.raw_record.get("attempt_id"),
            r.raw_record.get("fixture_identifier"),
            r.raw_record.get("market_id"),
            r.raw_record.get("outcome_id"),
            r.raw_record.get("provider_identifier"),
            list(r.rejection_reasons),
        ]
        for r in sorted_rejected_quotes
    ]
    generated_files["rejected_quotes"] = format_csv(rq_cols, rq_rows)
    row_counts["rejected_quotes"] = len(rq_rows)

    # Table 4: validated_snapshots
    snap_cols = [
        "snapshot_sha256",
        "attempt_id",
        "fixture_identifier",
        "market_id",
        "source",
        "provider_identifier",
        "bookmaker_identifier",
        "offset_seconds_before_kickoff",
        "scheduled_at",
        "attempted_at",
        "quote_snapshot_id",
        "observed_at",
        "yes_quote_record_sha256",
        "no_quote_record_sha256",
        "quote_age_seconds_at_attempt",
    ]
    sorted_snapshots = sorted(
        snapshots,
        key=lambda s: (
            s.fixture_identifier,
            s.market_id.value,
            s.offset_seconds_before_kickoff,
            s.attempt_id,
        ),
    )
    snap_rows = [
        [
            s.snapshot_sha256,
            s.attempt_id,
            s.fixture_identifier,
            s.market_id.value,
            s.source,
            s.provider_identifier,
            s.bookmaker_identifier,
            s.offset_seconds_before_kickoff,
            s.scheduled_at,
            s.attempted_at,
            s.quote_snapshot_id,
            s.observed_at,
            s.yes_quote_record_sha256,
            s.no_quote_record_sha256,
            s.quote_age_seconds_at_attempt,
        ]
        for s in sorted_snapshots
    ]
    generated_files["validated_snapshots"] = format_csv(snap_cols, snap_rows)
    row_counts["validated_snapshots"] = len(snap_rows)

    # Table 5: evaluations
    eval_cols = [
        "evaluation_record_sha256",
        "fixture_identifier",
        "market_id",
        "offset_seconds_before_kickoff",
        "scheduled_at",
        "availability_status",
        "availability_reason",
        "attempt_id",
        "attempt_result",
        "attempted_at",
        "attempt_window_seconds_used",
        "quote_snapshot_id",
        "observed_at",
        "quote_age_seconds_at_attempt",
        "has_valid_snapshot",
    ]
    sorted_evaluations = sorted(
        evaluations,
        key=lambda e: (
            e.scheduled_at,
            e.fixture_identifier,
            e.market_id.value,
            e.offset_seconds_before_kickoff,
        ),
    )
    eval_rows = [
        [
            e.evaluation_record_sha256,
            e.fixture_identifier,
            e.market_id.value,
            e.offset_seconds_before_kickoff,
            e.scheduled_at,
            e.availability_status.value,
            e.availability_reason,
            e.attempt_id,
            e.attempt_result,
            e.attempted_at,
            e.attempt_window_seconds_used,
            e.quote_snapshot_id,
            e.observed_at,
            e.quote_age_seconds_at_attempt,
            e.has_valid_snapshot,
        ]
        for e in sorted_evaluations
    ]
    generated_files["evaluations"] = format_csv(eval_cols, eval_rows)
    row_counts["evaluations"] = len(eval_rows)

    # Rejection reason counts
    quote_rejection_counts: dict[str, int] = {}
    for r in quote_parse_results:
        for reason in r.rejection_reasons:
            quote_rejection_counts[reason] = quote_rejection_counts.get(reason, 0) + 1

    attempt_rejection_counts: dict[str, int] = {}
    for r in attempt_parse_results:
        for reason in r.rejection_reasons:
            attempt_rejection_counts[reason] = attempt_rejection_counts.get(reason, 0) + 1

    # Table 6: summary JSON
    total_evals = len(evaluations)
    avail_count = sum(1 for e in evaluations if e.availability_status == AvailabilityStatus.AVAILABLE)
    unavail_count = sum(1 for e in evaluations if e.availability_status == AvailabilityStatus.UNAVAILABLE)
    unknown_count = sum(1 for e in evaluations if e.availability_status == AvailabilityStatus.UNKNOWN)
    invalid_count = sum(1 for e in evaluations if e.availability_status == AvailabilityStatus.INVALID)

    by_offset: dict[str, Any] = {}
    for offset in sorted(FROZEN_CANDIDATE_OFFSETS_SECONDS, reverse=True):
        offset_evals = [e for e in evaluations if e.offset_seconds_before_kickoff == offset]
        off_total = len(offset_evals)
        off_avail = sum(1 for e in offset_evals if e.availability_status == AvailabilityStatus.AVAILABLE)
        by_offset[str(offset)] = {
            "total_evaluations": off_total,
            "available_count": off_avail,
            "unavailable_count": sum(1 for e in offset_evals if e.availability_status == AvailabilityStatus.UNAVAILABLE),
            "unknown_count": sum(1 for e in offset_evals if e.availability_status == AvailabilityStatus.UNKNOWN),
            "invalid_count": sum(1 for e in offset_evals if e.availability_status == AvailabilityStatus.INVALID),
            "available_rate": round(off_avail / off_total, 6) if off_total > 0 else 0.0,
        }

    by_market: dict[str, Any] = {}
    for market in sorted(PERMITTED_MARKETS, key=lambda m: m.value):
        mkt_evals = [e for e in evaluations if e.market_id == market]
        mkt_total = len(mkt_evals)
        mkt_avail = sum(1 for e in mkt_evals if e.availability_status == AvailabilityStatus.AVAILABLE)
        by_market[market.value] = {
            "total_evaluations": mkt_total,
            "available_count": mkt_avail,
            "unavailable_count": sum(1 for e in mkt_evals if e.availability_status == AvailabilityStatus.UNAVAILABLE),
            "unknown_count": sum(1 for e in mkt_evals if e.availability_status == AvailabilityStatus.UNKNOWN),
            "invalid_count": sum(1 for e in mkt_evals if e.availability_status == AvailabilityStatus.INVALID),
            "available_rate": round(mkt_avail / mkt_total, 6) if mkt_total > 0 else 0.0,
        }

    availability_reason_counts = dict(sorted(Counter(
        evaluation.availability_reason for evaluation in evaluations
    ).items()))

    summary_dict: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": "win-either-half-prospective-replay-summary-v1",
        "provider_identifier": expected_provider,
        "fixture_count": len(fixtures),
        "expected_evaluations_total": len(fixtures) * EXPECTED_ATTEMPTS_PER_FIXTURE,
        "supplied_attempt_count": len(attempt_parse_results),
        "valid_attempt_count": len(valid_attempts_by_id),
        "invalid_attempt_count": sum(1 for r in attempt_parse_results if not r.is_valid),
        "supplied_quote_count": len(quote_parse_results),
        "valid_quote_count": len(valid_quotes),
        "invalid_quote_count": len(rejected_quote_results),
        "complete_snapshot_count": len(snapshots),
        "availability_reason_counts": availability_reason_counts,
        "selected_offset_seconds": None,
        "selection_authorized": False,
        "production_approval_authorized": False,
        "missing_expected_attempt_count": sum(
            1 for e in evaluations if e.availability_reason == AvailabilityReason.NO_ATTEMPT_RECORD.value
        ),
        "duplicate_expected_key_count": sum(
            1 for r in attempt_parse_results if "DUPLICATE_EXPECTED_KEY" in r.rejection_reasons
        ),
        "duplicate_attempt_id_count": sum(
            1 for r in attempt_parse_results if "DUPLICATE_ATTEMPT_ID" in r.rejection_reasons
        ),
        "unassociated_invalid_attempt_count": sum(
            1
            for r in attempt_parse_results
            if not r.is_valid
            and (
                "UNKNOWN_FIXTURE" in r.rejection_reasons
                or "UNKNOWN_MARKET" in r.rejection_reasons
                or "INVALID_OFFSET_SECONDS" in r.rejection_reasons
            )
        ),
        "orphan_quote_count": sum(
            1 for r in quote_parse_results if "UNKNOWN_ATTEMPT_ID" in r.rejection_reasons
        ),
        "quote_rejection_reason_counts": quote_rejection_counts,
        "attempt_rejection_reason_counts": attempt_rejection_counts,
        "evaluations_summary": {
            "total_evaluations": total_evals,
            "available_count": avail_count,
            "unavailable_count": unavail_count,
            "unknown_count": unknown_count,
            "invalid_count": invalid_count,
            "available_rate": round(avail_count / total_evals, 6) if total_evals > 0 else 0.0,
        },
        "by_offset": by_offset,
        "by_market": by_market,
        "governance": {
            "selected_offset_seconds": None,
            "selection_authorized": False,
            "production_approval_authorized": False,
            "HOME_WIN_EITHER_HALF": "DISABLED",
            "AWAY_WIN_EITHER_HALF": "DISABLED",
        },
        "no_production_approval": "Stage 5B2 prospective replay is observation evidence only.",
    }

    assert_no_odds_in_json(summary_dict)

    summary_bytes = (
        json.dumps(
            summary_dict,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    generated_files["summary"] = summary_bytes
    row_counts["summary"] = 1

    # Registries
    market_reg_snapshot = canonical_market_registry_snapshot()
    model_status_dict = {
        market.value: MODEL_STATUS_REGISTRY[market].status.value
        for market in sorted(MarketId, key=lambda item: item.value)
    }

    # Assert 15 canonical markets and Win Either Half disabled
    if len(market_reg_snapshot) != 15:
        raise ProspectiveReplayExportError(
            f"Expected 15 canonical markets, found {len(market_reg_snapshot)}"
        )
    if model_status_dict.get("HOME_WIN_EITHER_HALF") != "DISABLED":
        raise ProspectiveReplayExportError("HOME_WIN_EITHER_HALF must be DISABLED")
    if model_status_dict.get("AWAY_WIN_EITHER_HALF") != "DISABLED":
        raise ProspectiveReplayExportError("AWAY_WIN_EITHER_HALF must be DISABLED")

    # Table 7: manifest JSON
    manifest_outputs: dict[str, Any] = {}
    for name, content in generated_files.items():
        manifest_outputs[name] = {
            "relative_name": OUTPUT_FILENAMES[name],
            "byte_size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "rows": row_counts[name],
        }

    manifest_inputs: dict[str, Any] = {
        "source_qualification": {
            "relative_name": source_qual_path.name,
            "byte_size": len(source_qual_raw),
            "sha256": hashlib.sha256(source_qual_raw).hexdigest(),
        },
        "fixtures": {
            "relative_name": fixtures_path.name,
            "byte_size": len(fixtures_raw),
            "sha256": hashlib.sha256(fixtures_raw).hexdigest(),
            "rows": len(fixtures),
        },
        "provider_mappings": {
            "relative_name": mappings_path.name,
            "byte_size": len(provider_mappings_raw),
            "sha256": hashlib.sha256(provider_mappings_raw).hexdigest(),
            "rows": len(mappings),
        },
        "attempts": {
            "relative_name": attempts_path.name,
            "byte_size": len(attempts_raw),
            "sha256": hashlib.sha256(attempts_raw).hexdigest(),
            "rows": len(raw_attempts),
        },
        "quotes": {
            "relative_name": quotes_path.name,
            "byte_size": len(quotes_raw),
            "sha256": hashlib.sha256(quotes_raw).hexdigest(),
            "rows": len(raw_quotes),
        },
        "protocol": {
            "relative_name": protocol_path.name,
            "byte_size": len(protocol_raw),
            "sha256": hashlib.sha256(protocol_raw).hexdigest(),
        },
    }

    manifest_dict: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": "win-either-half-prospective-replay-manifest-v1",
        "generator": "scripts/export_win_either_half_prospective_replay.py",
        "generator_commit": git_sha,
        "tracked_worktree_clean": True,
        "candidate_offsets_seconds": list(FROZEN_CANDIDATE_OFFSETS_SECONDS),
        "attempt_window_seconds": ATTEMPT_WINDOW_SECONDS,
        "maximum_quote_age_seconds": MAXIMUM_QUOTE_AGE_SECONDS,
        "expected_attempts_per_fixture": EXPECTED_ATTEMPTS_PER_FIXTURE,
        "permitted_markets": [m.value for m in PERMITTED_MARKETS],
        "market_registry": market_reg_snapshot,
        "model_status_registry": model_status_dict,
        "snapshot_contract": {
            "attempt_id_required": True,
            "quotes_must_link_to_exact_attempt": True,
            "requires_yes_and_no": True,
            "same_source": True,
            "same_provider": True,
            "same_bookmaker": True,
            "same_provider_event": True,
            "same_provider_market": True,
            "same_snapshot": True,
            "same_observed_at": True,
            "maximum_quote_age_seconds": MAXIMUM_QUOTE_AGE_SECONDS,
            "freshness_reference": "ATTEMPTED_AT",
            "odds_values_emitted": False,
        },
        "prohibited_calculations": [
            "MODEL_PROBABILITY",
            "FAIR_ODDS",
            "EDGE",
            "EXPECTED_VALUE",
            "KELLY",
            "STAKE",
            "ACCA_SELECTION",
            "BETSLIP",
            "BOOKING_CODE",
            "BET_DECISION",
        ],
        "holdout_governance": {
            "final_test_season": "2025-26",
            "final_test_status": "ALREADY_CONSUMED_AUDIT_HOLDOUT",
            "match_outcomes_forbidden_from_offset_evaluation": True,
            "model_performance_forbidden_from_offset_evaluation": True,
            "pricing_profitability_forbidden_from_offset_evaluation": True,
            "prospective_validation_required": True,
            "production_approval_authorized": False,
        },
        "summary_accounting": {
            "fixture_count": summary_dict["fixture_count"],
            "expected_evaluations_total": summary_dict["expected_evaluations_total"],
            "supplied_attempt_count": summary_dict["supplied_attempt_count"],
            "valid_attempt_count": summary_dict["valid_attempt_count"],
            "invalid_attempt_count": summary_dict["invalid_attempt_count"],
            "supplied_quote_count": summary_dict["supplied_quote_count"],
            "valid_quote_count": summary_dict["valid_quote_count"],
            "invalid_quote_count": summary_dict["invalid_quote_count"],
            "complete_snapshot_count": summary_dict["complete_snapshot_count"],
            "availability_reason_counts": summary_dict["availability_reason_counts"],
        },
        "deterministic_ordering": {
            "attempts": [
                "fixture_identifier",
                "market_id",
                "offset_seconds_before_kickoff",
                "attempt_id",
                "input_record_sha256",
            ],
            "quotes": [
                "fixture_identifier",
                "market_id",
                "outcome_id",
                "attempt_id",
                "input_record_sha256",
            ],
            "evaluations": [
                "scheduled_at",
                "fixture_identifier",
                "market_id",
                "offset_seconds_before_kickoff",
            ],
        },
        "selected_offset_seconds": None,
        "selection_authorized": False,
        "production_approval_authorized": False,
        "inputs": manifest_inputs,
        "outputs": manifest_outputs,
        "no_production_approval": "Stage 5B2 is observation evidence only.",
    }

    assert_no_odds_in_json(manifest_dict)

    # Compute logical manifest hash before adding logical_manifest_sha256
    manifest_pre_bytes = json.dumps(
        manifest_dict,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8")
    manifest_dict["logical_manifest_sha256"] = hashlib.sha256(manifest_pre_bytes).hexdigest()

    manifest_bytes = (
        json.dumps(
            manifest_dict,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")

    generated_files["manifest"] = manifest_bytes
    row_counts["manifest"] = 1

    return EvidenceBundle(
        files=generated_files,
        manifest=manifest_dict,
        row_counts=row_counts,
    )


def commit_evidence_bundle(
    *,
    output_paths: Mapping[str, Path],
    contents: Mapping[str, bytes],
    force: bool = False,
) -> None:
    """Atomic multi-file write with fsync, rollback on error, and overwrite protection."""
    if set(output_paths) != set(contents):
        raise ProspectiveReplayExportError("Output paths and content keys differ")

    resolved_parents = {path.parent.resolve() for path in output_paths.values()}
    if len(resolved_parents) != 1:
        raise ProspectiveReplayExportError("All evidence outputs must share one directory")

    output_dir = next(iter(resolved_parents))
    output_dir.mkdir(parents=True, exist_ok=True)

    if not force and any(path.exists() for path in output_paths.values()):
        raise ProspectiveReplayExportError("Evidence output already exists; use --force")

    stage_dir = Path(tempfile.mkdtemp(prefix=".stage5b2-stage-", dir=output_dir))
    rollback_dir = Path(tempfile.mkdtemp(prefix=".stage5b2-rollback-", dir=output_dir))
    backups: list[tuple[Path, Path]] = []
    installed: list[Path] = []

    try:
        for name in sorted(output_paths):
            destination = output_paths[name]
            staged = stage_dir / destination.name
            with staged.open("wb") as handle:
                handle.write(contents[name])
                handle.flush()
                os.fsync(handle.fileno())

        for name in sorted(output_paths):
            destination = output_paths[name]
            if destination.exists():
                backup = rollback_dir / destination.name
                os.replace(destination, backup)
                backups.append((backup, destination))

        for name in sorted(output_paths):
            destination = output_paths[name]
            staged = stage_dir / destination.name
            os.replace(staged, destination)
            installed.append(destination)

        try:
            directory_fd = os.open(str(output_dir), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            pass

    except Exception as error:
        for destination in reversed(installed):
            if destination.exists():
                destination.unlink()
        for backup, destination in reversed(backups):
            if backup.exists():
                os.replace(backup, destination)
        raise ProspectiveReplayExportError(f"Atomic evidence commit failed: {error}") from error
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
        shutil.rmtree(rollback_dir, ignore_errors=True)



def check_manifest(
    *,
    manifest_path: Path,
    bundle: EvidenceBundle,
) -> None:
    """Verify stored manifest and all sibling evidence outputs against regenerated bundle."""
    if not manifest_path.is_file():
        raise ProspectiveReplayExportError(f"Manifest not found: {manifest_path}")

    stored_manifest_bytes = manifest_path.read_bytes()
    if stored_manifest_bytes != bundle.files["manifest"]:
        raise ProspectiveReplayExportError("Stored manifest bytes differ")

    try:
        stored_manifest = json.loads(stored_manifest_bytes.decode("utf-8"))
    except Exception as err:
        raise ProspectiveReplayExportError(f"Stored manifest is invalid JSON: {err}") from err

    # Verify manifest safety fields
    if stored_manifest.get("schema_version") != SCHEMA_VERSION:
        raise ProspectiveReplayExportError("Stored manifest schema_version mismatch")
    if stored_manifest.get("selected_offset_seconds") is not None:
        raise ProspectiveReplayExportError("Stored manifest selected_offset_seconds must be null")
    if stored_manifest.get("selection_authorized") is not False:
        raise ProspectiveReplayExportError("Stored manifest selection_authorized must be false")
    if stored_manifest.get("production_approval_authorized") is not False:
        raise ProspectiveReplayExportError("Stored manifest production_approval_authorized must be false")

    output_dir = manifest_path.parent
    for name, expected_filename in OUTPUT_FILENAMES.items():
        sibling_path = output_dir / expected_filename
        if not sibling_path.is_file():
            raise ProspectiveReplayExportError(f"Stored sibling output missing: {sibling_path}")
        stored_bytes = sibling_path.read_bytes()
        expected_bytes = bundle.files[name]

        if stored_bytes != expected_bytes:
            raise ProspectiveReplayExportError(
                f"Stored file {sibling_path.name} does not match expected bytes"
            )

        if name != "manifest":
            stored_sha = hashlib.sha256(stored_bytes).hexdigest()
            manifest_meta = stored_manifest.get("outputs", {}).get(name, {})
            if manifest_meta.get("sha256") != stored_sha:
                raise ProspectiveReplayExportError(
                    f"Manifest sha256 mismatch for {name}: {manifest_meta.get('sha256')} != {stored_sha}"
                )
            if manifest_meta.get("byte_size") != len(stored_bytes):
                raise ProspectiveReplayExportError(
                    f"Manifest byte_size mismatch for {name}: {manifest_meta.get('byte_size')} != {len(stored_bytes)}"
                )
            if manifest_meta.get("rows") != bundle.row_counts[name]:
                raise ProspectiveReplayExportError(
                    f"Manifest rows mismatch for {name}: {manifest_meta.get('rows')} != {bundle.row_counts[name]}"
                )


def build_parser() -> argparse.ArgumentParser:
    """Build command-line parser."""
    parser = argparse.ArgumentParser(
        description="Measure provider-qualified prospective Win Either Half quote availability at predeclared decision offsets."
    )
    parser.add_argument("--source-qualification", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--provider-mappings", type=Path, required=True)
    parser.add_argument("--attempts", type=Path, required=True)
    parser.add_argument("--quotes", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest-output", type=Path)
    mode.add_argument("--check", type=Path)

    parser.add_argument("--force", action="store_true")
    return parser


def run(args: Sequence[str]) -> int:
    """Execute exporter CLI."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    try:
        # Read input files
        if not parsed.source_qualification.is_file():
            raise ProspectiveReplayExportError(f"Source qualification file not found: {parsed.source_qualification}")
        source_qual_raw = parsed.source_qualification.read_bytes()
        try:
            source_qual = json.loads(source_qual_raw.decode("utf-8"))
        except Exception as err:
            raise ProspectiveReplayExportError(f"Source qualification JSON invalid: {err}") from err

        if not parsed.fixtures.is_file():
            raise ProspectiveReplayExportError(f"Fixtures file not found: {parsed.fixtures}")
        fixtures_raw = parsed.fixtures.read_bytes()
        try:
            fixtures = json.loads(fixtures_raw.decode("utf-8"))
        except Exception as err:
            raise ProspectiveReplayExportError(f"Fixtures JSON invalid: {err}") from err

        if not parsed.provider_mappings.is_file():
            raise ProspectiveReplayExportError(f"Provider mappings file not found: {parsed.provider_mappings}")
        mappings_raw = parsed.provider_mappings.read_bytes()
        try:
            mappings = json.loads(mappings_raw.decode("utf-8"))
        except Exception as err:
            raise ProspectiveReplayExportError(f"Provider mappings JSON invalid: {err}") from err

        if not parsed.attempts.is_file():
            raise ProspectiveReplayExportError(f"Attempts file not found: {parsed.attempts}")
        attempts_raw = parsed.attempts.read_bytes()
        raw_attempts = read_jsonl_records(attempts_raw)

        if not parsed.quotes.is_file():
            raise ProspectiveReplayExportError(f"Quotes file not found: {parsed.quotes}")
        quotes_raw = parsed.quotes.read_bytes()
        raw_quotes = read_jsonl_records(quotes_raw)

        if not parsed.protocol.is_file():
            raise ProspectiveReplayExportError(f"Protocol file not found: {parsed.protocol}")
        protocol_raw = parsed.protocol.read_bytes()
        try:
            protocol = json.loads(protocol_raw.decode("utf-8"))
        except Exception as err:
            raise ProspectiveReplayExportError(f"Protocol JSON invalid: {err}") from err

        code_state = get_code_state(REPOSITORY_ROOT)
        if not code_state.get("tracked_worktree_clean"):
            raise ProspectiveReplayExportError("Tracked worktree is dirty")

        bundle = build_outputs(
            source_qual_raw=source_qual_raw,
            source_qual_payload=source_qual,
            fixtures_raw=fixtures_raw,
            fixtures_payload=fixtures,
            provider_mappings_raw=mappings_raw,
            provider_mappings_payload=mappings,
            attempts_raw=attempts_raw,
            raw_attempts=raw_attempts,
            quotes_raw=quotes_raw,
            raw_quotes=raw_quotes,
            protocol_raw=protocol_raw,
            protocol_payload=protocol,
            source_qual_path=parsed.source_qualification,
            fixtures_path=parsed.fixtures,
            mappings_path=parsed.provider_mappings,
            attempts_path=parsed.attempts,
            quotes_path=parsed.quotes,
            protocol_path=parsed.protocol,
            code_state=code_state,
        )

        if parsed.manifest_output is not None:
            manifest_path: Path = parsed.manifest_output
            if manifest_path.name != OUTPUT_FILENAMES["manifest"]:
                raise ProspectiveReplayExportError(
                    f"--manifest-output filename must be '{OUTPUT_FILENAMES['manifest']}', got '{manifest_path.name}'"
                )
            output_dir = manifest_path.parent
            output_paths = {
                name: output_dir / filename
                for name, filename in OUTPUT_FILENAMES.items()
            }
            commit_evidence_bundle(
                output_paths=output_paths,
                contents=bundle.files,
                force=parsed.force,
            )
            print(f"Generated 7 evidence files in {output_dir}")
            return 0

        elif parsed.check is not None:
            check_manifest(
                manifest_path=parsed.check,
                bundle=bundle,
            )
            print("Stage 5B2 prospective replay verified")
            return 0

        return 0
    except Exception as err:
        sys.stderr.write(f"Error: {err}\n")
        return 1


def main() -> None:
    """Entry point."""
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
