#!/usr/bin/env python3
"""Offline Stage 5B1 Win Either Half source-qualification exporter."""

from __future__ import annotations

import argparse
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
    PERMITTED_MARKETS,
    QualificationStatus,
    SCHEMA_VERSION,
    SourceQualificationError,
    SourceRole,
    canonical_market_registry_snapshot,
    qualify_mandatory_gates,
    qualify_prospective_replay,
    validate_market_semantics,
)
from scripts.freeze_evidence_baseline import get_code_state  # noqa: E402


DATASET_NAME = "win-either-half-pricing-source-qualification-v1"
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


def _override_gate(
    gates: dict[GateId, GateEvidence],
    gate: GateId,
    status: GateStatus,
    reason: str,
    checked_at: datetime,
) -> None:
    existing = gates.get(gate)
    reference = existing.evidence_reference if existing else None
    gates[gate] = GateEvidence(status, reason, reference, checked_at)


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


def qualify_candidate(
    value: Mapping[str, Any],
    *,
    evidence_root: Path,
    protocol: Mapping[str, Any],
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
    gates = _load_gates(value.get("gate_evidence"))
    for gate in GateId:
        gates.setdefault(
            gate,
            GateEvidence(
                GateStatus.UNKNOWN,
                "NO_EVIDENCE_SUPPLIED",
                None,
                checked_at,
            ),
        )

    semantics = value["market_semantics_evidence"].get("markets")
    if not isinstance(semantics, list):
        raise QualificationExportError("market_semantics_evidence.markets must be a list")
    semantic_results = []
    for row in semantics:
        if not isinstance(row, Mapping):
            raise QualificationExportError("Market semantics row must be an object")
        try:
            semantic_results.append(validate_market_semantics(row))
        except SourceQualificationError as error:
            raise QualificationExportError(str(error)) from error
    if len(semantic_results) != 2 or any(
        result.status is not GateStatus.PASS for result in semantic_results
    ):
        reason = (
            "MISSING_MARKET_DESCRIPTION"
            if any(result.status is GateStatus.UNKNOWN for result in semantic_results)
            else "MARKET_SEMANTICS_MISMATCH"
        )
        _override_gate(gates, GateId.EXACT_MARKET_SEMANTICS, GateStatus.FAIL, reason, checked_at)

    outcome_ids = value["outcome_evidence"].get("identifiers")
    if outcome_ids != ["YES", "NO"]:
        _override_gate(
            gates,
            GateId.EXACT_YES_NO_STRUCTURE,
            GateStatus.FAIL,
            "YES_NO_IDENTIFIERS_MISMATCH",
            checked_at,
        )

    quote = value["quote_field_evidence"]
    price_type = quote.get("price_type")
    if price_type != "RAW_DECIMAL_BOOKMAKER_ODDS":
        _override_gate(
            gates,
            GateId.RAW_DECIMAL_ODDS,
            GateStatus.FAIL,
            "SYNTHETIC_OR_DERIVED_PRICE",
            checked_at,
        )
    if not quote.get("bookmaker_identifier") or not quote.get("bookmaker_name_or_source"):
        _override_gate(
            gates,
            GateId.BOOKMAKER_PROVENANCE,
            GateStatus.FAIL,
            "MISSING_BOOKMAKER_PROVENANCE",
            checked_at,
        )
    if not all(
        quote.get(field)
        for field in (
            "provider_event_identifier",
            "provider_market_identifier",
            "provider_selection_identifier",
            "fixture_kickoff_or_stable_reference",
        )
    ):
        _override_gate(
            gates,
            GateId.REPRODUCIBLE_PROVIDER_MAPPING,
            GateStatus.FAIL,
            "MISSING_PROVIDER_QUOTE_IDENTIFIER",
            checked_at,
        )
    timestamp = value["timestamp_evidence"]
    if timestamp.get("timestamp_source") != "PROVIDER_QUOTE_OR_UPDATE":
        _override_gate(
            gates,
            GateId.QUOTE_OBSERVED_AT,
            GateStatus.FAIL,
            "DOWNLOAD_TIME_IS_NOT_QUOTE_TIME",
            checked_at,
        )
    snapshot = value["snapshot_evidence"]
    if snapshot.get("yes_no_common_snapshot") is not True:
        _override_gate(
            gates,
            GateId.SAME_BOOKMAKER_SNAPSHOT,
            GateStatus.FAIL,
            "YES_NO_SNAPSHOT_NOT_PROVEN",
            checked_at,
        )

    evidence_identities = validate_evidence_files(
        value.get("evidence_files"), evidence_root=evidence_root
    )
    evidence_paths = {identity["relative_path"] for identity in evidence_identities}
    for gate, result in gates.items():
        if (
            result.status is GateStatus.PASS
            and result.evidence_reference not in evidence_paths
        ):
            raise QualificationExportError(
                f"Passing gate evidence reference is not verified: {gate.value}"
            )
    limitations = value.get("limitations")
    if not isinstance(limitations, list) or any(
        not isinstance(item, str) or not item.strip() for item in limitations
    ):
        raise QualificationExportError("limitations must be a list of non-empty strings")
    role_statuses = {
        role.value: qualify_mandatory_gates(role, gates).value for role in roles
    }
    for role in SourceRole:
        role_statuses.setdefault(role.value, QualificationStatus.UNKNOWN.value)
    prospective = qualify_prospective_replay(gates)
    unsupported = sorted(
        gate.value for gate, result in gates.items() if result.status is GateStatus.FAIL
    )
    unknown = sorted(
        gate.value for gate in GateId if gates[gate].status is GateStatus.UNKNOWN
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
        "gate_results": {
            gate.value: result.to_dict()
            for gate, result in sorted(gates.items(), key=lambda item: item[0].value)
        },
        "unsupported_capabilities": unsupported,
        "unknown_capabilities": unknown,
        "limitations": sorted(item.strip()[:500] for item in limitations),
        "evidence_files": evidence_identities,
        "input_identity": dict(input_identity),
        "protocol": {
            "dataset_name": protocol.get("dataset_name"),
            "schema_version": protocol.get("schema_version"),
            "sha256": _sha256(_canonical_json_bytes(protocol, pretty=False)),
        },
        "decision_protocol": DEFAULT_DECISION_PROTOCOL.to_dict(),
        "holdout_governance": dict(CONSUMED_HOLDOUT_GOVERNANCE),
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
        protocol, _ = _read_json(args.protocol, "Qualification protocol")
        if not isinstance(protocol, Mapping) or protocol.get("schema_version") != 1:
            raise QualificationExportError("Qualification protocol contract differs")
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
