#!/usr/bin/env python3
"""Export deterministic Stage 5B2 Win Either Half prospective replay evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Optional, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from domain.markets import MarketId  # noqa: E402
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus  # noqa: E402
from domain.win_either_half_prospective_replay import (  # noqa: E402
    DEFAULT_MAX_QUOTE_AGE_SECONDS,
    PERMITTED_MARKETS,
    ProspectiveReplayError,
    QuoteParseResult,
    aggregate_replay,
    load_fixture_catalog,
    load_provider_mappings,
    parse_quotes,
    reject_forbidden_fields,
    run_prospective_replay,
    validate_candidate_offsets,
    validate_source_qualification_report,
)
from scripts.freeze_evidence_baseline import get_code_state  # noqa: E402

DATASET_NAME = "win-either-half-prospective-replay-v1"
DEFAULT_PROTOCOL_PATH = (
    REPOSITORY_ROOT
    / "artifacts/research-protocols/win-either-half-prospective-replay-v1.json"
)
DEFAULT_ROWS_OUTPUT = (
    REPOSITORY_ROOT
    / ".cache/athena-research/win-either-half/prospective-replay-rows-v1.csv"
)
DEFAULT_REJECTED_OUTPUT = (
    REPOSITORY_ROOT
    / ".cache/athena-research/win-either-half/prospective-replay-rejected-quotes-v1.csv"
)
DEFAULT_SUMMARY_OUTPUT = (
    REPOSITORY_ROOT
    / ".cache/athena-research/win-either-half/prospective-replay-summary-v1.json"
)
ROW_COLUMNS = (
    "fixture_identifier",
    "market_id",
    "source",
    "fixture_kickoff",
    "candidate_offset_seconds",
    "decision_at",
    "raw_quote_row_count",
    "structurally_valid_quote_row_count",
    "at_or_before_decision_quote_row_count",
    "fresh_quote_row_count",
    "complete_snapshot_count",
    "availability_status",
    "availability_reason",
    "selected_snapshot_id",
    "selected_observed_at",
    "selected_quote_age_seconds",
)
REJECTED_COLUMNS = (
    "source_row_number",
    "fixture_identifier",
    "market_id",
    "outcome_id",
    "source",
    "quote_snapshot_id",
    "observed_at",
    "fixture_kickoff",
    "rejection_reasons_json",
)
FORBIDDEN_OUTPUT_KEYS = {
    "decimal_odds",
    "yes_odds",
    "no_odds",
    "model_probability",
    "calibrated_probability",
    "edge",
    "expected_value",
    "kelly",
    "stake",
    "bet",
    "bet_decision",
}


class ProspectiveReplayExportError(RuntimeError):
    """A bounded Stage 5B2 lifecycle, protocol, or output failure."""


@dataclass(frozen=True)
class ValidatedProtocol:
    value: Mapping[str, Any]
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class InputFile:
    path: Path
    content: bytes

    def identity(self, *, rows: Optional[int] = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "relative_name": self.path.name,
            "byte_size": len(self.content),
            "sha256": hashlib.sha256(self.content).hexdigest(),
        }
        if rows is not None:
            result["rows"] = rows
        return result


def _canonical_json_bytes(value: Any, *, pretty: bool = True) -> bytes:
    rendered = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )
    if pretty:
        rendered += "\n"
    return rendered.encode("utf-8")


def _read(path: Path, label: str) -> InputFile:
    try:
        return InputFile(path, path.read_bytes())
    except OSError as error:
        raise ProspectiveReplayExportError(f"Could not read {label}: {path}") from error


def _read_json(path: Path, label: str) -> tuple[Any, InputFile]:
    file = _read(path, label)
    try:
        return json.loads(file.content.decode("utf-8", errors="strict")), file
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProspectiveReplayExportError(f"{label} must be valid UTF-8 JSON") from error


def _read_jsonl(path: Path, label: str) -> tuple[list[Mapping[str, Any]], InputFile]:
    file = _read(path, label)
    try:
        text = file.content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ProspectiveReplayExportError(f"{label} must be UTF-8") from error
    rows: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ProspectiveReplayExportError(
                f"{label} line {line_number} is not JSON"
            ) from error
        if not isinstance(value, Mapping):
            raise ProspectiveReplayExportError(
                f"{label} line {line_number} must be an object"
            )
        rows.append(value)
    return rows, file


def validate_protocol_contract(
    value: Any,
    content: bytes,
    *,
    committed_protocol_path: Path = DEFAULT_PROTOCOL_PATH,
) -> ValidatedProtocol:
    committed_value, committed_file = _read_json(
        committed_protocol_path, "Committed Stage 5B2 protocol"
    )
    if not isinstance(value, Mapping) or value != committed_value:
        raise ProspectiveReplayExportError(
            "Supplied prospective replay protocol differs from the committed protocol"
        )
    expected_markets = {
        market.value: {"line": None, "outcomes": ["YES", "NO"]}
        for market in sorted(PERMITTED_MARKETS, key=lambda item: item.value)
    }
    checks = (
        (value.get("schema_version"), 1, "schema version"),
        (
            value.get("dataset_name"),
            "win-either-half-prospective-replay-protocol-v1",
            "dataset name",
        ),
        (
            value.get("maximum_quote_age_seconds"),
            DEFAULT_MAX_QUOTE_AGE_SECONDS,
            "maximum quote age",
        ),
        (value.get("market_scope"), expected_markets, "market scope"),
        (
            value.get("source_qualification_required_statuses"),
            [
                "QUALIFIED_FOR_HISTORICAL_RESEARCH",
                "QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY",
            ],
            "source qualification statuses",
        ),
        (
            value.get("selection_policy", {}).get("selection_status"),
            "UNSELECTED",
            "selection status",
        ),
        (
            value.get("output_contract", {}).get("selected_offset_emitted"),
            False,
            "selected offset output",
        ),
        (
            value.get("output_contract", {}).get("odds_values_emitted"),
            False,
            "odds output policy",
        ),
        (value.get("no_production_approval"), True, "no-production flag"),
    )
    for actual, expected, label in checks:
        if actual != expected:
            raise ProspectiveReplayExportError(
                f"Prospective replay protocol {label} drifted"
            )
    validate_candidate_offsets(value.get("candidate_offsets_seconds"))
    minimum = value.get("minimum_fixtures_for_interpretation")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum <= 0:
        raise ProspectiveReplayExportError(
            "Prospective replay protocol minimum support drifted"
        )
    holdout = value.get("holdout_governance")
    if not isinstance(holdout, Mapping) or holdout != {
        "final_test_season": "2025-26",
        "final_test_status": "ALREADY_CONSUMED_AUDIT_HOLDOUT",
        "match_outcomes_forbidden_from_offset_evaluation": True,
        "model_performance_forbidden_from_offset_evaluation": True,
        "pricing_profitability_forbidden_from_offset_evaluation": True,
        "prospective_validation_required": True,
        "production_approval_authorized": False,
    }:
        raise ProspectiveReplayExportError(
            "Prospective replay holdout governance drifted"
        )
    if content != committed_file.content:
        raise ProspectiveReplayExportError(
            "Supplied protocol bytes differ from the committed protocol"
        )
    return ValidatedProtocol(
        value=value,
        byte_size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def _csv_bytes(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column) for column in columns})
    return buffer.getvalue().encode("utf-8")


def _rejected_rows(results: Sequence[QuoteParseResult]) -> list[dict[str, Any]]:
    rows = []
    for result in results:
        if result.accepted:
            continue
        audit = result.audit_dict()
        rows.append(
            {
                "source_row_number": result.source_row_number,
                "fixture_identifier": audit.get("fixture_identifier"),
                "market_id": audit.get("market_id"),
                "outcome_id": audit.get("outcome_id"),
                "source": audit.get("source"),
                "quote_snapshot_id": audit.get("quote_snapshot_id"),
                "observed_at": audit.get("observed_at"),
                "fixture_kickoff": audit.get("fixture_kickoff"),
                "rejection_reasons_json": json.dumps(
                    [reason.value for reason in result.reasons],
                    separators=(",", ":"),
                ),
            }
        )
    return rows


def _walk_keys(value: Any):
    if isinstance(value, Mapping):
        for key, nested in value.items():
            yield str(key).lower()
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_keys(nested)


def build_outputs(
    *,
    protocol: ValidatedProtocol,
    source_qualification: Mapping[str, Any],
    source_qualification_file: InputFile,
    fixtures_value: Mapping[str, Any],
    fixtures_file: InputFile,
    mappings_value: Any,
    mappings_file: InputFile,
    quote_rows: Sequence[Mapping[str, Any]],
    quotes_file: InputFile,
    code_state: Mapping[str, Any],
) -> tuple[bytes, bytes, bytes, dict[str, Any]]:
    reject_forbidden_fields(source_qualification, location="source_qualification")
    reject_forbidden_fields(fixtures_value, location="fixtures")
    reject_forbidden_fields(mappings_value, location="provider_mappings")
    reject_forbidden_fields(quote_rows, location="quotes")
    qualification = validate_source_qualification_report(source_qualification)
    fixtures, expected_sources = load_fixture_catalog(
        fixtures_value,
        provider_identifier=qualification["provider_identifier"],
    )
    mapping_lookup, _ = load_provider_mappings(
        mappings_value,
        fixtures=fixtures,
        expected_sources=expected_sources,
    )
    quote_results = parse_quotes(
        quote_rows,
        fixtures=fixtures,
        mapping_lookup=mapping_lookup,
    )
    offsets = validate_candidate_offsets(
        protocol.value["candidate_offsets_seconds"]
    )
    replay_rows = run_prospective_replay(
        fixtures=fixtures,
        expected_sources=expected_sources,
        offsets=offsets,
        raw_quote_rows=quote_rows,
        quote_results=quote_results,
        max_quote_age_seconds=protocol.value["maximum_quote_age_seconds"],
    )
    row_dicts = [row.to_dict() for row in replay_rows]
    rejected_dicts = _rejected_rows(quote_results)
    row_bytes = _csv_bytes(row_dicts, ROW_COLUMNS)
    rejected_bytes = _csv_bytes(rejected_dicts, REJECTED_COLUMNS)
    aggregate = aggregate_replay(
        replay_rows,
        minimum_fixtures_for_interpretation=protocol.value[
            "minimum_fixtures_for_interpretation"
        ],
    )
    expected_denominator = (
        len(fixtures) * len(expected_sources) * len(PERMITTED_MARKETS) * len(offsets)
    )
    if len(replay_rows) != expected_denominator:
        raise ProspectiveReplayExportError(
            "Prospective replay denominator does not reconcile"
        )
    market_safety = {
        market.value: MODEL_STATUS_REGISTRY[market].status.value
        for market in sorted(PERMITTED_MARKETS, key=lambda item: item.value)
    }
    if any(status != ModelStatus.DISABLED.value for status in market_safety.values()):
        raise ProspectiveReplayExportError("Win Either Half markets are not disabled")
    summary = {
        "schema_version": 1,
        "dataset_name": DATASET_NAME,
        "provider_identifier": qualification["provider_identifier"],
        "prospective_source_status": qualification["prospective_replay_status"],
        "candidate_offsets_seconds": list(offsets),
        "maximum_quote_age_seconds": protocol.value["maximum_quote_age_seconds"],
        "minimum_fixtures_for_interpretation": protocol.value[
            "minimum_fixtures_for_interpretation"
        ],
        "fixture_count": len(fixtures),
        "expected_sources": list(expected_sources),
        "expected_row_denominator": expected_denominator,
        "quote_rows_supplied": len(quote_rows),
        "quote_rows_structurally_accepted": sum(
            result.accepted for result in quote_results
        ),
        "quote_rows_rejected": len(rejected_dicts),
        "aggregate": aggregate,
        "files": {
            "source_qualification": source_qualification_file.identity(),
            "fixtures": fixtures_file.identity(rows=len(fixtures)),
            "provider_mappings": mappings_file.identity(rows=len(mappings_value)),
            "quotes": quotes_file.identity(rows=len(quote_rows)),
            "rows_output": {
                "rows": len(row_dicts),
                "byte_size": len(row_bytes),
                "sha256": hashlib.sha256(row_bytes).hexdigest(),
            },
            "rejected_quotes_output": {
                "rows": len(rejected_dicts),
                "byte_size": len(rejected_bytes),
                "sha256": hashlib.sha256(rejected_bytes).hexdigest(),
            },
        },
        "protocol": {
            "dataset_name": protocol.value["dataset_name"],
            "byte_size": protocol.byte_size,
            "sha256": protocol.sha256,
        },
        "holdout_governance": dict(protocol.value["holdout_governance"]),
        "market_safety": market_safety,
        "generator": {
            "generator_git_head_sha": code_state.get("evidence_git_head_sha"),
            "tracked_worktree_clean": code_state.get("tracked_worktree_clean"),
        },
        "no_production_approval": (
            "Stage 5B2 measures prospective operational quote availability only. "
            "It selects no decision offset, enables no market, and authorizes no "
            "value calculation, recommendation, execution, booking code, or bet."
        ),
    }
    if FORBIDDEN_OUTPUT_KEYS.intersection(_walk_keys(summary)):
        raise ProspectiveReplayExportError(
            "Prospective replay summary contains a forbidden output field"
        )
    summary_bytes = _canonical_json_bytes(summary)
    return row_bytes, rejected_bytes, summary_bytes, summary


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write(path: Path, content: bytes, *, force: bool) -> None:
    if path.exists() and not force:
        raise ProspectiveReplayExportError(
            f"Output already exists; use --force: {path}"
        )
    _atomic_write(path, content)


def _check(path: Path, expected: bytes, label: str) -> None:
    actual = _read(path, label).content
    if actual != expected:
        raise ProspectiveReplayExportError(f"{label} differs")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure provider-qualified prospective Win Either Half quote "
            "availability at predeclared decision offsets."
        )
    )
    parser.add_argument("--source-qualification", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--provider-mappings", type=Path, required=True)
    parser.add_argument("--quotes", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)
    parser.add_argument("--rows-output", type=Path, default=DEFAULT_ROWS_OUTPUT)
    parser.add_argument(
        "--rejected-output", type=Path, default=DEFAULT_REJECTED_OUTPUT
    )
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--check-rows", type=Path)
    parser.add_argument("--check-rejected", type=Path)
    parser.add_argument("--check-summary", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        protocol_value, protocol_file = _read_json(args.protocol, "Protocol")
        protocol = validate_protocol_contract(protocol_value, protocol_file.content)
        source_value, source_file = _read_json(
            args.source_qualification, "Source qualification report"
        )
        fixtures_value, fixtures_file = _read_json(args.fixtures, "Fixture catalog")
        mappings_value, mappings_file = _read_json(
            args.provider_mappings, "Provider mappings"
        )
        if not isinstance(fixtures_value, Mapping):
            raise ProspectiveReplayExportError("Fixture catalog must be an object")
        if not isinstance(mappings_value, list):
            raise ProspectiveReplayExportError("Provider mappings must be a list")
        quote_rows, quotes_file = _read_jsonl(args.quotes, "Quote records")
        code_state = get_code_state(REPOSITORY_ROOT)
        if not code_state.get("tracked_worktree_clean"):
            raise ProspectiveReplayExportError("Tracked worktree is dirty")
        row_bytes, rejected_bytes, summary_bytes, summary = build_outputs(
            protocol=protocol,
            source_qualification=source_value,
            source_qualification_file=source_file,
            fixtures_value=fixtures_value,
            fixtures_file=fixtures_file,
            mappings_value=mappings_value,
            mappings_file=mappings_file,
            quote_rows=quote_rows,
            quotes_file=quotes_file,
            code_state=code_state,
        )
        checks = (args.check_rows, args.check_rejected, args.check_summary)
        if any(check is not None for check in checks):
            if not all(check is not None for check in checks):
                raise ProspectiveReplayExportError(
                    "All three --check outputs are required together"
                )
            _check(args.check_rows, row_bytes, "Stored replay rows")
            _check(args.check_rejected, rejected_bytes, "Stored rejected quotes")
            _check(args.check_summary, summary_bytes, "Stored replay summary")
            print("Stage 5B2 prospective replay verified")
            return 0
        _write(args.rows_output, row_bytes, force=args.force)
        _write(args.rejected_output, rejected_bytes, force=args.force)
        _write(args.summary_output, summary_bytes, force=args.force)
        print(
            "Stage 5B2 prospective replay generated: "
            f"provider={summary['provider_identifier']} rows={summary['expected_row_denominator']}"
        )
        return 0
    except (ProspectiveReplayError, ProspectiveReplayExportError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
