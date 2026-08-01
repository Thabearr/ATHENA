#!/usr/bin/env python3
"""Offline Stage 5B1 Win Either Half source-qualification exporter."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Optional, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from domain.markets import MarketId  # noqa: E402
from domain.model_status import MODEL_STATUS_REGISTRY  # noqa: E402
from domain.win_either_half_pricing_source_qualification import (  # noqa: E402
    DEFAULT_DECISION_PROTOCOL,
    GateEvidence,
    GateId,
    GateStatus,
    EXECUTION_REQUIRED_GATES,
    HISTORICAL_REQUIRED_GATES,
    KICKOFF_TOLERANCE_SECONDS,
    LIVE_REQUIRED_GATES,
    MARKET_SEMANTICS,
    OPTIONAL_GATES,
    PERMITTED_MARKETS,
    PROSPECTIVE_REQUIRED_GATES,
    QualificationStatus,
    SCHEMA_VERSION,
    SourceQualificationError,
    SourceRole,
    FixtureMappingStatus,
    FixtureReference,
    canonical_market_registry_snapshot,
    evaluate_fixture_mapping,
    qualify_mandatory_gates,
    qualify_prospective_replay,
    validate_market_semantics,
    validate_snapshot_identity,
)
from scripts.freeze_evidence_baseline import get_code_state  # noqa: E402


DATASET_NAME = "win-either-half-pricing-source-qualification-v1"
FROZEN_FIXTURE_MARKET_DENOMINATOR = {
    "CALIBRATION_FIT_OOF": 21270,
    "VALIDATION_SELECTION": 6952,
    "FINAL_TEST": 8096,
    "total": 36318,
}
DEFAULT_PROTOCOL_PATH = (
    REPOSITORY_ROOT
    / "artifacts/research-protocols/win-either-half-pricing-source-qualification-v1.json"
)
DEFAULT_OUTPUT_PATH = (
    REPOSITORY_ROOT
    / ".cache/athena-research/win-either-half/pricing-source-qualification-v1.json"
)
FORBIDDEN_FIELDS = {
    "edge",
    "edge_pp",
    "expected_value",
    "kelly",
    "kelly_stake",
    "profitability",
    "stake",
    "bet",
    "acca",
}
REQUIRED_EVIDENCE_SECTIONS = (
    "market_semantics_evidence",
    "outcome_evidence",
    "quote_field_evidence",
    "timestamp_evidence",
    "snapshot_evidence",
    "historical_retention_evidence",
    "live_pricing_evidence",
    "fixture_mapping_evidence",
    "export_reproducibility_evidence",
    "licensing_and_retention_evidence",
    "execution_workflow_evidence",
    "booking_code_evidence",
)
CONSUMED_HOLDOUT_GOVERNANCE = {
    "final_test_season": "2025-26",
    "status": "ALREADY_CONSUMED_AUDIT_HOLDOUT",
    "provider_selection_must_not_use_target_outcomes_or_performance": True,
    "prospective_validation_required": True,
    "production_approval_authorized": False,
}


class QualificationExportError(RuntimeError):
    """A bounded Stage 5B1 CLI, lifecycle, or evidence error."""


@dataclass(frozen=True)
class ValidatedProtocol:
    value: Mapping[str, Any]
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class DerivedGate:
    status: GateStatus
    reason: str
    evidence_references: tuple[str, ...] = ()


def _canonical_json_bytes(value: Any, *, pretty: bool = True) -> bytes:
    text = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":") if not pretty else None,
        indent=2 if pretty else None,
    )
    if pretty:
        text += "\n"
    return text.encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_json(path: Path, label: str) -> tuple[Any, bytes]:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise QualificationExportError(f"Could not read {label}: {path.name}") from error
    try:
        return json.loads(content.decode("utf-8")), content
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QualificationExportError(f"{label} is not valid UTF-8 JSON") from error


def validate_protocol_contract(
    value: Any,
    content: bytes,
    *,
    committed_protocol_path: Path = DEFAULT_PROTOCOL_PATH,
) -> ValidatedProtocol:
    """Require semantic equality with the committed, code-aligned protocol."""
    committed, _ = _read_json(committed_protocol_path, "Committed qualification protocol")
    if not isinstance(value, Mapping) or value != committed:
        raise QualificationExportError("Supplied protocol differs from committed protocol")
    expected_role_gates = {
        SourceRole.HISTORICAL_RESEARCH_SOURCE.value: [
            gate.value for gate in HISTORICAL_REQUIRED_GATES
        ],
        SourceRole.LIVE_PRICING_SOURCE.value: [gate.value for gate in LIVE_REQUIRED_GATES],
        SourceRole.EXECUTION_BOOKMAKER.value: [
            gate.value for gate in EXECUTION_REQUIRED_GATES
        ],
        "PROSPECTIVE_REPLAY": [gate.value for gate in PROSPECTIVE_REQUIRED_GATES],
    }
    expected_market_scope = {
        market.value: {
            "line": None,
            "no_settlement": MARKET_SEMANTICS[market]["no_settlement"],
            "outcomes": ["YES", "NO"],
            "subject": MARKET_SEMANTICS[market]["subject"],
            "yes_settlement": MARKET_SEMANTICS[market]["yes_settlement"],
        }
        for market in PERMITTED_MARKETS
    }
    expected_snapshot = {
        "derived_identifier_components": [
            "provider",
            "fixture",
            "market",
            "bookmaker",
            "exact_common_update_timestamp",
        ],
        "required_outcomes": ["YES", "NO"],
        "same_bookmaker": True,
        "same_fixture": True,
        "same_market": True,
        "same_observed_at": True,
        "same_snapshot_identifier": True,
    }
    expected_holdout = {
        "final_test_season": "2025-26",
        "prospective_validation_required": True,
        "provider_selection_must_not_use_target_outcomes_or_performance": True,
        "status": "ALREADY_CONSUMED_AUDIT_HOLDOUT",
    }
    checks = (
        (
            value.get("mandatory_gate_policy"),
            "ALL_REQUIRED_GATES_PASS; UNKNOWN_AND_NOT_APPLICABLE_NEVER_QUALIFY; NO_WEIGHTED_SCORE",
            "mandatory gate policy",
        ),
        (value.get("role_mandatory_gates"), expected_role_gates, "mandatory gate lists"),
        (
            value.get("not_applicable_allowlist"),
            {
                "EXECUTION_BOOKMAKER": [],
                "HISTORICAL_RESEARCH_SOURCE": [],
                "LIVE_PRICING_SOURCE": [],
                "PROSPECTIVE_REPLAY": [],
            },
            "NOT_APPLICABLE allowlist",
        ),
        (value.get("optional_capabilities"), ["booking_code_support"], "optional capabilities"),
        (
            value.get("qualification_statuses"),
            [status.value for status in QualificationStatus],
            "qualification statuses",
        ),
        (value.get("market_scope"), expected_market_scope, "market semantics"),
        (
            value.get("fixture_mapping", {}).get("kickoff_tolerance_seconds"),
            KICKOFF_TOLERANCE_SECONDS,
            "fixture tolerance",
        ),
        (value.get("snapshot_contract"), expected_snapshot, "snapshot contract"),
        (
            value.get("decision_protocol", {}).get("maximum_quote_age_seconds"),
            900,
            "maximum quote age",
        ),
        (
            value.get("decision_protocol"),
            DEFAULT_DECISION_PROTOCOL.to_dict(),
            "decision protocol",
        ),
        (
            value.get("frozen_fixture_market_denominator"),
            FROZEN_FIXTURE_MARKET_DENOMINATOR,
            "frozen denominator",
        ),
        (value.get("holdout_governance"), expected_holdout, "holdout governance"),
        (value.get("no_production_approval"), True, "no-production-approval flag"),
    )
    for actual, expected, label in checks:
        if actual != expected:
            raise QualificationExportError(f"Qualification protocol {label} drifted")
    return ValidatedProtocol(value, len(content), _sha256(content))


def _stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_evidence_files(
    records: Any,
    *,
    evidence_root: Path,
) -> list[dict]:
    """Verify safe, relative, immutable evidence-file identities."""
    if not isinstance(records, list):
        raise QualificationExportError("evidence_files must be a list")
    try:
        root = evidence_root.resolve(strict=True)
    except OSError as error:
        raise QualificationExportError("Evidence root does not exist") from error
    identities = []
    seen = set()
    for row in records:
        if not isinstance(row, Mapping):
            raise QualificationExportError("Evidence file row must be an object")
        relative_text = row.get("path")
        if not isinstance(relative_text, str) or not relative_text.strip():
            raise QualificationExportError("Evidence file path is required")
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise QualificationExportError("Evidence file path must be safely relative")
        candidate = root / relative
        if candidate.is_symlink():
            raise QualificationExportError("Symlinked evidence files are forbidden")
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as error:
            raise QualificationExportError("Evidence file escapes the allowed root") from error
        if not resolved.is_file():
            raise QualificationExportError("Evidence path must identify a regular file")
        normalized = relative.as_posix()
        if normalized in seen:
            raise QualificationExportError("Duplicate evidence file identity")
        seen.add(normalized)
        actual_size = resolved.stat().st_size
        actual_sha = _stream_sha256(resolved)
        if row.get("byte_size") != actual_size:
            raise QualificationExportError("Evidence file byte-size mismatch")
        if row.get("sha256") != actual_sha:
            raise QualificationExportError("Evidence file SHA-256 mismatch")
        identities.append(
            {"relative_path": normalized, "byte_size": actual_size, "sha256": actual_sha}
        )
    return sorted(identities, key=lambda item: item["relative_path"])


def _bounded_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualificationExportError(f"{field} is required")
    return value.strip()[:500]


def _load_gates(value: Any) -> dict[GateId, GateEvidence]:
    if not isinstance(value, Mapping):
        raise QualificationExportError("gate_evidence must be an object")
    gates = {}
    for name, row in value.items():
        try:
            gate = GateId(name)
        except (TypeError, ValueError) as error:
            raise QualificationExportError(f"Unknown qualification gate: {name}") from error
        try:
            gates[gate] = GateEvidence.from_mapping(row)
        except SourceQualificationError as error:
            raise QualificationExportError(str(error)) from error
    return gates


def _parse_checked_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise QualificationExportError("evidence_checked_at is required")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise QualificationExportError("evidence_checked_at must be ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QualificationExportError("evidence_checked_at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _section_metadata(section: Mapping[str, Any], label: str) -> Optional[DerivedGate]:
    reference = section.get("evidence_reference")
    checked_at = section.get("checked_at")
    if reference is None or checked_at is None:
        return DerivedGate(GateStatus.UNKNOWN, f"MISSING_{label}_DOCUMENTATION")
    if not isinstance(reference, str) or not reference.strip():
        return DerivedGate(GateStatus.FAIL, f"INVALID_{label}_EVIDENCE_REFERENCE")
    try:
        _parse_checked_at(checked_at)
    except QualificationExportError:
        return DerivedGate(GateStatus.FAIL, f"INVALID_{label}_CHECKED_AT")
    return None


def _reference(section: Mapping[str, Any]) -> tuple[str, ...]:
    value = section.get("evidence_reference")
    return (value.strip(),) if isinstance(value, str) and value.strip() else ()


def _strict_strings(
    section: Mapping[str, Any], fields: Sequence[str], label: str
) -> Optional[DerivedGate]:
    missing = [
        field
        for field in fields
        if field not in section or section.get(field) is None or section.get(field) == ""
    ]
    if missing:
        return DerivedGate(GateStatus.UNKNOWN, f"MISSING_{label}_FIELDS")
    if any(
        not isinstance(section.get(field), str) or not section.get(field).strip()
        for field in fields
    ):
        return DerivedGate(GateStatus.FAIL, f"INVALID_{label}_FIELD_TYPE")
    return None


def _strict_true(
    section: Mapping[str, Any], fields: Sequence[str], label: str
) -> Optional[DerivedGate]:
    if any(field not in section for field in fields):
        return DerivedGate(GateStatus.UNKNOWN, f"MISSING_{label}_EVIDENCE")
    if any(section.get(field) is not True for field in fields):
        return DerivedGate(GateStatus.FAIL, f"CONTRADICTORY_{label}_EVIDENCE")
    return None


def _merge_derived(*values: DerivedGate) -> DerivedGate:
    references = tuple(
        sorted({reference for value in values for reference in value.evidence_references})
    )
    failures = [value.reason for value in values if value.status is GateStatus.FAIL]
    if failures:
        return DerivedGate(GateStatus.FAIL, ";".join(sorted(failures)), references)
    unknown = [value.reason for value in values if value.status is GateStatus.UNKNOWN]
    if unknown:
        return DerivedGate(GateStatus.UNKNOWN, ";".join(sorted(unknown)), references)
    return DerivedGate(GateStatus.PASS, "STRUCTURED_EVIDENCE_VALIDATED", references)


def _derive_market_and_outcomes(value: Mapping[str, Any]) -> dict[GateId, DerivedGate]:
    section = value["market_semantics_evidence"]
    section_problem = _section_metadata(section, "MARKET_SEMANTICS")
    if section_problem:
        return {
            GateId.EXACT_MARKET_SEMANTICS: section_problem,
            GateId.EXACT_YES_NO_STRUCTURE: section_problem,
        }
    rows = section.get("markets")
    if not isinstance(rows, list) or not rows:
        missing = DerivedGate(GateStatus.UNKNOWN, "MISSING_MARKET_DOCUMENTATION")
        return {
            GateId.EXACT_MARKET_SEMANTICS: missing,
            GateId.EXACT_YES_NO_STRUCTURE: missing,
        }
    by_market = {}
    results = []
    references = set(_reference(section))
    for row in rows:
        if not isinstance(row, Mapping):
            results.append(DerivedGate(GateStatus.FAIL, "INVALID_MARKET_EVIDENCE_ROW"))
            continue
        try:
            market = MarketId(row.get("market_id"))
        except (TypeError, ValueError):
            results.append(DerivedGate(GateStatus.FAIL, "UNKNOWN_MARKET"))
            continue
        if market in by_market:
            results.append(DerivedGate(GateStatus.FAIL, "DUPLICATE_MARKET_EVIDENCE"))
            continue
        by_market[market] = row
        if row.get("checked_at") is None:
            results.append(
                DerivedGate(GateStatus.UNKNOWN, "MISSING_MARKET_CHECKED_AT")
            )
            continue
        try:
            result = validate_market_semantics(row)
        except SourceQualificationError:
            results.append(
                DerivedGate(GateStatus.FAIL, "INVALID_MARKET_CHECKED_AT")
            )
            continue
        references.update(_reference(row))
        results.append(DerivedGate(result.status, result.reason, _reference(row)))
    if set(by_market) != set(PERMITTED_MARKETS):
        results.append(DerivedGate(GateStatus.UNKNOWN, "MISSING_CANONICAL_MARKET_EVIDENCE"))
    semantics = _merge_derived(*results)

    outcome = value["outcome_evidence"]
    outcome_problem = _section_metadata(outcome, "OUTCOME")
    if outcome_problem:
        outcome_result = outcome_problem
    else:
        string_problem = _strict_strings(
            outcome,
            (
                "provider_yes_selection_identifier",
                "provider_yes_selection_label",
                "provider_no_selection_identifier",
                "provider_no_selection_label",
            ),
            "OUTCOME",
        )
        if string_problem:
            outcome_result = string_problem
        elif outcome.get("canonical_outcome_ids") != ["YES", "NO"]:
            outcome_result = DerivedGate(GateStatus.FAIL, "YES_NO_IDENTIFIERS_MISMATCH")
        else:
            outcome_result = DerivedGate(
                GateStatus.PASS, "EXACT_YES_NO_STRUCTURE", _reference(outcome)
            )
    yes_no = _merge_derived(
        DerivedGate(semantics.status, semantics.reason, tuple(sorted(references))),
        outcome_result,
    )
    return {
        GateId.EXACT_MARKET_SEMANTICS: DerivedGate(
            semantics.status, semantics.reason, tuple(sorted(references))
        ),
        GateId.EXACT_YES_NO_STRUCTURE: yes_no,
    }


def _derive_quote_fields(value: Mapping[str, Any]) -> dict[GateId, DerivedGate]:
    section = value["quote_field_evidence"]
    metadata = _section_metadata(section, "QUOTE")
    refs = _reference(section)
    if metadata:
        return {
            GateId.RAW_DECIMAL_ODDS: metadata,
            GateId.BOOKMAKER_PROVENANCE: metadata,
            GateId.REPRODUCIBLE_PROVIDER_MAPPING: metadata,
        }
    raw = _strict_true(section, ("raw_decimal_odds_capability",), "RAW_ODDS")
    if raw is None:
        raw = DerivedGate(GateStatus.PASS, "RAW_DECIMAL_BOOKMAKER_ODDS", refs)
    provenance = _strict_strings(
        section,
        ("bookmaker_identifier", "bookmaker_name_or_source"),
        "BOOKMAKER_PROVENANCE",
    )
    if provenance is None:
        provenance = DerivedGate(GateStatus.PASS, "BOOKMAKER_IDENTIFIED", refs)
    mapping = _strict_strings(
        section,
        (
            "provider_event_identifier",
            "provider_market_identifier",
            "provider_yes_selection_identifier",
            "provider_no_selection_identifier",
            "fixture_reference",
        ),
        "PROVIDER_MAPPING",
    )
    if mapping is None:
        mapping = DerivedGate(GateStatus.PASS, "PROVIDER_MAPPING_IDENTIFIED", refs)
    return {
        GateId.RAW_DECIMAL_ODDS: raw,
        GateId.BOOKMAKER_PROVENANCE: provenance,
        GateId.REPRODUCIBLE_PROVIDER_MAPPING: mapping,
    }


def _derive_timestamp(value: Mapping[str, Any]) -> DerivedGate:
    section = value["timestamp_evidence"]
    metadata = _section_metadata(section, "TIMESTAMP")
    if metadata:
        return metadata
    if any(
        field not in section
        for field in (
            "timestamp_source",
            "sample_timestamp",
            "download_time_distinct",
            "quote_ordering_reproducible",
        )
    ):
        return DerivedGate(GateStatus.UNKNOWN, "MISSING_TIMESTAMP_EVIDENCE")
    if section.get("timestamp_source") != "PROVIDER_QUOTE_OR_UPDATE":
        return DerivedGate(GateStatus.FAIL, "DOWNLOAD_TIME_IS_NOT_QUOTE_TIME")
    try:
        _parse_checked_at(section.get("sample_timestamp"))
    except QualificationExportError:
        return DerivedGate(GateStatus.FAIL, "INVALID_QUOTE_UPDATE_TIMESTAMP")
    if (
        section.get("download_time_distinct") is not True
        or section.get("quote_ordering_reproducible") is not True
    ):
        return DerivedGate(GateStatus.FAIL, "QUOTE_TIMESTAMP_PROTOCOL_CONFLICT")
    return DerivedGate(GateStatus.PASS, "QUOTE_UPDATE_TIMESTAMP_VALIDATED", _reference(section))


def _derive_snapshot(value: Mapping[str, Any]) -> DerivedGate:
    section = value["snapshot_evidence"]
    metadata = _section_metadata(section, "SNAPSHOT")
    if metadata:
        return metadata
    required = (
        "provider_identifier",
        "fixture_identifier",
        "market_id",
        "bookmaker_identifier",
        "yes_observed_at",
        "no_observed_at",
    )
    if any(field not in section for field in required):
        return DerivedGate(GateStatus.UNKNOWN, "MISSING_SNAPSHOT_COMPONENT")
    string_problem = _strict_strings(
        section,
        ("provider_identifier", "fixture_identifier", "bookmaker_identifier"),
        "SNAPSHOT",
    )
    if string_problem:
        return string_problem
    if "native_snapshot_id" in section and section.get("native_snapshot_id") is not None:
        native = section.get("native_snapshot_id")
        if not isinstance(native, str) or not native.strip():
            return DerivedGate(GateStatus.FAIL, "INVALID_NATIVE_SNAPSHOT_ID")
    result = validate_snapshot_identity(
        provider_identifier=section.get("provider_identifier"),
        fixture_identifier=section.get("fixture_identifier"),
        market_id=section.get("market_id"),
        bookmaker_identifier=section.get("bookmaker_identifier"),
        yes_observed_at=section.get("yes_observed_at"),
        no_observed_at=section.get("no_observed_at"),
        native_snapshot_id=section.get("native_snapshot_id"),
    )
    return DerivedGate(result.status, result.reason, _reference(section))


def _fixture_reference(value: Any) -> Optional[FixtureReference]:
    if not isinstance(value, Mapping):
        return None
    identifier_fields = (
        "provider_event_identifier",
        "home_participant_identifier",
        "home_participant_name",
        "away_participant_identifier",
        "away_participant_name",
        "fixture_status",
    )
    if _strict_strings(value, identifier_fields, "FIXTURE") is not None:
        return None
    return FixtureReference(
        provider_event_identifier=value["provider_event_identifier"].strip(),
        competition_identifier=(
            value.get("competition_identifier").strip()
            if isinstance(value.get("competition_identifier"), str)
            and value.get("competition_identifier").strip()
            else None
        ),
        season_identifier=(
            value.get("season_identifier").strip()
            if isinstance(value.get("season_identifier"), str)
            and value.get("season_identifier").strip()
            else None
        ),
        kickoff=value.get("kickoff"),
        home_participant_identifier=value["home_participant_identifier"].strip(),
        home_participant_name=value["home_participant_name"].strip(),
        away_participant_identifier=value["away_participant_identifier"].strip(),
        away_participant_name=value["away_participant_name"].strip(),
        neutral_venue=(
            value.get("neutral_venue")
            if isinstance(value.get("neutral_venue"), bool)
            else None
        ),
        fixture_status=value["fixture_status"].strip(),
    )


def _derive_fixture_mapping(value: Mapping[str, Any]) -> DerivedGate:
    section = value["fixture_mapping_evidence"]
    metadata = _section_metadata(section, "FIXTURE_MAPPING")
    if metadata:
        return metadata
    examples = section.get("examples")
    aggregate = section.get("aggregate_results")
    if not isinstance(examples, list) or not examples or not isinstance(aggregate, Mapping):
        return DerivedGate(GateStatus.UNKNOWN, "MISSING_FIXTURE_MAPPING_SAMPLE")
    results = []
    for example in examples:
        if not isinstance(example, Mapping):
            results.append(FixtureMappingStatus.UNAVAILABLE)
            continue
        provider = _fixture_reference(example.get("provider"))
        canonical = _fixture_reference(example.get("canonical"))
        if provider is None or canonical is None:
            results.append(FixtureMappingStatus.UNAVAILABLE)
            continue
        try:
            results.append(
                evaluate_fixture_mapping(
                    provider,
                    canonical,
                    fuzzy_only=example.get("fuzzy_only") is True,
                    kickoff_tolerance_seconds=KICKOFF_TOLERANCE_SECONDS,
                )
            )
        except SourceQualificationError:
            results.append(FixtureMappingStatus.CONFLICT)
    counts = Counter(result.value for result in results)
    expected_counts = {
        status.value: counts[status.value] for status in FixtureMappingStatus
    }
    if aggregate != expected_counts:
        return DerivedGate(GateStatus.FAIL, "FIXTURE_MAPPING_AGGREGATE_MISMATCH")
    if section.get("independent_fuzzy_name_qualification") is not False:
        return DerivedGate(GateStatus.FAIL, "FUZZY_MAPPING_CANNOT_QUALIFY")
    if any(result is not FixtureMappingStatus.EXACT for result in results):
        return DerivedGate(GateStatus.FAIL, "NON_EXACT_FIXTURE_MAPPING_PRESENT")
    return DerivedGate(GateStatus.PASS, "EXACT_FIXTURE_MAPPING_VALIDATED", _reference(section))


def _derive_historical(value: Mapping[str, Any]) -> dict[GateId, DerivedGate]:
    section = value["historical_retention_evidence"]
    metadata = _section_metadata(section, "HISTORICAL")
    refs = _reference(section)
    if metadata:
        retention = metadata
        coverage = metadata
    else:
        retention = _strict_true(
            section,
            (
                "retained_settled_history",
                "historical_observed_at",
                "bookmaker_identity",
                "exact_market_and_selections",
                "quote_change_ordering",
                "archived_or_exportable_snapshots",
            ),
            "HISTORICAL_RETENTION",
        ) or DerivedGate(GateStatus.PASS, "HISTORICAL_EVIDENCE_VALIDATED", refs)
        supplied_coverage = section.get("frozen_period_coverage")
        if supplied_coverage is None:
            coverage = DerivedGate(GateStatus.UNKNOWN, "MISSING_FROZEN_PERIOD_COVERAGE")
        elif supplied_coverage != FROZEN_FIXTURE_MARKET_DENOMINATOR:
            coverage = DerivedGate(GateStatus.FAIL, "FROZEN_PERIOD_COVERAGE_MISMATCH")
        elif sum(
            supplied_coverage[role]
            for role in ("CALIBRATION_FIT_OOF", "VALIDATION_SELECTION", "FINAL_TEST")
        ) != supplied_coverage["total"]:
            coverage = DerivedGate(GateStatus.FAIL, "FROZEN_PERIOD_COVERAGE_NOT_RECONCILED")
        else:
            coverage = DerivedGate(GateStatus.PASS, "FROZEN_PERIOD_COVERAGE_EXACT", refs)

    export = value["export_reproducibility_evidence"]
    export_metadata = _section_metadata(export, "EXPORT")
    reproducible = export_metadata or _strict_true(
        export,
        ("reproducible_export", "stable_fixture_market_identifiers", "deterministic_ordering"),
        "REPRODUCIBLE_EXPORT",
    ) or DerivedGate(GateStatus.PASS, "REPRODUCIBLE_EXPORT_VALIDATED", _reference(export))

    licensing = value["licensing_and_retention_evidence"]
    licensing_metadata = _section_metadata(licensing, "RETENTION_PERMISSION")
    permission = licensing_metadata or _strict_true(
        licensing,
        ("research_retention_permission", "retained_research_use_permitted"),
        "RESEARCH_RETENTION_PERMISSION",
    ) or DerivedGate(GateStatus.PASS, "RESEARCH_RETENTION_PERMISSION_VALIDATED", _reference(licensing))
    return {
        GateId.HISTORICAL_RETENTION: retention,
        GateId.FROZEN_PERIOD_COVERAGE: coverage,
        GateId.REPRODUCIBLE_EXPORT: reproducible,
        GateId.RESEARCH_RETENTION_PERMISSION: permission,
    }


def _derive_live(value: Mapping[str, Any]) -> dict[GateId, DerivedGate]:
    section = value["live_pricing_evidence"]
    metadata = _section_metadata(section, "LIVE_PRICING")
    refs = _reference(section)
    if metadata:
        return {
            GateId.CURRENT_MARKET_AVAILABILITY: metadata,
            GateId.FRESHNESS_ENFORCEABLE: metadata,
        }
    availability = _strict_true(
        section,
        (
            "current_exact_market_availability",
            "complete_yes_no_snapshots",
            "latest_eligible_snapshot_selection",
            "provider_mapping_reproducible",
            "timezone_aware_quote_updates",
        ),
        "LIVE_AVAILABILITY",
    ) or DerivedGate(GateStatus.PASS, "LIVE_MARKET_AVAILABILITY_VALIDATED", refs)
    if "maximum_quote_age_seconds" not in section:
        freshness = DerivedGate(GateStatus.UNKNOWN, "MISSING_LIVE_FRESHNESS_CONTRACT")
    elif section.get("maximum_quote_age_seconds") != 900:
        freshness = DerivedGate(GateStatus.FAIL, "LIVE_FRESHNESS_MUST_EQUAL_900_SECONDS")
    else:
        freshness = _strict_true(
            section,
            ("excludes_post_decision", "excludes_post_kickoff"),
            "LIVE_TEMPORAL_EXCLUSION",
        ) or DerivedGate(GateStatus.PASS, "LIVE_FRESHNESS_VALIDATED", refs)
    return {
        GateId.CURRENT_MARKET_AVAILABILITY: availability,
        GateId.FRESHNESS_ENFORCEABLE: freshness,
    }


def _derive_execution(value: Mapping[str, Any]) -> dict[GateId, DerivedGate]:
    section = value["execution_workflow_evidence"]
    metadata = _section_metadata(section, "EXECUTION")
    mapping = {
        GateId.EXACT_EXECUTION_SELECTION: "exact_fixture_market_outcome_selection",
        GateId.DETERMINISTIC_BETSLIP: "deterministic_betslip_construction",
        GateId.VALIDATED_QUOTE_PRICE_MATCH: "validated_price_matching",
        GateId.CHANGED_ODDS_DETECTION: "changed_odds_detection",
        GateId.SUSPENDED_SELECTION_DETECTION: "suspended_selection_detection",
        GateId.MISSING_MARKET_DETECTION: "missing_market_detection",
        GateId.EXPLICIT_USER_CONFIRMATION: "explicit_user_confirmation",
        GateId.PERMITTED_AUTOMATION: "permitted_automation",
    }
    results = {}
    for gate, field in mapping.items():
        if metadata:
            results[gate] = metadata
        elif field not in section:
            results[gate] = DerivedGate(GateStatus.UNKNOWN, f"MISSING_{field.upper()}")
        elif section.get(field) is not True:
            results[gate] = DerivedGate(GateStatus.FAIL, f"{field.upper()}_NOT_PROVEN")
        else:
            results[gate] = DerivedGate(GateStatus.PASS, f"{field.upper()}_VALIDATED", _reference(section))
    booking = value["booking_code_evidence"]
    booking_metadata = _section_metadata(booking, "BOOKING_CODE")
    if booking_metadata:
        results[GateId.BOOKING_CODE_SUPPORT] = booking_metadata
    else:
        capability = booking.get("capability_status")
        if capability == "AVAILABLE":
            results[GateId.BOOKING_CODE_SUPPORT] = DerivedGate(GateStatus.PASS, "BOOKING_CODE_AVAILABLE", _reference(booking))
        elif capability == "UNAVAILABLE":
            results[GateId.BOOKING_CODE_SUPPORT] = DerivedGate(GateStatus.NOT_APPLICABLE, "BOOKING_CODE_UNAVAILABLE", _reference(booking))
        elif capability in (None, "UNKNOWN"):
            results[GateId.BOOKING_CODE_SUPPORT] = DerivedGate(GateStatus.UNKNOWN, "BOOKING_CODE_UNKNOWN", _reference(booking))
        else:
            results[GateId.BOOKING_CODE_SUPPORT] = DerivedGate(GateStatus.FAIL, "INVALID_BOOKING_CODE_STATUS", _reference(booking))
    return results


def derive_structured_gates(value: Mapping[str, Any]) -> dict[GateId, DerivedGate]:
    derived = {gate: DerivedGate(GateStatus.UNKNOWN, "NO_STRUCTURED_EVIDENCE") for gate in GateId}
    derived.update(_derive_market_and_outcomes(value))
    derived.update(_derive_quote_fields(value))
    derived[GateId.QUOTE_OBSERVED_AT] = _derive_timestamp(value)
    derived[GateId.SAME_BOOKMAKER_SNAPSHOT] = _derive_snapshot(value)
    derived[GateId.FIXTURE_MAPPING] = _derive_fixture_mapping(value)
    derived.update(_derive_historical(value))
    derived.update(_derive_live(value))
    derived.update(_derive_execution(value))
    return derived


def build_effective_gates(
    declared: Mapping[GateId, GateEvidence],
    derived: Mapping[GateId, DerivedGate],
    *,
    evidence_paths: set[str],
    checked_at: datetime,
) -> tuple[dict[GateId, GateEvidence], dict[str, dict]]:
    effective = {}
    audit = {}
    for gate in GateId:
        declaration = declared.get(
            gate,
            GateEvidence(GateStatus.UNKNOWN, "NO_REVIEWER_DECLARATION", None, checked_at),
        )
        structured = derived[gate]
        if declaration.status is GateStatus.NOT_APPLICABLE:
            if gate in OPTIONAL_GATES:
                status = GateStatus.NOT_APPLICABLE
                reason = "OPTIONAL_CAPABILITY_NOT_APPLICABLE"
            else:
                status = GateStatus.FAIL
                reason = "NOT_APPLICABLE_NOT_ALLOWED"
        elif structured.status is GateStatus.FAIL:
            status = GateStatus.FAIL
            reason = structured.reason
        elif structured.status is GateStatus.UNKNOWN:
            status = GateStatus.UNKNOWN
            reason = (
                f"DECLARED_PASS_UNSUPPORTED:{structured.reason}"
                if declaration.status is GateStatus.PASS
                else structured.reason
            )
        elif structured.status is GateStatus.NOT_APPLICABLE:
            if gate in OPTIONAL_GATES:
                status = GateStatus.NOT_APPLICABLE
                reason = structured.reason
            else:
                status = GateStatus.FAIL
                reason = "NOT_APPLICABLE_NOT_ALLOWED"
        elif declaration.status is GateStatus.FAIL:
            status = GateStatus.FAIL
            reason = "REVIEWER_DECLARED_FAIL"
        elif declaration.status is not GateStatus.PASS:
            status = GateStatus.UNKNOWN
            reason = "REVIEWER_PASS_NOT_DECLARED"
        elif declaration.evidence_reference not in evidence_paths:
            status = GateStatus.FAIL
            reason = "DECLARED_EVIDENCE_REFERENCE_NOT_VERIFIED"
        elif not structured.evidence_references or any(
            reference not in evidence_paths for reference in structured.evidence_references
        ):
            status = GateStatus.FAIL
            reason = "STRUCTURED_EVIDENCE_REFERENCE_NOT_VERIFIED"
        elif declaration.evidence_reference not in structured.evidence_references:
            status = GateStatus.FAIL
            reason = "DECLARED_AND_STRUCTURED_EVIDENCE_REFERENCE_MISMATCH"
        else:
            status = GateStatus.PASS
            reason = "DECLARED_AND_STRUCTURED_EVIDENCE_VALIDATED"
        evidence_reference = declaration.evidence_reference
        effective[gate] = GateEvidence(status, reason, evidence_reference, checked_at)
        audit[gate.value] = {
            "declared": declaration.to_dict(),
            "derived": {
                "status": structured.status.value,
                "reason": structured.reason,
                "evidence_references": list(structured.evidence_references),
            },
            "effective": effective[gate].to_dict(),
        }
    return effective, audit


def qualify_candidate(
    value: Mapping[str, Any],
    *,
    evidence_root: Path,
    protocol: ValidatedProtocol,
    code_state: Mapping[str, Any],
    input_identity: Mapping[str, Any],
) -> dict:
    if not isinstance(value, Mapping) or value.get("schema_version") != SCHEMA_VERSION:
        raise QualificationExportError("Candidate schema_version must be 1")
    provider_identifier = _bounded_text(value.get("provider_identifier"), "provider_identifier")
    provider_name = _bounded_text(value.get("provider_name"), "provider_name")
    checked_at = _parse_checked_at(value.get("evidence_checked_at"))
    roles_value = value.get("candidate_roles")
    if not isinstance(roles_value, list) or not roles_value:
        raise QualificationExportError("candidate_roles must be a non-empty list")
    try:
        roles = tuple(SourceRole(role) for role in roles_value)
    except (TypeError, ValueError) as error:
        raise QualificationExportError("candidate_roles contains an unknown role") from error
    if len(set(roles)) != len(roles):
        raise QualificationExportError("candidate_roles must be unique")
    for section in REQUIRED_EVIDENCE_SECTIONS:
        if not isinstance(value.get(section), Mapping):
            raise QualificationExportError(f"{section} must be an object")
    declared_gates = _load_gates(value.get("gate_evidence"))
    evidence_identities = validate_evidence_files(
        value.get("evidence_files"), evidence_root=evidence_root
    )
    evidence_paths = {identity["relative_path"] for identity in evidence_identities}
    derived_gates = derive_structured_gates(value)
    effective_gates, gate_audit = build_effective_gates(
        declared_gates,
        derived_gates,
        evidence_paths=evidence_paths,
        checked_at=checked_at,
    )
    limitations = value.get("limitations")
    if not isinstance(limitations, list) or any(
        not isinstance(item, str) or not item.strip() for item in limitations
    ):
        raise QualificationExportError("limitations must be a list of non-empty strings")
    role_statuses = {
        role.value: qualify_mandatory_gates(role, effective_gates).value
        for role in roles
    }
    for role in SourceRole:
        role_statuses.setdefault(role.value, QualificationStatus.UNKNOWN.value)
    prospective = qualify_prospective_replay(effective_gates)
    unsupported = sorted(
        gate.value
        for gate, result in effective_gates.items()
        if result.status is GateStatus.FAIL
    )
    unknown = sorted(
        gate.value
        for gate in GateId
        if effective_gates[gate].status is GateStatus.UNKNOWN
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "provider_identifier": provider_identifier,
        "provider_name": provider_name,
        "candidate_roles": sorted(role.value for role in roles),
        "evidence_checked_at": checked_at.isoformat().replace("+00:00", "Z"),
        "qualification": {
            "historical_status": role_statuses[SourceRole.HISTORICAL_RESEARCH_SOURCE.value],
            "live_pricing_status": role_statuses[SourceRole.LIVE_PRICING_SOURCE.value],
            "execution_bookmaker_status": role_statuses[SourceRole.EXECUTION_BOOKMAKER.value],
            "prospective_replay_status": prospective.value,
        },
        "gate_results": gate_audit,
        "unsupported_capabilities": unsupported,
        "unknown_capabilities": unknown,
        "limitations": sorted(item.strip()[:500] for item in limitations),
        "evidence_files": evidence_identities,
        "input_identity": dict(input_identity),
        "protocol": {
            "dataset_name": protocol.value.get("dataset_name"),
            "schema_version": protocol.value.get("schema_version"),
            "byte_size": protocol.byte_size,
            "sha256": protocol.sha256,
        },
        "decision_protocol": dict(protocol.value["decision_protocol"]),
        "holdout_governance": {
            **dict(protocol.value["holdout_governance"]),
            "production_approval_authorized": False,
        },
        "market_registry": canonical_market_registry_snapshot(),
        "market_statuses": {
            market.value: MODEL_STATUS_REGISTRY[market].status.value
            for market in sorted(MarketId, key=lambda item: item.value)
        },
        "generator": {
            "git_head_sha": code_state.get("evidence_git_head_sha"),
            "tracked_worktree_clean": code_state.get("tracked_worktree_clean"),
        },
        "no_production_approval": (
            "Stage 5B1 qualifies evidence capabilities only; it authorizes no odds "
            "integration, value decision, execution, booking code, or bet."
        ),
    }
    lowered_keys = {str(key).lower() for key in _walk_keys(report)}
    if FORBIDDEN_FIELDS.intersection(lowered_keys):
        raise QualificationExportError("Qualification output contains a forbidden field")
    return report


def _walk_keys(value: Any):
    if isinstance(value, Mapping):
        for key, nested in value.items():
            yield key
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_keys(nested)


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
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


def write_report(path: Path, report: Mapping, *, force: bool = False) -> None:
    if path.exists() and not force:
        raise QualificationExportError("Qualification output already exists; use --force")
    _atomic_write(path, _canonical_json_bytes(report))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Qualify a Win Either Half pricing source from offline evidence."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--check", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        candidate, candidate_bytes = _read_json(args.input, "Candidate capability evidence")
        protocol_value, protocol_bytes = _read_json(args.protocol, "Qualification protocol")
        protocol = validate_protocol_contract(protocol_value, protocol_bytes)
        code_state = get_code_state(REPOSITORY_ROOT)
        if not code_state.get("tracked_worktree_clean"):
            raise QualificationExportError("Tracked worktree is dirty")
        report = qualify_candidate(
            candidate,
            evidence_root=args.evidence_root,
            protocol=protocol,
            code_state=code_state,
            input_identity={
                "byte_size": len(candidate_bytes),
                "sha256": _sha256(candidate_bytes),
            },
        )
        content = _canonical_json_bytes(report)
        if args.check is not None:
            stored, _ = _read_json(args.check, "Stored qualification report")
            if stored != report:
                raise QualificationExportError("Qualification report differs")
            print("Stage 5B1 source qualification verified")
            return 0
        write_report(args.output, report, force=args.force)
        print(
            "Stage 5B1 source qualification generated: "
            f"provider={report['provider_identifier']}"
        )
        return 0
    except (QualificationExportError, SourceQualificationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
