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
FROZEN_MARKET_DENOMINATOR = {
    market.value: {
        "CALIBRATION_FIT_OOF": 10635,
        "VALIDATION_SELECTION": 3476,
        "FINAL_TEST": 4048,
        "total": 18159,
    }
    for market in PERMITTED_MARKETS
}
CLAIM_CAPABILITY_ALLOWLIST = {
    GateId.EXACT_MARKET_SEMANTICS: frozenset({"MARKET_SEMANTICS"}),
    GateId.EXACT_YES_NO_STRUCTURE: frozenset(
        {"MARKET_SEMANTICS", "OUTCOME_STRUCTURE", "QUOTE_SCHEMA"}
    ),
    GateId.RAW_DECIMAL_ODDS: frozenset({"QUOTE_SCHEMA"}),
    GateId.BOOKMAKER_PROVENANCE: frozenset({"QUOTE_SCHEMA"}),
    GateId.QUOTE_OBSERVED_AT: frozenset({"TIMESTAMP"}),
    GateId.SAME_BOOKMAKER_SNAPSHOT: frozenset({"SNAPSHOT"}),
    GateId.FIXTURE_MAPPING: frozenset({"FIXTURE_MAPPING"}),
    GateId.REPRODUCIBLE_EXPORT: frozenset({"REPRODUCIBLE_EXPORT"}),
    GateId.HISTORICAL_RETENTION: frozenset({"HISTORICAL_RETENTION"}),
    GateId.FROZEN_PERIOD_COVERAGE: frozenset({"FROZEN_COVERAGE"}),
    GateId.RESEARCH_RETENTION_PERMISSION: frozenset({"RESEARCH_PERMISSION"}),
    GateId.CURRENT_MARKET_AVAILABILITY: frozenset({"LIVE_AVAILABILITY"}),
    GateId.FRESHNESS_ENFORCEABLE: frozenset(
        {"LIVE_AVAILABILITY", "TIMESTAMP"}
    ),
    GateId.REPRODUCIBLE_PROVIDER_MAPPING: frozenset(
        {"QUOTE_SCHEMA", "LIVE_AVAILABILITY"}
    ),
    GateId.PERMITTED_AUTOMATION: frozenset({"EXECUTION_SAFETY"}),
    GateId.EXACT_EXECUTION_SELECTION: frozenset({"EXECUTION_SAFETY"}),
    GateId.DETERMINISTIC_BETSLIP: frozenset({"EXECUTION_SAFETY"}),
    GateId.VALIDATED_QUOTE_PRICE_MATCH: frozenset({"EXECUTION_SAFETY"}),
    GateId.CHANGED_ODDS_DETECTION: frozenset({"EXECUTION_SAFETY"}),
    GateId.SUSPENDED_SELECTION_DETECTION: frozenset({"EXECUTION_SAFETY"}),
    GateId.MISSING_MARKET_DETECTION: frozenset({"EXECUTION_SAFETY"}),
    GateId.EXPLICIT_USER_CONFIRMATION: frozenset({"EXECUTION_SAFETY"}),
    GateId.BOOKING_CODE_SUPPORT: frozenset({"BOOKING_CODE"}),
}
PERMITTED_CLAIM_CAPABILITIES = frozenset(
    capability
    for capabilities in CLAIM_CAPABILITY_ALLOWLIST.values()
    for capability in capabilities
)
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
    evidence_claim_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceClaim:
    claim_id: str
    provider_identifier: str
    evidence_file_path: str
    document_title: str
    source_reference: str
    capability_identifier: str
    capability_statement: str
    retrieval_timestamp: datetime
    reviewer_checked_at: datetime
    reviewer_conclusion: GateStatus

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "provider_identifier": self.provider_identifier,
            "evidence_file_path": self.evidence_file_path,
            "document_title": self.document_title,
            "source_reference": self.source_reference,
            "capability_identifier": self.capability_identifier,
            "capability_statement": self.capability_statement,
            "retrieval_timestamp": self.retrieval_timestamp.isoformat().replace(
                "+00:00", "Z"
            ),
            "reviewer_checked_at": self.reviewer_checked_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "reviewer_conclusion": self.reviewer_conclusion.value,
        }


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
    expected_claim_contract = {
        "required_fields": [
            "claim_id",
            "provider_identifier",
            "evidence_file_path",
            "document_title",
            "source_reference",
            "capability_identifier",
            "capability_statement",
            "retrieval_timestamp",
            "reviewer_checked_at",
            "reviewer_conclusion",
        ],
        "reviewer_conclusions": ["PASS", "FAIL", "UNKNOWN"],
        "gate_capability_allowlist": {
            gate.value: sorted(capabilities)
            for gate, capabilities in sorted(
                CLAIM_CAPABILITY_ALLOWLIST.items(), key=lambda item: item[0].value
            )
        },
    }
    expected_market_specific = {
        "required_markets": sorted(market.value for market in PERMITTED_MARKETS),
        "quote_mapping_records_per_market": 1,
        "snapshot_samples_per_market": 1,
        "live_capability_records_per_market": 1,
        "historical_coverage_records_per_market": 1,
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
        (
            value.get("frozen_fixture_market_denominator_by_market"),
            FROZEN_MARKET_DENOMINATOR,
            "per-market frozen denominator",
        ),
        (
            value.get("market_specific_evidence_contract"),
            expected_market_specific,
            "market-specific evidence contract",
        ),
        (
            value.get("evidence_claim_contract"),
            expected_claim_contract,
            "evidence claim contract",
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


def _claim_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualificationExportError(f"Evidence claim {field} is required")
    return value.strip()[:500]


def load_evidence_claims(
    records: Any,
    *,
    provider_identifier: str,
    verified_evidence_paths: set[str],
) -> dict[str, EvidenceClaim]:
    """Validate typed claims independently from their verified file identities."""
    if not isinstance(records, list):
        raise QualificationExportError("evidence_claims must be a list")
    claims: dict[str, EvidenceClaim] = {}
    for row in records:
        if not isinstance(row, Mapping):
            raise QualificationExportError("Evidence claim row must be an object")
        claim_id = _claim_text(row.get("claim_id"), "claim_id")
        if claim_id in claims:
            raise QualificationExportError("Evidence claim IDs must be unique")
        claim_provider = _claim_text(
            row.get("provider_identifier"), "provider_identifier"
        )
        if claim_provider != provider_identifier:
            raise QualificationExportError(
                "Evidence claim provider does not match candidate"
            )
        evidence_path = _claim_text(
            row.get("evidence_file_path"), "evidence_file_path"
        )
        if evidence_path not in verified_evidence_paths:
            raise QualificationExportError(
                "Evidence claim does not identify a verified evidence file"
            )
        capability = _claim_text(
            row.get("capability_identifier"), "capability_identifier"
        )
        if capability not in PERMITTED_CLAIM_CAPABILITIES:
            raise QualificationExportError(
                "Evidence claim capability_identifier is not permitted"
            )
        try:
            conclusion = GateStatus(row.get("reviewer_conclusion"))
        except (TypeError, ValueError) as error:
            raise QualificationExportError(
                "Evidence claim reviewer_conclusion is invalid"
            ) from error
        if conclusion is GateStatus.NOT_APPLICABLE:
            raise QualificationExportError(
                "Evidence claim reviewer_conclusion cannot be NOT_APPLICABLE"
            )
        claims[claim_id] = EvidenceClaim(
            claim_id=claim_id,
            provider_identifier=claim_provider,
            evidence_file_path=evidence_path,
            document_title=_claim_text(row.get("document_title"), "document_title"),
            source_reference=_claim_text(row.get("source_reference"), "source_reference"),
            capability_identifier=capability,
            capability_statement=_claim_text(
                row.get("capability_statement"), "capability_statement"
            ),
            retrieval_timestamp=_parse_checked_at(row.get("retrieval_timestamp")),
            reviewer_checked_at=_parse_checked_at(row.get("reviewer_checked_at")),
            reviewer_conclusion=conclusion,
        )
    return dict(sorted(claims.items()))


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
    claim_ids = section.get("claim_ids")
    checked_at = section.get("checked_at")
    if claim_ids is None or checked_at is None:
        return DerivedGate(GateStatus.UNKNOWN, f"MISSING_{label}_DOCUMENTATION")
    if not isinstance(claim_ids, list) or any(
        not isinstance(claim_id, str) or not claim_id.strip()
        for claim_id in claim_ids
    ):
        return DerivedGate(GateStatus.FAIL, f"INVALID_{label}_EVIDENCE_CLAIMS")
    if len(set(claim_ids)) != len(claim_ids):
        return DerivedGate(GateStatus.FAIL, f"DUPLICATE_{label}_EVIDENCE_CLAIMS")
    if not claim_ids:
        return DerivedGate(GateStatus.UNKNOWN, f"MISSING_{label}_EVIDENCE_CLAIMS")
    try:
        _parse_checked_at(checked_at)
    except QualificationExportError:
        return DerivedGate(GateStatus.FAIL, f"INVALID_{label}_CHECKED_AT")
    return None


def _claim_ids(
    section: Mapping[str, Any], field: str = "claim_ids"
) -> tuple[str, ...]:
    values = section.get(field)
    if not isinstance(values, list):
        return ()
    return tuple(
        sorted(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        )
    )


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
    claim_ids = tuple(
        sorted({claim_id for value in values for claim_id in value.evidence_claim_ids})
    )
    failures = [value.reason for value in values if value.status is GateStatus.FAIL]
    if failures:
        return DerivedGate(GateStatus.FAIL, ";".join(sorted(failures)), claim_ids)
    unknown = [value.reason for value in values if value.status is GateStatus.UNKNOWN]
    if unknown:
        return DerivedGate(GateStatus.UNKNOWN, ";".join(sorted(unknown)), claim_ids)
    return DerivedGate(GateStatus.PASS, "STRUCTURED_EVIDENCE_VALIDATED", claim_ids)


def _market_rows(
    rows: Any, label: str
) -> tuple[dict[MarketId, Mapping[str, Any]], list[DerivedGate]]:
    indexed: dict[MarketId, Mapping[str, Any]] = {}
    problems: list[DerivedGate] = []
    if not isinstance(rows, list) or not rows:
        return indexed, [DerivedGate(GateStatus.UNKNOWN, f"MISSING_{label}_RECORDS")]
    for row in rows:
        if not isinstance(row, Mapping):
            problems.append(DerivedGate(GateStatus.FAIL, f"INVALID_{label}_RECORD"))
            continue
        try:
            market = MarketId(row.get("market_id"))
        except (TypeError, ValueError):
            problems.append(DerivedGate(GateStatus.FAIL, f"UNKNOWN_{label}_MARKET"))
            continue
        if market not in PERMITTED_MARKETS:
            problems.append(DerivedGate(GateStatus.FAIL, f"EXTRA_{label}_MARKET"))
            continue
        if market in indexed:
            problems.append(DerivedGate(GateStatus.FAIL, f"DUPLICATE_{label}_MARKET"))
            continue
        indexed[market] = row
    return indexed, problems


def _missing_market_result(label: str) -> DerivedGate:
    return DerivedGate(GateStatus.UNKNOWN, f"MISSING_{label}_FOR_CANONICAL_MARKET")


def _derive_market_and_outcomes(
    value: Mapping[str, Any],
) -> tuple[dict[GateId, DerivedGate], dict[MarketId, DerivedGate], dict[MarketId, Mapping[str, Any]]]:
    section = value["market_semantics_evidence"]
    section_problem = _section_metadata(section, "MARKET_SEMANTICS")
    indexed, indexing_problems = _market_rows(section.get("markets"), "SEMANTICS")
    per_market: dict[MarketId, DerivedGate] = {}
    for market in PERMITTED_MARKETS:
        row = indexed.get(market)
        if section_problem:
            per_market[market] = section_problem
        elif row is None:
            per_market[market] = _missing_market_result("SEMANTICS")
        elif row.get("checked_at") is None:
            per_market[market] = DerivedGate(
                GateStatus.UNKNOWN, "MISSING_MARKET_CHECKED_AT", _claim_ids(row)
            )
        else:
            try:
                result = validate_market_semantics(row)
            except SourceQualificationError:
                per_market[market] = DerivedGate(
                    GateStatus.FAIL, "INVALID_MARKET_CHECKED_AT", _claim_ids(row)
                )
            else:
                per_market[market] = DerivedGate(
                    result.status,
                    result.reason,
                    tuple(sorted(set(_claim_ids(section) + result.evidence_claim_ids))),
                )
    semantics = _merge_derived(*per_market.values(), *indexing_problems)

    outcome = value["outcome_evidence"]
    outcome_problem = _section_metadata(outcome, "OUTCOME")
    if outcome_problem:
        outcome_result = outcome_problem
    elif outcome.get("canonical_outcome_ids") != ["YES", "NO"]:
        outcome_result = DerivedGate(
            GateStatus.FAIL, "YES_NO_IDENTIFIERS_MISMATCH", _claim_ids(outcome)
        )
    else:
        outcome_result = DerivedGate(
            GateStatus.PASS, "EXACT_YES_NO_STRUCTURE", _claim_ids(outcome)
        )
    return (
        {
            GateId.EXACT_MARKET_SEMANTICS: semantics,
            GateId.EXACT_YES_NO_STRUCTURE: _merge_derived(
                semantics, outcome_result
            ),
        },
        per_market,
        indexed,
    )


def _derive_quote_fields(
    value: Mapping[str, Any],
    semantic_rows: Mapping[MarketId, Mapping[str, Any]],
) -> tuple[dict[GateId, DerivedGate], dict[MarketId, DerivedGate], dict[MarketId, Mapping[str, Any]]]:
    section = value["quote_field_evidence"]
    section_problem = _section_metadata(section, "QUOTE")
    indexed, indexing_problems = _market_rows(section.get("mappings"), "QUOTE_MAPPING")
    per_market: dict[MarketId, DerivedGate] = {}
    required_strings = (
        "provider_market_identifier",
        "provider_market_name",
        "provider_yes_selection_identifier",
        "provider_yes_selection_label",
        "provider_no_selection_identifier",
        "provider_no_selection_label",
        "bookmaker_identifier",
        "bookmaker_name_or_source",
        "provider_event_identifier",
        "fixture_reference",
    )
    for market in PERMITTED_MARKETS:
        row = indexed.get(market)
        semantics = semantic_rows.get(market)
        if section_problem:
            per_market[market] = section_problem
        elif row is None:
            per_market[market] = _missing_market_result("QUOTE_MAPPING")
        elif (row_problem := _section_metadata(row, "QUOTE_MAPPING")) is not None:
            per_market[market] = row_problem
        elif (string_problem := _strict_strings(row, required_strings, "QUOTE_MAPPING")) is not None:
            per_market[market] = string_problem
        elif row.get("raw_decimal_odds_capability") is not True:
            per_market[market] = DerivedGate(
                GateStatus.FAIL,
                "RAW_DECIMAL_ODDS_CAPABILITY_NOT_PROVEN",
                _claim_ids(row),
            )
        elif semantics is None:
            per_market[market] = DerivedGate(
                GateStatus.UNKNOWN, "MISSING_CORRESPONDING_SEMANTIC_RECORD", _claim_ids(row)
            )
        elif any(
            row.get(field) != semantics.get(field)
            for field in (
                "provider_market_identifier",
                "provider_market_name",
                "provider_yes_selection_identifier",
                "provider_yes_selection_label",
                "provider_no_selection_identifier",
                "provider_no_selection_label",
            )
        ):
            per_market[market] = DerivedGate(
                GateStatus.FAIL, "QUOTE_MAPPING_SEMANTICS_MISMATCH", _claim_ids(row)
            )
        else:
            per_market[market] = DerivedGate(
                GateStatus.PASS,
                "MARKET_SPECIFIC_QUOTE_MAPPING_VALIDATED",
                tuple(sorted(set(_claim_ids(section) + _claim_ids(row)))),
            )
    complete_rows = [indexed.get(market) for market in PERMITTED_MARKETS]
    if all(row is not None for row in complete_rows):
        provider_market_ids = [row.get("provider_market_identifier") for row in complete_rows]
        if (
            len(set(provider_market_ids)) != len(provider_market_ids)
            and section.get("shared_provider_market_identifier_proven_for_both_subjects")
            is not True
        ):
            indexing_problems.append(
                DerivedGate(GateStatus.FAIL, "UNPROVEN_SHARED_PROVIDER_MARKET_IDENTIFIER")
            )
        selection_ids = [
            row.get(field)
            for row in complete_rows
            for field in (
                "provider_yes_selection_identifier",
                "provider_no_selection_identifier",
            )
        ]
        if len(set(selection_ids)) != len(selection_ids):
            indexing_problems.append(
                DerivedGate(GateStatus.FAIL, "CROSS_MARKET_SELECTION_IDENTIFIER_REUSE")
            )
    overall = _merge_derived(*per_market.values(), *indexing_problems)
    return (
        {
            GateId.RAW_DECIMAL_ODDS: overall,
            GateId.BOOKMAKER_PROVENANCE: overall,
            GateId.REPRODUCIBLE_PROVIDER_MAPPING: overall,
        },
        per_market,
        indexed,
    )


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
    return DerivedGate(GateStatus.PASS, "QUOTE_UPDATE_TIMESTAMP_VALIDATED", _claim_ids(section))


def _derive_snapshot(
    value: Mapping[str, Any],
    quote_rows: Mapping[MarketId, Mapping[str, Any]],
    provider_identifier: str,
) -> tuple[DerivedGate, dict[MarketId, DerivedGate], dict[MarketId, dict]]:
    section = value["snapshot_evidence"]
    section_problem = _section_metadata(section, "SNAPSHOT")
    indexed, indexing_problems = _market_rows(section.get("samples"), "SNAPSHOT")
    per_market: dict[MarketId, DerivedGate] = {}
    audit: dict[MarketId, dict] = {}
    for market in PERMITTED_MARKETS:
        row = indexed.get(market)
        quote = quote_rows.get(market)
        audit[market] = {
            "provider_identifier": row.get("provider_identifier") if row else None,
            "fixture_identifier": row.get("fixture_identifier") if row else None,
            "market_id": market.value,
            "bookmaker_identifier": row.get("bookmaker_identifier") if row else None,
            "observed_at": row.get("yes_observed_at") if row else None,
            "snapshot_identifier": None,
            "snapshot_identifier_derived": None,
        }
        if section_problem:
            per_market[market] = section_problem
        elif row is None:
            per_market[market] = _missing_market_result("SNAPSHOT")
        elif (row_problem := _section_metadata(row, "SNAPSHOT")) is not None:
            per_market[market] = row_problem
        elif row.get("provider_identifier") != provider_identifier:
            per_market[market] = DerivedGate(
                GateStatus.FAIL, "SNAPSHOT_PROVIDER_MISMATCH", _claim_ids(row)
            )
        elif row.get("outcome_identifiers") != ["YES", "NO"]:
            per_market[market] = DerivedGate(
                GateStatus.FAIL, "SNAPSHOT_YES_NO_RELATIONSHIP_INVALID", _claim_ids(row)
            )
        elif quote is None:
            per_market[market] = DerivedGate(
                GateStatus.UNKNOWN, "MISSING_CORRESPONDING_QUOTE_MAPPING", _claim_ids(row)
            )
        elif any(
            row.get(field) != quote.get(field)
            for field in (
                "provider_yes_selection_identifier",
                "provider_no_selection_identifier",
                "bookmaker_identifier",
            )
        ):
            per_market[market] = DerivedGate(
                GateStatus.FAIL, "SNAPSHOT_QUOTE_MAPPING_MISMATCH", _claim_ids(row)
            )
        elif row.get("native_snapshot_id") is not None and (
            not isinstance(row.get("native_snapshot_id"), str)
            or not row.get("native_snapshot_id").strip()
        ):
            per_market[market] = DerivedGate(
                GateStatus.FAIL, "INVALID_NATIVE_SNAPSHOT_ID", _claim_ids(row)
            )
        else:
            result = validate_snapshot_identity(
                provider_identifier=row.get("provider_identifier"),
                fixture_identifier=row.get("fixture_identifier"),
                market_id=row.get("market_id"),
                bookmaker_identifier=row.get("bookmaker_identifier"),
                yes_observed_at=row.get("yes_observed_at"),
                no_observed_at=row.get("no_observed_at"),
                native_snapshot_id=row.get("native_snapshot_id"),
            )
            per_market[market] = DerivedGate(
                result.status,
                result.reason,
                tuple(sorted(set(_claim_ids(section) + _claim_ids(row)))),
            )
            audit[market]["snapshot_identifier"] = result.snapshot_identifier
            audit[market]["snapshot_identifier_derived"] = result.derived
    return (
        _merge_derived(*per_market.values(), *indexing_problems),
        per_market,
        audit,
    )


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
    return DerivedGate(GateStatus.PASS, "EXACT_FIXTURE_MAPPING_VALIDATED", _claim_ids(section))


def _derive_historical(
    value: Mapping[str, Any],
) -> tuple[dict[GateId, DerivedGate], dict[MarketId, DerivedGate]]:
    section = value["historical_retention_evidence"]
    section_problem = _section_metadata(section, "HISTORICAL")
    indexed, indexing_problems = _market_rows(section.get("markets"), "HISTORICAL")
    per_market: dict[MarketId, DerivedGate] = {}
    retention_results: list[DerivedGate] = []
    coverage_results: list[DerivedGate] = []
    for market in PERMITTED_MARKETS:
        row = indexed.get(market)
        if section_problem:
            per_market[market] = section_problem
            retention_results.append(section_problem)
            coverage_results.append(section_problem)
        elif row is None:
            per_market[market] = _missing_market_result("HISTORICAL")
            retention_results.append(per_market[market])
            coverage_results.append(per_market[market])
        elif (row_problem := _section_metadata(row, "HISTORICAL")) is not None:
            per_market[market] = row_problem
            retention_results.append(row_problem)
            coverage_results.append(row_problem)
        else:
            capability = _strict_true(
                row,
                (
                    "retained_settled_history",
                    "historical_observed_at",
                    "bookmaker_identity",
                    "exact_market_and_selections",
                    "quote_change_ordering",
                    "archived_or_exportable_snapshots",
                ),
                "HISTORICAL_RETENTION",
            ) or DerivedGate(
                GateStatus.PASS,
                "HISTORICAL_MARKET_EVIDENCE_VALIDATED",
                _claim_ids(row, "retention_claim_ids"),
            )
            supplied = row.get("frozen_period_coverage")
            if supplied is None:
                coverage = DerivedGate(
                    GateStatus.UNKNOWN,
                    "MISSING_MARKET_FROZEN_PERIOD_COVERAGE",
                    _claim_ids(row, "coverage_claim_ids"),
                )
            elif supplied != FROZEN_MARKET_DENOMINATOR[market.value]:
                coverage = DerivedGate(
                    GateStatus.FAIL,
                    "MARKET_FROZEN_PERIOD_COVERAGE_MISMATCH",
                    _claim_ids(row, "coverage_claim_ids"),
                )
            else:
                coverage = DerivedGate(
                    GateStatus.PASS,
                    "MARKET_FROZEN_PERIOD_COVERAGE_EXACT",
                    _claim_ids(row, "coverage_claim_ids"),
                )
            coverage_results.append(coverage)
            retention_results.append(capability)
            per_market[market] = _merge_derived(capability, coverage)
    combined = section.get("combined_frozen_period_coverage")
    if combined is None:
        combined_result = DerivedGate(
            GateStatus.UNKNOWN, "MISSING_COMBINED_FROZEN_PERIOD_COVERAGE"
        )
    elif combined != FROZEN_FIXTURE_MARKET_DENOMINATOR:
        combined_result = DerivedGate(
            GateStatus.FAIL, "COMBINED_FROZEN_PERIOD_COVERAGE_MISMATCH"
        )
    elif all(
        indexed.get(market) is not None
        and isinstance(indexed[market].get("frozen_period_coverage"), Mapping)
        for market in PERMITTED_MARKETS
    ) and any(
        sum(
            indexed[market]["frozen_period_coverage"].get(key, -1)
            for market in PERMITTED_MARKETS
        )
        != combined[key]
        for key in (
            "CALIBRATION_FIT_OOF",
            "VALIDATION_SELECTION",
            "FINAL_TEST",
            "total",
        )
    ):
        combined_result = DerivedGate(
            GateStatus.FAIL, "MARKET_AND_COMBINED_COVERAGE_NOT_RECONCILED"
        )
    else:
        combined_result = DerivedGate(
            GateStatus.PASS,
            "COMBINED_FROZEN_PERIOD_COVERAGE_EXACT",
            _claim_ids(section, "coverage_claim_ids"),
        )
    retention = _merge_derived(*retention_results, *indexing_problems)
    coverage = _merge_derived(*coverage_results, combined_result, *indexing_problems)

    export = value["export_reproducibility_evidence"]
    export_metadata = _section_metadata(export, "EXPORT")
    reproducible = export_metadata or _strict_true(
        export,
        ("reproducible_export", "stable_fixture_market_identifiers", "deterministic_ordering"),
        "REPRODUCIBLE_EXPORT",
    ) or DerivedGate(GateStatus.PASS, "REPRODUCIBLE_EXPORT_VALIDATED", _claim_ids(export))

    licensing = value["licensing_and_retention_evidence"]
    licensing_metadata = _section_metadata(licensing, "RETENTION_PERMISSION")
    permission = licensing_metadata or _strict_true(
        licensing,
        ("research_retention_permission", "retained_research_use_permitted"),
        "RESEARCH_RETENTION_PERMISSION",
    ) or DerivedGate(GateStatus.PASS, "RESEARCH_RETENTION_PERMISSION_VALIDATED", _claim_ids(licensing))
    return (
        {
            GateId.HISTORICAL_RETENTION: retention,
            GateId.FROZEN_PERIOD_COVERAGE: coverage,
            GateId.REPRODUCIBLE_EXPORT: reproducible,
            GateId.RESEARCH_RETENTION_PERMISSION: permission,
        },
        per_market,
    )


def _derive_live(
    value: Mapping[str, Any],
) -> tuple[dict[GateId, DerivedGate], dict[MarketId, DerivedGate]]:
    section = value["live_pricing_evidence"]
    section_problem = _section_metadata(section, "LIVE_PRICING")
    indexed, indexing_problems = _market_rows(section.get("markets"), "LIVE")
    per_market: dict[MarketId, DerivedGate] = {}
    availability_results: list[DerivedGate] = []
    freshness_results: list[DerivedGate] = []
    for market in PERMITTED_MARKETS:
        row = indexed.get(market)
        if section_problem:
            availability = section_problem
            freshness = section_problem
        elif row is None:
            availability = _missing_market_result("LIVE")
            freshness = availability
        elif (row_problem := _section_metadata(row, "LIVE")) is not None:
            availability = row_problem
            freshness = row_problem
        else:
            availability = _strict_true(
                row,
                (
                    "current_exact_market_availability",
                    "complete_yes_no_snapshots",
                    "latest_eligible_snapshot_selection",
                    "provider_mapping_reproducible",
                    "timezone_aware_quote_updates",
                ),
                "LIVE_AVAILABILITY",
            ) or DerivedGate(
                GateStatus.PASS,
                "LIVE_MARKET_AVAILABILITY_VALIDATED",
                tuple(sorted(set(_claim_ids(section) + _claim_ids(row)))),
            )
            if "maximum_quote_age_seconds" not in row:
                freshness = DerivedGate(
                    GateStatus.UNKNOWN, "MISSING_LIVE_FRESHNESS_CONTRACT", _claim_ids(row)
                )
            elif row.get("maximum_quote_age_seconds") != 900:
                freshness = DerivedGate(
                    GateStatus.FAIL,
                    "LIVE_FRESHNESS_MUST_EQUAL_900_SECONDS",
                    _claim_ids(row),
                )
            else:
                freshness = _strict_true(
                    row,
                    ("excludes_post_decision", "excludes_post_kickoff"),
                    "LIVE_TEMPORAL_EXCLUSION",
                ) or DerivedGate(
                    GateStatus.PASS, "LIVE_FRESHNESS_VALIDATED", _claim_ids(row)
                )
        availability_results.append(availability)
        freshness_results.append(freshness)
        per_market[market] = _merge_derived(availability, freshness)
    return (
        {
            GateId.CURRENT_MARKET_AVAILABILITY: _merge_derived(
                *availability_results, *indexing_problems
            ),
            GateId.FRESHNESS_ENFORCEABLE: _merge_derived(
                *freshness_results, *indexing_problems
            ),
        },
        per_market,
    )


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
            results[gate] = DerivedGate(GateStatus.PASS, f"{field.upper()}_VALIDATED", _claim_ids(section))
    booking = value["booking_code_evidence"]
    booking_metadata = _section_metadata(booking, "BOOKING_CODE")
    if booking_metadata:
        results[GateId.BOOKING_CODE_SUPPORT] = booking_metadata
    else:
        capability = booking.get("capability_status")
        if capability == "AVAILABLE":
            results[GateId.BOOKING_CODE_SUPPORT] = DerivedGate(GateStatus.PASS, "BOOKING_CODE_AVAILABLE", _claim_ids(booking))
        elif capability == "UNAVAILABLE":
            results[GateId.BOOKING_CODE_SUPPORT] = DerivedGate(GateStatus.NOT_APPLICABLE, "BOOKING_CODE_UNAVAILABLE", _claim_ids(booking))
        elif capability in (None, "UNKNOWN"):
            results[GateId.BOOKING_CODE_SUPPORT] = DerivedGate(GateStatus.UNKNOWN, "BOOKING_CODE_UNKNOWN", _claim_ids(booking))
        else:
            results[GateId.BOOKING_CODE_SUPPORT] = DerivedGate(GateStatus.FAIL, "INVALID_BOOKING_CODE_STATUS", _claim_ids(booking))
    return results


def derive_structured_gates(
    value: Mapping[str, Any],
    provider_identifier: str,
    claims: Mapping[str, EvidenceClaim],
) -> tuple[dict[GateId, DerivedGate], dict[str, dict]]:
    derived = {
        gate: DerivedGate(GateStatus.UNKNOWN, "NO_STRUCTURED_EVIDENCE")
        for gate in GateId
    }
    semantics_gates, semantics_market, semantic_rows = _derive_market_and_outcomes(value)
    quote_gates, quote_market, quote_rows = _derive_quote_fields(value, semantic_rows)
    snapshot_gate, snapshot_market, snapshot_audit = _derive_snapshot(
        value, quote_rows, provider_identifier
    )
    historical_gates, historical_market = _derive_historical(value)
    live_gates, live_market = _derive_live(value)
    historical_rows, _ = _market_rows(
        value["historical_retention_evidence"].get("markets"), "HISTORICAL"
    )
    live_rows, _ = _market_rows(
        value["live_pricing_evidence"].get("markets"), "LIVE"
    )
    derived.update(semantics_gates)
    derived.update(quote_gates)
    derived[GateId.EXACT_YES_NO_STRUCTURE] = _merge_derived(
        derived[GateId.EXACT_YES_NO_STRUCTURE],
        quote_gates[GateId.REPRODUCIBLE_PROVIDER_MAPPING],
    )
    derived[GateId.QUOTE_OBSERVED_AT] = _derive_timestamp(value)
    derived[GateId.SAME_BOOKMAKER_SNAPSHOT] = snapshot_gate
    derived[GateId.FIXTURE_MAPPING] = _derive_fixture_mapping(value)
    derived.update(historical_gates)
    derived.update(live_gates)
    derived.update(_derive_execution(value))
    market_qualification = {}
    for market in sorted(PERMITTED_MARKETS, key=lambda item: item.value):
        quote_row = quote_rows.get(market, {})
        historical_row = historical_rows.get(market, {})
        live_row = live_rows.get(market, {})
        market_results = {
            "semantics": _apply_claim_support(
                semantics_market[market], claims, {"MARKET_SEMANTICS"}
            ),
            "quote_mapping": _apply_claim_support(
                quote_market[market], claims, {"QUOTE_SCHEMA"}
            ),
            "snapshot": _apply_claim_support(
                snapshot_market[market], claims, {"SNAPSHOT"}
            ),
            "historical": _apply_claim_support(
                historical_market[market],
                claims,
                {"HISTORICAL_RETENTION", "FROZEN_COVERAGE"},
            ),
            "live": _apply_claim_support(
                live_market[market], claims, {"LIVE_AVAILABILITY"}
            ),
        }
        market_qualification[market.value] = {
            **{
                f"{name}_status": result.status.value
                for name, result in market_results.items()
            },
            **{
                f"{name}_reason": result.reason
                for name, result in market_results.items()
            },
            "quote_mapping_audit": {
                field: quote_row.get(field)
                for field in (
                    "provider_market_identifier",
                    "provider_market_name",
                    "provider_yes_selection_identifier",
                    "provider_yes_selection_label",
                    "provider_no_selection_identifier",
                    "provider_no_selection_label",
                    "bookmaker_identifier",
                    "bookmaker_name_or_source",
                    "provider_event_identifier",
                    "fixture_reference",
                )
            },
            "snapshot_audit": snapshot_audit[market],
            "historical_frozen_period_coverage": historical_row.get(
                "frozen_period_coverage"
            ),
            "live_protocol_audit": {
                field: live_row.get(field)
                for field in (
                    "maximum_quote_age_seconds",
                    "excludes_post_decision",
                    "excludes_post_kickoff",
                )
            },
        }
    return derived, market_qualification


def _claim_support_capabilities(
    claim_ids: Sequence[str],
    claims: Mapping[str, EvidenceClaim],
    permitted_capabilities: set[str] | frozenset[str],
) -> DerivedGate:
    if not claim_ids:
        return DerivedGate(GateStatus.UNKNOWN, "MISSING_EVIDENCE_CLAIMS")
    resolved = []
    for claim_id in claim_ids:
        claim = claims.get(claim_id)
        if claim is None:
            return DerivedGate(
                GateStatus.UNKNOWN, "UNKNOWN_EVIDENCE_CLAIM", tuple(sorted(claim_ids))
            )
        if claim.capability_identifier not in permitted_capabilities:
            return DerivedGate(
                GateStatus.FAIL,
                "EVIDENCE_CLAIM_CAPABILITY_NOT_ALLOWED_FOR_GATE",
                tuple(sorted(claim_ids)),
            )
        resolved.append(claim)
    if any(claim.reviewer_conclusion is GateStatus.FAIL for claim in resolved):
        return DerivedGate(
            GateStatus.FAIL, "CONTRADICTORY_EVIDENCE_CLAIM", tuple(sorted(claim_ids))
        )
    if any(claim.reviewer_conclusion is GateStatus.UNKNOWN for claim in resolved):
        return DerivedGate(
            GateStatus.UNKNOWN, "UNKNOWN_EVIDENCE_CLAIM", tuple(sorted(claim_ids))
        )
    return DerivedGate(
        GateStatus.PASS, "TYPED_EVIDENCE_CLAIMS_VALIDATED", tuple(sorted(claim_ids))
    )


def _claim_support(
    gate: GateId,
    claim_ids: Sequence[str],
    claims: Mapping[str, EvidenceClaim],
) -> DerivedGate:
    return _claim_support_capabilities(
        claim_ids, claims, CLAIM_CAPABILITY_ALLOWLIST[gate]
    )


def _apply_claim_support(
    result: DerivedGate,
    claims: Mapping[str, EvidenceClaim],
    permitted_capabilities: set[str] | frozenset[str],
) -> DerivedGate:
    support = _claim_support_capabilities(
        result.evidence_claim_ids, claims, permitted_capabilities
    )
    return _merge_derived(result, support)


def build_effective_gates(
    declared: Mapping[GateId, GateEvidence],
    derived: Mapping[GateId, DerivedGate],
    *,
    claims: Mapping[str, EvidenceClaim],
    checked_at: datetime,
) -> tuple[dict[GateId, GateEvidence], dict[str, dict]]:
    effective = {}
    audit = {}
    for gate in GateId:
        declaration = declared.get(
            gate,
            GateEvidence(GateStatus.UNKNOWN, "NO_REVIEWER_DECLARATION", (), checked_at),
        )
        structured = derived[gate]
        declared_claims = _claim_support(gate, declaration.evidence_claim_ids, claims)
        structured_claims = _claim_support(gate, structured.evidence_claim_ids, claims)
        if structured.status is GateStatus.FAIL or structured_claims.status is GateStatus.FAIL:
            status = GateStatus.FAIL
            reason = (
                structured.reason
                if structured.status is GateStatus.FAIL
                else structured_claims.reason
            )
        elif declaration.status is GateStatus.FAIL or declared_claims.status is GateStatus.FAIL:
            status = GateStatus.FAIL
            reason = (
                "REVIEWER_DECLARED_FAIL"
                if declaration.status is GateStatus.FAIL
                else declared_claims.reason
            )
        elif declaration.status is GateStatus.NOT_APPLICABLE and gate not in OPTIONAL_GATES:
            status = GateStatus.FAIL
            reason = "NOT_APPLICABLE_NOT_ALLOWED"
        elif structured.status is GateStatus.NOT_APPLICABLE and gate not in OPTIONAL_GATES:
            status = GateStatus.FAIL
            reason = "NOT_APPLICABLE_NOT_ALLOWED"
        elif gate in OPTIONAL_GATES and declaration.status is GateStatus.NOT_APPLICABLE:
            if structured.status is GateStatus.NOT_APPLICABLE and all(
                result.status is GateStatus.PASS
                for result in (declared_claims, structured_claims)
            ):
                status = GateStatus.NOT_APPLICABLE
                reason = "OPTIONAL_CAPABILITY_EXPLICITLY_UNAVAILABLE"
            elif structured.status is GateStatus.PASS:
                status = GateStatus.FAIL
                reason = "OPTIONAL_CAPABILITY_STATUS_INCONSISTENT"
            else:
                status = GateStatus.UNKNOWN
                reason = "OPTIONAL_CAPABILITY_UNAVAILABILITY_UNPROVEN"
        elif gate in OPTIONAL_GATES and structured.status is GateStatus.NOT_APPLICABLE:
            status = GateStatus.FAIL if declaration.status is GateStatus.PASS else GateStatus.UNKNOWN
            reason = (
                "OPTIONAL_CAPABILITY_STATUS_INCONSISTENT"
                if declaration.status is GateStatus.PASS
                else "OPTIONAL_CAPABILITY_UNAVAILABILITY_UNDECLARED"
            )
        elif (
            structured.status is GateStatus.UNKNOWN
            or structured_claims.status is GateStatus.UNKNOWN
            or declaration.status is GateStatus.UNKNOWN
            or declared_claims.status is GateStatus.UNKNOWN
        ):
            status = GateStatus.UNKNOWN
            reason = (
                structured.reason
                if structured.status is GateStatus.UNKNOWN
                else "EVIDENCE_CLAIMS_OR_REVIEWER_STATUS_UNKNOWN"
            )
        elif declaration.status is GateStatus.PASS and structured.status is GateStatus.PASS:
            status = GateStatus.PASS
            reason = "DECLARED_AND_STRUCTURED_EVIDENCE_VALIDATED"
        else:
            status = GateStatus.UNKNOWN
            reason = "GATE_STATUS_COMBINATION_UNAVAILABLE"
        effective_claim_ids = tuple(
            sorted(set(declaration.evidence_claim_ids + structured.evidence_claim_ids))
        )
        effective[gate] = GateEvidence(status, reason, effective_claim_ids, checked_at)
        audit[gate.value] = {
            "declared": declaration.to_dict(),
            "derived": {
                "status": structured.status.value,
                "reason": structured.reason,
                "evidence_claim_ids": list(structured.evidence_claim_ids),
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
    evidence_claims = load_evidence_claims(
        value.get("evidence_claims"),
        provider_identifier=provider_identifier,
        verified_evidence_paths=evidence_paths,
    )
    derived_gates, market_qualification = derive_structured_gates(
        value, provider_identifier, evidence_claims
    )
    effective_gates, gate_audit = build_effective_gates(
        declared_gates,
        derived_gates,
        claims=evidence_claims,
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
        "market_qualification": market_qualification,
        "unsupported_capabilities": unsupported,
        "unknown_capabilities": unknown,
        "limitations": sorted(item.strip()[:500] for item in limitations),
        "evidence_files": evidence_identities,
        "evidence_claims": [
            evidence_claims[claim_id].to_dict() for claim_id in sorted(evidence_claims)
        ],
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
