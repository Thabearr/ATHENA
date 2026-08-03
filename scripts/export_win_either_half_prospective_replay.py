"""Exporter CLI for Stage 5B2 Win Either Half prospective pricing observation replay.

Generates and verifies deterministic evidence files measuring prospective quote
availability at predeclared decision offsets before kickoff.

Usage:
  python -m scripts.export_win_either_half_prospective_replay \\
    --source-qualification path/to/source-qualification.json \\
    --fixtures path/to/prospective-fixtures.json \\
    --provider-mappings path/to/provider-mappings.json \\
    --attempts path/to/attempts.jsonl \\
    --quotes path/to/quotes.jsonl \\
    --manifest-output .cache/athena-research/win-either-half/prospective-replay-manifest-v1.json

Verification:
  python -m scripts.export_win_either_half_prospective_replay \\
    --source-qualification path/to/source-qualification.json \\
    --fixtures path/to/prospective-fixtures.json \\
    --provider-mappings path/to/provider-mappings.json \\
    --attempts path/to/attempts.jsonl \\
    --quotes path/to/quotes.jsonl \\
    --check .cache/athena-research/win-either-half/prospective-replay-manifest-v1.json
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Optional, Sequence

from domain.markets import MarketId, OutcomeId
from domain.win_either_half_prospective_replay import (
    SCHEMA_VERSION,
    PERMITTED_MARKETS,
    FROZEN_CANDIDATE_OFFSETS_SECONDS,
    ATTEMPT_WINDOW_SECONDS,
    MAXIMUM_QUOTE_AGE_SECONDS,
    EXPECTED_ATTEMPTS_PER_FIXTURE,
    AttemptResult,
    AvailabilityStatus,
    AvailabilityReason,
    ProspectiveFixture,
    ProviderSelectionMapping,
    ObservationAttempt,
    AttemptParseResult,
    ProspectiveQuote,
    QuoteParseResult,
    ValidatedSnapshot,
    ProspectiveReplayRow,
    AttemptIndex,
    canonical_record_bytes,
    canonical_record_sha256,
    assert_no_forbidden_fields,
    load_source_qualification,
    load_prospective_fixtures,
    load_provider_mappings,
    market_mapping_identity,
    expected_attempt_keys,
    parse_attempt,
    index_attempt_results,
    parse_quote,
    evaluate_expected_key,
    aggregate_replay,
)


DEFAULT_PROTOCOL_PATH = (
    Path(__file__).resolve().parent.parent
    / "artifacts"
    / "research-protocols"
    / "win-either-half-prospective-replay-v1.json"
)

OUTPUT_FILENAMES = {
    "normalized_attempts": "prospective-replay-normalized-attempts-v1.csv",
    "valid_quotes": "prospective-replay-valid-quotes-v1.csv",
    "rejected_quotes": "prospective-replay-rejected-quotes-v1.csv",
    "validated_snapshots": "prospective-replay-validated-snapshots-v1.csv",
    "evaluations": "prospective-replay-evaluations-v1.csv",
    "summary": "prospective-replay-summary-v1.json",
    "manifest": "prospective-replay-manifest-v1.json",
}

NORMALIZED_ATTEMPT_COLUMNS = (
    "input_record_sha256",
    "occurrence_index",
    "validation_status",
    "rejection_reasons_json",
    "attempt_id",
    "fixture_identifier",
    "market_id",
    "source",
    "provider_identifier",
    "bookmaker_identifier",
    "provider_event_identifier",
    "provider_market_identifier",
    "offset_seconds_before_kickoff",
    "scheduled_at",
    "attempted_at",
    "result",
    "capture_method",
    "quote_snapshot_id",
)

VALID_QUOTE_COLUMNS = (
    "input_record_sha256",
    "occurrence_index",
    "fixture_identifier",
    "market_id",
    "outcome_id",
    "source",
    "provider_identifier",
    "bookmaker_identifier",
    "provider_event_identifier",
    "provider_market_identifier",
    "provider_selection_identifier",
    "quote_snapshot_id",
    "observed_at",
    "fixture_kickoff",
    "odds_validated",
)

REJECTED_QUOTE_COLUMNS = (
    "input_record_sha256",
    "occurrence_index",
    "fixture_identifier",
    "market_id",
    "outcome_id",
    "source",
    "provider_identifier",
    "bookmaker_identifier",
    "quote_snapshot_id",
    "observed_at",
    "fixture_kickoff",
    "rejection_reasons_json",
)

VALIDATED_SNAPSHOT_COLUMNS = (
    "fixture_identifier",
    "market_id",
    "offset_seconds_before_kickoff",
    "source",
    "provider_identifier",
    "bookmaker_identifier",
    "provider_event_identifier",
    "provider_market_identifier",
    "quote_snapshot_id",
    "observed_at",
    "quote_age_seconds",
    "yes_quote_record_sha256",
    "no_quote_record_sha256",
)

EVALUATION_COLUMNS = (
    "fixture_identifier",
    "market_id",
    "offset_seconds_before_kickoff",
    "scheduled_at",
    "attempt_status",
    "attempt_result",
    "raw_quote_row_count",
    "accepted_quote_row_count",
    "rejected_quote_row_count",
    "validated_snapshot_count",
    "availability_status",
    "availability_reason",
    "validated_snapshot_id",
    "validated_observed_at",
    "validated_quote_age_seconds",
)


class ProspectiveReplayExportError(Exception):
    """Raised when replay export or verification fails."""


@dataclass(frozen=True)
class EvidenceBundle:
    files: Mapping[str, bytes]
    manifest: Mapping[str, Any]
    row_counts: Mapping[str, int]


def write_and_fsync(path: Path, content: bytes) -> None:
    """Write bytes to file and fsync."""
    with open(path, "wb") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())


def fsync_directory(path: Path) -> None:
    """Fsync a directory descriptor on supported platforms."""
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        fd = os.open(str(path), flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:
        pass


def get_git_state() -> tuple[str, bool]:
    """Return generator git head sha and worktree cleanliness."""
    try:
        sha_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        sha = sha_proc.stdout.strip()
        status_proc = subprocess.run(
            ["git", "status", "--porcelain", "-uno"],
            capture_output=True,
            text=True,
            check=True,
        )
        is_clean = len(status_proc.stdout.strip()) == 0
        return sha, is_clean
    except Exception:
        return "UNKNOWN_GIT_SHA", True


def read_json_file(path: Path) -> tuple[bytes, dict[str, Any]]:
    """Read a JSON file, returning raw bytes and parsed dict."""
    if not path.is_file():
        raise ProspectiveReplayExportError(f"File not found: {path}")
    raw = path.read_bytes()
    if not raw.strip():
        raise ProspectiveReplayExportError(f"Empty JSON file: {path}")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception as err:
        raise ProspectiveReplayExportError(f"Invalid JSON in {path}: {err}") from err
    if not isinstance(parsed, dict):
        raise ProspectiveReplayExportError(f"JSON root must be an object: {path}")
    return raw, parsed


def read_jsonl_file(path: Path) -> tuple[bytes, list[dict[str, Any]]]:
    """Read a JSON Lines file, returning raw bytes and list of parsed objects."""
    if not path.is_file():
        raise ProspectiveReplayExportError(f"File not found: {path}")
    raw = path.read_bytes()
    if not raw.strip():
        raise ProspectiveReplayExportError(f"Empty JSONL file: {path}")
    lines = raw.decode("utf-8").splitlines()
    records: list[dict[str, Any]] = []
    for line_idx, line in enumerate(lines, start=1):
        line_str = line.strip()
        if not line_str:
            continue
        try:
            item = json.loads(line_str)
        except Exception as err:
            raise ProspectiveReplayExportError(
                f"Invalid JSON at {path}:{line_idx}: {err}"
            ) from err
        if not isinstance(item, dict):
            raise ProspectiveReplayExportError(
                f"JSONL row at {path}:{line_idx} must be an object"
            )
        records.append(item)
    return raw, records


def validate_protocol_contract(protocol: Mapping[str, Any]) -> None:
    """Validate protocol structure and enforce strict equality with frozen Stage 5B2 contract."""
    assert_no_forbidden_fields(protocol)
    if protocol.get("schema_version") != SCHEMA_VERSION:
        raise ProspectiveReplayExportError("Protocol schema_version mismatch")
    if protocol.get("dataset_name") != "win-either-half-prospective-replay-protocol-v1":
        raise ProspectiveReplayExportError("Protocol dataset_name mismatch")

    offsets = protocol.get("candidate_offsets_seconds")
    if offsets != list(FROZEN_CANDIDATE_OFFSETS_SECONDS):
        raise ProspectiveReplayExportError(
            f"Protocol candidate offsets must match {list(FROZEN_CANDIDATE_OFFSETS_SECONDS)}"
        )

    attempt_c = protocol.get("attempt_contract", {})
    if attempt_c.get("expected_attempts_per_fixture") != EXPECTED_ATTEMPTS_PER_FIXTURE:
        raise ProspectiveReplayExportError("Protocol expected_attempts_per_fixture mismatch")
    if attempt_c.get("attempt_window_seconds") != ATTEMPT_WINDOW_SECONDS:
        raise ProspectiveReplayExportError("Protocol attempt_window_seconds mismatch")
    if not attempt_c.get("scheduled_at_must_equal_kickoff_minus_offset"):
        raise ProspectiveReplayExportError("Protocol scheduled_at rule must be true")
    if not attempt_c.get("attempted_at_must_be_before_kickoff"):
        raise ProspectiveReplayExportError("Protocol attempted_at rule must be true")

    quote_c = protocol.get("quote_contract", {})
    if quote_c.get("maximum_quote_age_seconds") != MAXIMUM_QUOTE_AGE_SECONDS:
        raise ProspectiveReplayExportError("Protocol maximum_quote_age_seconds mismatch")
    if not quote_c.get("requires_same_source"):
        raise ProspectiveReplayExportError("Protocol requires_same_source must be true")
    if not quote_c.get("requires_same_provider"):
        raise ProspectiveReplayExportError("Protocol requires_same_provider must be true")
    if not quote_c.get("requires_same_bookmaker"):
        raise ProspectiveReplayExportError("Protocol requires_same_bookmaker must be true")
    if not quote_c.get("requires_same_provider_event"):
        raise ProspectiveReplayExportError("Protocol requires_same_provider_event must be true")
    if not quote_c.get("requires_same_provider_market"):
        raise ProspectiveReplayExportError("Protocol requires_same_provider_market must be true")
    if not quote_c.get("requires_same_snapshot"):
        raise ProspectiveReplayExportError("Protocol requires_same_snapshot must be true")
    if not quote_c.get("requires_same_observed_at"):
        raise ProspectiveReplayExportError("Protocol requires_same_observed_at must be true")
    if quote_c.get("odds_values_emitted") is not False:
        raise ProspectiveReplayExportError("Protocol odds_values_emitted must be false")

    avail_c = protocol.get("availability_contract", {})
    if avail_c.get("statuses") != ["AVAILABLE", "UNAVAILABLE", "UNKNOWN", "INVALID"]:
        raise ProspectiveReplayExportError("Protocol availability statuses mismatch")
    if not avail_c.get("unavailable_requires_explicit_provider_evidence"):
        raise ProspectiveReplayExportError("Protocol explicit evidence rule must be true")
    if avail_c.get("missing_attempt_status") != "UNKNOWN":
        raise ProspectiveReplayExportError("Protocol missing attempt status must be UNKNOWN")
    if avail_c.get("capture_error_status") != "UNKNOWN":
        raise ProspectiveReplayExportError("Protocol capture error status must be UNKNOWN")
    if avail_c.get("contradiction_status") != "INVALID":
        raise ProspectiveReplayExportError("Protocol contradiction status must be INVALID")
    if not avail_c.get("invalid_precedes_unknown"):
        raise ProspectiveReplayExportError("Protocol invalid_precedes_unknown must be true")

    output_c = protocol.get("output_contract", {})
    if output_c.get("selected_offset_seconds") is not None:
        raise ProspectiveReplayExportError("Protocol selected_offset_seconds must be null")
    if output_c.get("selection_authorized") is not False:
        raise ProspectiveReplayExportError("Protocol selection_authorized must be false")
    if output_c.get("selection_status") != "UNSELECTED":
        raise ProspectiveReplayExportError("Protocol selection_status must be UNSELECTED")
    if not output_c.get("manifest_required"):
        raise ProspectiveReplayExportError("Protocol manifest_required must be true")
    if not output_c.get("transactional_write_required"):
        raise ProspectiveReplayExportError("Protocol transactional_write_required must be true")

    if not protocol.get("no_production_approval"):
        raise ProspectiveReplayExportError("Protocol no_production_approval must be true")


def format_csv(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> bytes:
    """Format a deterministic UTF-8 CSV with LF line endings."""
    lines: list[str] = [",".join(columns)]
    for row in rows:
        formatted_cells: list[str] = []
        for val in row:
            if val is None:
                formatted_cells.append("")
            elif isinstance(val, bool):
                formatted_cells.append("true" if val else "false")
            elif isinstance(val, datetime):
                formatted_cells.append(val.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
            elif isinstance(val, (int, float, Decimal)):
                formatted_cells.append(str(val))
            elif isinstance(val, (list, tuple, dict)):
                formatted_cells.append(
                    json.dumps(val, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                )
            else:
                formatted_cells.append(str(val))
        lines.append(",".join(formatted_cells))
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_outputs(
    *,
    source_qualification_raw: bytes,
    source_qualification_payload: Mapping[str, Any],
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
) -> EvidenceBundle:
    """Build all seven evidence output byte sequences entirely in memory."""
    # 1. Validate safety & protocols
    assert_no_forbidden_fields(source_qualification_payload)
    assert_no_forbidden_fields(fixtures_payload)
    assert_no_forbidden_fields(provider_mappings_payload)
    assert_no_forbidden_fields(protocol_payload)
    validate_protocol_contract(protocol_payload)

    qualified_provider_id = load_source_qualification(source_qualification_payload)
    fixtures = load_prospective_fixtures(fixtures_payload)
    mappings = load_provider_mappings(
        provider_mappings_payload, fixtures, qualified_provider_id
    )
    market_mappings = market_mapping_identity(mappings)

    expected_source = next(iter(fixtures.values())).expected_sources[0]

    # 2. Canonicalize and assign occurrence indices for raw attempts
    sorted_raw_attempts = sorted(raw_attempts, key=canonical_record_bytes)
    attempt_occurrences: dict[str, int] = {}
    attempt_parse_results: list[AttemptParseResult] = []

    for raw_att in sorted_raw_attempts:
        sha = canonical_record_sha256(raw_att)
        attempt_occurrences[sha] = attempt_occurrences.get(sha, 0) + 1
        occ_idx = attempt_occurrences[sha]

        parsed_att = parse_attempt(
            raw_att,
            fixtures=fixtures,
            mapping_by_market=market_mappings,
            qualified_provider_identifier=qualified_provider_id,
            expected_source=expected_source,
        )
        # Attach occurrence index
        attempt_parse_results.append(
            AttemptParseResult(
                input_record_sha256=parsed_att.input_record_sha256,
                record=parsed_att.record,
                reasons=parsed_att.reasons,
                candidate_key=parsed_att.candidate_key,
                raw_payload=parsed_att.raw_payload,
                occurrence_index=occ_idx,
            )
        )

    # 3. Canonicalize and assign occurrence indices for raw quotes
    sorted_raw_quotes = sorted(raw_quotes, key=canonical_record_bytes)
    quote_occurrences: dict[str, int] = {}
    quote_parse_results: list[QuoteParseResult] = []

    for raw_q in sorted_raw_quotes:
        sha = canonical_record_sha256(raw_q)
        quote_occurrences[sha] = quote_occurrences.get(sha, 0) + 1
        occ_idx = quote_occurrences[sha]

        parsed_q = parse_quote(
            raw_q,
            fixtures=fixtures,
            mappings=mappings,
            qualified_provider_identifier=qualified_provider_id,
            expected_source=expected_source,
        )
        quote_parse_results.append(
            QuoteParseResult(
                input_record_sha256=parsed_q.input_record_sha256,
                record=parsed_q.record,
                reasons=parsed_q.reasons,
                candidate_key=parsed_q.candidate_key,
                raw_payload=parsed_q.raw_payload,
                occurrence_index=occ_idx,
            )
        )

    # 4. Group attempts and quotes
    attempt_index = index_attempt_results(attempt_parse_results)

    # Index quotes by (fixture_id, market_id)
    quotes_by_fixture_market: dict[tuple[str, MarketId], list[QuoteParseResult]] = {}
    raw_quotes_by_fixture_market: dict[tuple[str, MarketId], list[Mapping[str, Any]]] = {}

    for q in quote_parse_results:
        f_id = q.raw_payload.get("fixture_identifier")
        m_id_raw = q.raw_payload.get("market_id")
        if isinstance(f_id, str) and isinstance(m_id_raw, str):
            try:
                m_id = MarketId(m_id_raw)
                if m_id in PERMITTED_MARKETS and f_id in fixtures:
                    quotes_by_fixture_market.setdefault((f_id, m_id), []).append(q)
                    raw_quotes_by_fixture_market.setdefault((f_id, m_id), []).append(q.raw_payload)
            except ValueError:
                pass

    # 5. Evaluate expected keys
    exp_keys = expected_attempt_keys(fixtures)
    if len(exp_keys) != len(fixtures) * EXPECTED_ATTEMPTS_PER_FIXTURE:
        raise ProspectiveReplayExportError("Expected key denominator length mismatch")

    replay_rows: list[ProspectiveReplayRow] = []
    validated_snapshots: list[ValidatedSnapshot] = []

    for key in exp_keys:
        f_id, m_id, offset = key
        fixture = fixtures[f_id]
        mapping = market_mappings[(f_id, m_id)]

        q_for_key = quotes_by_fixture_market.get((f_id, m_id), [])
        raw_q_for_key = raw_quotes_by_fixture_market.get((f_id, m_id), [])

        row, snap = evaluate_expected_key(
            key=key,
            fixture=fixture,
            attempt_index=attempt_index,
            raw_quotes_for_key=raw_q_for_key,
            parsed_quotes_for_key=q_for_key,
            mapping=mapping,
        )
        replay_rows.append(row)
        if snap is not None:
            validated_snapshots.append(snap)

    # 6. Generate CSV and JSON bytes
    # Normalized attempts
    def attempt_sort_key(res: AttemptParseResult) -> tuple[Any, ...]:
        raw = res.raw_payload
        f_id = str(raw.get("fixture_identifier", ""))
        m_id = str(raw.get("market_id", ""))
        offset = int(raw.get("offset_seconds_before_kickoff", 0)) if isinstance(raw.get("offset_seconds_before_kickoff"), int) else 0
        att_at = str(raw.get("attempted_at", ""))
        att_id = str(raw.get("attempt_id", ""))
        return (f_id, m_id, -offset, att_at, att_id, res.input_record_sha256, res.occurrence_index)

    sorted_attempts = sorted(attempt_parse_results, key=attempt_sort_key)
    attempt_table_rows: list[list[Any]] = []
    for a in sorted_attempts:
        r = a.record
        raw = a.raw_payload
        attempt_table_rows.append([
            a.input_record_sha256,
            a.occurrence_index,
            "VALID" if r is not None else "INVALID",
            list(a.reasons),
            r.attempt_id if r else raw.get("attempt_id"),
            r.fixture_identifier if r else raw.get("fixture_identifier"),
            r.market_id.value if r else raw.get("market_id"),
            r.source if r else raw.get("source"),
            r.provider_identifier if r else raw.get("provider_identifier"),
            r.bookmaker_identifier if r else raw.get("bookmaker_identifier"),
            r.provider_event_identifier if r else raw.get("provider_event_identifier"),
            r.provider_market_identifier if r else raw.get("provider_market_identifier"),
            r.offset_seconds_before_kickoff if r else raw.get("offset_seconds_before_kickoff"),
            r.scheduled_at if r else raw.get("scheduled_at"),
            r.attempted_at if r else raw.get("attempted_at"),
            r.result.value if r else raw.get("result"),
            r.capture_method if r else raw.get("capture_method"),
            r.quote_snapshot_id if r else raw.get("quote_snapshot_id"),
        ])
    attempts_csv_bytes = format_csv(NORMALIZED_ATTEMPT_COLUMNS, attempt_table_rows)

    # Valid & Rejected Quotes
    def quote_sort_key(res: QuoteParseResult) -> tuple[Any, ...]:
        raw = res.raw_payload
        f_id = str(raw.get("fixture_identifier", ""))
        m_id = str(raw.get("market_id", ""))
        o_id = str(raw.get("outcome_id", ""))
        obs_at = str(raw.get("observed_at", ""))
        snap_id = str(raw.get("quote_snapshot_id", ""))
        sel_id = str(raw.get("provider_selection_identifier", ""))
        return (f_id, m_id, o_id, obs_at, snap_id, sel_id, res.input_record_sha256, res.occurrence_index)

    valid_quote_results = [q for q in quote_parse_results if q.record is not None]
    rejected_quote_results = [q for q in quote_parse_results if q.record is None]

    sorted_valid_quotes = sorted(valid_quote_results, key=quote_sort_key)
    sorted_rejected_quotes = sorted(rejected_quote_results, key=quote_sort_key)

    valid_quote_table_rows: list[list[Any]] = []
    for q in sorted_valid_quotes:
        r = q.record
        assert r is not None
        valid_quote_table_rows.append([
            q.input_record_sha256,
            q.occurrence_index,
            r.fixture_identifier,
            r.market_id.value,
            r.outcome_id.value,
            r.source,
            r.provider_identifier,
            r.bookmaker_identifier,
            r.provider_event_identifier,
            r.provider_market_identifier,
            r.provider_selection_identifier,
            r.quote_snapshot_id,
            r.observed_at,
            r.fixture_kickoff,
            True,
        ])
    valid_quotes_csv_bytes = format_csv(VALID_QUOTE_COLUMNS, valid_quote_table_rows)

    rejected_quote_table_rows: list[list[Any]] = []
    for q in sorted_rejected_quotes:
        raw = q.raw_payload
        rejected_quote_table_rows.append([
            q.input_record_sha256,
            q.occurrence_index,
            raw.get("fixture_identifier"),
            raw.get("market_id"),
            raw.get("outcome_id"),
            raw.get("source"),
            raw.get("provider_identifier"),
            raw.get("bookmaker_identifier"),
            raw.get("quote_snapshot_id"),
            raw.get("observed_at"),
            raw.get("fixture_kickoff"),
            list(q.reasons),
        ])
    rejected_quotes_csv_bytes = format_csv(REJECTED_QUOTE_COLUMNS, rejected_quote_table_rows)

    # Validated Snapshots
    def snap_sort_key(snap: ValidatedSnapshot) -> tuple[Any, ...]:
        return (
            snap.fixture_identifier,
            snap.market_id.value,
            -snap.offset_seconds_before_kickoff,
            snap.observed_at.isoformat(),
            snap.quote_snapshot_id,
        )

    sorted_snapshots = sorted(validated_snapshots, key=snap_sort_key)
    snap_table_rows: list[list[Any]] = [
        [
            s.fixture_identifier,
            s.market_id.value,
            s.offset_seconds_before_kickoff,
            s.source,
            s.provider_identifier,
            s.bookmaker_identifier,
            s.provider_event_identifier,
            s.provider_market_identifier,
            s.quote_snapshot_id,
            s.observed_at,
            s.quote_age_seconds,
            s.yes_quote_record_sha256,
            s.no_quote_record_sha256,
        ]
        for s in sorted_snapshots
    ]
    snapshots_csv_bytes = format_csv(VALIDATED_SNAPSHOT_COLUMNS, snap_table_rows)

    # Evaluations
    def row_sort_key(row: ProspectiveReplayRow) -> tuple[Any, ...]:
        return (row.fixture_identifier, row.market_id.value, -row.offset_seconds_before_kickoff)

    sorted_replay_rows = sorted(replay_rows, key=row_sort_key)
    eval_table_rows: list[list[Any]] = [
        [
            r.fixture_identifier,
            r.market_id.value,
            r.offset_seconds_before_kickoff,
            r.scheduled_at,
            r.attempt_status,
            r.attempt_result,
            r.raw_quote_row_count,
            r.accepted_quote_row_count,
            r.rejected_quote_row_count,
            r.validated_snapshot_count,
            r.availability_status.value,
            r.availability_reason.value,
            r.validated_snapshot_id,
            r.validated_observed_at,
            r.validated_quote_age_seconds,
        ]
        for r in sorted_replay_rows
    ]
    evaluations_csv_bytes = format_csv(EVALUATION_COLUMNS, eval_table_rows)

    # Summary JSON
    summary_dict = aggregate_replay(sorted_replay_rows, fixtures)
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

    generated_files: dict[str, bytes] = {
        "normalized_attempts": attempts_csv_bytes,
        "valid_quotes": valid_quotes_csv_bytes,
        "rejected_quotes": rejected_quotes_csv_bytes,
        "validated_snapshots": snapshots_csv_bytes,
        "evaluations": evaluations_csv_bytes,
        "summary": summary_bytes,
    }

    row_counts = {
        "normalized_attempts": len(attempt_table_rows),
        "valid_quotes": len(valid_quote_table_rows),
        "rejected_quotes": len(rejected_quote_table_rows),
        "validated_snapshots": len(snap_table_rows),
        "evaluations": len(eval_table_rows),
        "summary": 1,
        "manifest": 1,
    }

    # Build Manifest
    git_sha, git_clean = get_git_state()

    manifest_dict: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": "win-either-half-prospective-replay-manifest-v1",
        "inputs": {
            "source_qualification": {
                "path": str(source_qual_path),
                "byte_size": len(source_qualification_raw),
                "sha256": hashlib.sha256(source_qualification_raw).hexdigest(),
            },
            "fixtures": {
                "path": str(fixtures_path),
                "byte_size": len(fixtures_raw),
                "sha256": hashlib.sha256(fixtures_raw).hexdigest(),
            },
            "provider_mappings": {
                "path": str(mappings_path),
                "byte_size": len(provider_mappings_raw),
                "sha256": hashlib.sha256(provider_mappings_raw).hexdigest(),
            },
            "attempts": {
                "path": str(attempts_path),
                "byte_size": len(attempts_raw),
                "sha256": hashlib.sha256(attempts_raw).hexdigest(),
            },
            "quotes": {
                "path": str(quotes_path),
                "byte_size": len(quotes_raw),
                "sha256": hashlib.sha256(quotes_raw).hexdigest(),
            },
            "protocol": {
                "path": str(protocol_path),
                "byte_size": len(protocol_raw),
                "sha256": hashlib.sha256(protocol_raw).hexdigest(),
            },
        },
        "outputs": {
            name: {
                "relative_name": OUTPUT_FILENAMES[name],
                "byte_size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "rows": row_counts[name],
            }
            for name, content in generated_files.items()
        },
        "protocol": {
            "candidate_offsets_seconds": list(FROZEN_CANDIDATE_OFFSETS_SECONDS),
            "attempt_window_seconds": ATTEMPT_WINDOW_SECONDS,
            "maximum_quote_age_seconds": MAXIMUM_QUOTE_AGE_SECONDS,
            "expected_attempts_per_fixture": EXPECTED_ATTEMPTS_PER_FIXTURE,
        },
        "market_registry": {
            m.value: "DISABLED" for m in sorted(PERMITTED_MARKETS, key=lambda x: x.value)
        },
        "model_status_registry": {
            m.value: "DISABLED" for m in sorted(PERMITTED_MARKETS, key=lambda x: x.value)
        },
        "generator": {
            "generator_git_head_sha": git_sha,
            "tracked_worktree_clean": git_clean,
        },
        "selected_offset_seconds": None,
        "selection_status": "UNSELECTED",
        "selection_authorized": False,
        "production_approval_authorized": False,
        "market_statuses": {
            "HOME_WIN_EITHER_HALF": "DISABLED",
            "AWAY_WIN_EITHER_HALF": "DISABLED",
        },
        "no_production_approval": "Stage 5B2 is observation evidence only.",
    }

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

    return EvidenceBundle(
        files=generated_files,
        manifest=manifest_dict,
        row_counts=row_counts,
    )


def commit_evidence_bundle(
    *,
    output_paths: Mapping[str, Path],
    contents: Mapping[str, bytes],
    force: bool,
) -> None:
    """Write the entire evidence set or restore the previous set byte-for-byte."""
    parents = {path.parent.resolve() for path in output_paths.values()}
    if len(parents) != 1:
        raise ProspectiveReplayExportError("All evidence outputs must share one directory")
    output_dir = next(iter(parents))
    output_dir.mkdir(parents=True, exist_ok=True)

    if not force:
        existing = [path for path in output_paths.values() if path.exists()]
        if existing:
            raise ProspectiveReplayExportError(
                "Evidence output already exists; use --force"
            )

    stage_dir = Path(tempfile.mkdtemp(prefix=".prospective-stage-", dir=output_dir))
    rollback_dir = Path(tempfile.mkdtemp(prefix=".prospective-rollback-", dir=output_dir))
    moved_old: list[tuple[Path, Path]] = []
    installed_new: list[Path] = []

    try:
        # Write and fsync every staged file before touching existing outputs.
        for name, destination in sorted(output_paths.items()):
            staged = stage_dir / destination.name
            write_and_fsync(staged, contents[name])

        # Move old files aside, then install the new set.
        for name, destination in sorted(output_paths.items()):
            if destination.exists():
                backup = rollback_dir / destination.name
                os.replace(destination, backup)
                moved_old.append((backup, destination))

        for name, destination in sorted(output_paths.items()):
            os.replace(stage_dir / destination.name, destination)
            installed_new.append(destination)

        fsync_directory(output_dir)
    except Exception:
        for destination in reversed(installed_new):
            if destination.exists():
                destination.unlink()
        for backup, destination in reversed(moved_old):
            if backup.exists():
                os.replace(backup, destination)
        fsync_directory(output_dir)
        raise
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

        # For manifest JSON, compare semantic JSON equality
        if name == "manifest":
            if stored_bytes != expected_bytes:
                stored_obj = json.loads(stored_bytes.decode("utf-8"))
                if stored_obj != bundle.manifest:
                    raise ProspectiveReplayExportError("Manifest mismatch")
        else:
            if stored_bytes != expected_bytes:
                raise ProspectiveReplayExportError(
                    f"Stored file {sibling_path.name} does not match expected bytes"
                )

            stored_sha = hashlib.sha256(stored_bytes).hexdigest()
            manifest_meta = stored_manifest.get("outputs", {}).get(name, {})
            if manifest_meta.get("sha256") != stored_sha:
                raise ProspectiveReplayExportError(
                    f"Manifest sha256 mismatch for {name}: {manifest_meta.get('sha256')} != {stored_sha}"
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
        source_qual_raw, source_qual = read_json_file(parsed.source_qualification)
        fixtures_raw, fixtures = read_json_file(parsed.fixtures)
        mappings_raw, mappings = read_json_file(parsed.provider_mappings)
        protocol_raw, protocol = read_json_file(parsed.protocol)

        attempts_raw, raw_attempts = read_jsonl_file(parsed.attempts)
        quotes_raw, raw_quotes = read_jsonl_file(parsed.quotes)

        bundle = build_outputs(
            source_qualification_raw=source_qual_raw,
            source_qualification_payload=source_qual,
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
