"""Deterministic Stage 5B4 Win Either Half campaign commitment contract.

This module defines reusable domain structures, protocol validators, Stage 5B3
bundle verifiers, declaration generators, and GitHub deadline qualification
rules for prospective capture-campaign commitments.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from domain.markets import MARKET_REGISTRY, MarketId
from domain.win_either_half_capture_campaign import (
    DEFAULT_PROTOCOL_PATH as DEFAULT_STAGE_5B3_PROTOCOL_PATH,
)
from domain.win_either_half_capture_campaign import (
    FROZEN_CANDIDATE_OFFSETS_SECONDS,
    PERMITTED_MARKETS,
)
from domain.win_either_half_capture_campaign import (
    validate_campaign_protocol as validate_stage_5b3_protocol_raw,
)


SCHEMA_VERSION = 1
PROTOCOL_DATASET_NAME = "win-either-half-campaign-commitment-protocol-v1"
DECLARATION_DATASET_NAME = "win-either-half-campaign-commitment-v1"
ATTESTATION_DATASET_NAME = (
    "win-either-half-campaign-commitment-deadline-attestation-v1"
)

STAGE_5B3_TASKS_FILENAME = "capture-campaign-tasks-v1.jsonl"
STAGE_5B3_SUMMARY_FILENAME = "capture-campaign-summary-v1.json"
STAGE_5B3_MANIFEST_FILENAME = "capture-campaign-manifest-v1.json"

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMMITMENT_ROOT = Path("artifacts/research-commitments/win-either-half")
DEFAULT_PROTOCOL_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-protocols"
    / "win-either-half-campaign-commitment-v1.json"
)

DECLARATION_STATUS = (
    "TRACKED_DECLARATION_PENDING_GITHUB_DEADLINE_CHECK"
)
PROSPECTIVE_CLAIM_AUTHORIZED = False
EVIDENCE_COUNTING_AUTHORIZED = False

CAMPAIGN_ID_PATTERN = re.compile(r"^WEH-CAP-[0-9A-F]{24}$")

FORBIDDEN_FIELDS = frozenset({
    "acca_selection",
    "away_goals",
    "bet",
    "bet_decision",
    "bookmaker_odds",
    "calibrated_probability",
    "decimal_odds",
    "decision_label",
    "edge",
    "edge_pp",
    "expected_value",
    "fair_odds",
    "full_time_away_goals",
    "full_time_home_goals",
    "half_time_away_goals",
    "half_time_home_goals",
    "home_goals",
    "kelly",
    "kelly_stake",
    "label",
    "model_probability",
    "profit",
    "profitability",
    "settled_outcome",
    "stake",
    "target",
    "target_value",
})

GENERATED_SAFETY_CONTRACT: dict[str, bool] = {
    "network_requests": False,
    "scraping": False,
    "browser_automation": False,
    "credential_use": False,
    "odds_collection": False,
    "provider_qualification": False,
    "offset_selection": False,
    "market_activation": False,
    "production_approval": False,
    "bet_decision": False,
}

STAGE_5B3_SAFETY_CONTRACT: dict[str, bool] = {
    "network_requests": False,
    "scraping": False,
    "browser_automation": False,
    "credential_use": False,
    "odds_collection": False,
    "provider_qualification": False,
    "offset_selection": False,
    "market_activation": False,
    "bet_decision": False,
}


class CampaignCommitmentError(ValueError):
    """Raised when campaign commitment validation fails closed."""


def _assert_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or isinstance(value, bool):
        raise CampaignCommitmentError(f"{label} must be a string")
    stripped = value.strip()
    if not stripped or stripped != value:
        raise CampaignCommitmentError(
            f"{label} must be an unpadded non-empty string"
        )
    return stripped


def _assert_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CampaignCommitmentError(f"{label} must be an integer")
    return value


def parse_utc(value: Any, label: str) -> datetime:
    text = _assert_str(value, label)
    if not (text.endswith("Z") or "+00:00" in text):
        raise CampaignCommitmentError(
            f"{label} must be an explicit UTC timestamp (Z or +00:00)"
        )
    iso_text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_text)
    except ValueError as error:
        raise CampaignCommitmentError(
            f"{label} must be a valid ISO 8601 UTC timestamp: {text}"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(None):
        raise CampaignCommitmentError(
            f"{label} must have a valid UTC timezone offset: {text}"
        )
    return parsed.astimezone(timezone.utc)


def serialize_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(None):
        raise CampaignCommitmentError("Serialization requires a UTC datetime")
    utc_dt = value.astimezone(timezone.utc)
    text = utc_dt.isoformat()
    if "+00:00" in text:
        text = text.replace(".000000+00:00", "Z").replace("+00:00", "Z")
    return text


def validate_sha256(value: Any, label: str) -> str:
    text = _assert_str(value, label)
    if len(text) != 64 or not all(char in "0123456789abcdefABCDEF" for char in text):
        raise CampaignCommitmentError(
            f"{label} must be a full 64-character hexadecimal SHA-256 string"
        )
    return text.lower()


def validate_git_sha(value: Any, label: str) -> str:
    text = _assert_str(value, label)
    if len(text) != 40 or not all(char in "0123456789abcdefABCDEF" for char in text):
        raise CampaignCommitmentError(
            f"{label} must be a full 40-character hexadecimal Git SHA"
        )
    return text.lower()


def canonical_json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    options: dict[str, Any] = {
        "ensure_ascii": False,
        "allow_nan": False,
        "sort_keys": True,
    }
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    return (json.dumps(value, **options) + "\n").encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _walk_mapping_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key).strip().lower()
            yield from _walk_mapping_keys(child)
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            yield from _walk_mapping_keys(child)


def assert_no_forbidden_fields(value: Any, label: str) -> None:
    found = sorted(FORBIDDEN_FIELDS.intersection(_walk_mapping_keys(value)))
    if found:
        raise CampaignCommitmentError(
            f"{label} contains forbidden fields: {', '.join(found)}"
        )


@dataclass(frozen=True)
class FileIdentity:
    relative_name: str
    byte_size: int
    sha256: str
    rows: int | None = None

    def __post_init__(self) -> None:
        _assert_str(self.relative_name, "FileIdentity.relative_name")
        size = _assert_int(self.byte_size, "FileIdentity.byte_size")
        if size < 0:
            raise CampaignCommitmentError("FileIdentity.byte_size cannot be negative")
        validate_sha256(self.sha256, "FileIdentity.sha256")
        if self.rows is not None:
            r_val = _assert_int(self.rows, "FileIdentity.rows")
            if r_val < 0:
                raise CampaignCommitmentError("FileIdentity.rows cannot be negative")

    def to_mapping(self) -> dict[str, Any]:
        mapping: dict[str, Any] = {
            "relative_name": self.relative_name,
            "byte_size": self.byte_size,
            "sha256": self.sha256.lower(),
        }
        if self.rows is not None:
            mapping["rows"] = self.rows
        return mapping


@dataclass(frozen=True)
class CampaignTarget:
    provider_identifier: str
    source: str
    bookmaker_identifier: str
    capture_method: str

    def __post_init__(self) -> None:
        _assert_str(self.provider_identifier, "CampaignTarget.provider_identifier")
        _assert_str(self.source, "CampaignTarget.source")
        _assert_str(self.bookmaker_identifier, "CampaignTarget.bookmaker_identifier")
        _assert_str(self.capture_method, "CampaignTarget.capture_method")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "provider_identifier": self.provider_identifier,
            "source": self.source,
            "bookmaker_identifier": self.bookmaker_identifier,
            "capture_method": self.capture_method,
        }


@dataclass(frozen=True)
class ValidatedStage5B3Bundle:
    campaign_id: str
    target: CampaignTarget
    prospective_replay_status: str
    commitment_deadline_at: datetime
    fixture_count: int
    task_count: int
    tasks_identity: FileIdentity
    summary_identity: FileIdentity
    manifest_identity: FileIdentity

    def __post_init__(self) -> None:
        _assert_str(self.campaign_id, "ValidatedStage5B3Bundle.campaign_id")
        if not CAMPAIGN_ID_PATTERN.match(self.campaign_id):
            raise CampaignCommitmentError(
                f"Invalid Stage 5B3 campaign_id pattern: {self.campaign_id}"
            )
        _assert_str(
            self.prospective_replay_status,
            "ValidatedStage5B3Bundle.prospective_replay_status",
        )
        if self.commitment_deadline_at.tzinfo is None:
            raise CampaignCommitmentError(
                "ValidatedStage5B3Bundle.commitment_deadline_at must be timezone-aware UTC"
            )
        fc = _assert_int(self.fixture_count, "ValidatedStage5B3Bundle.fixture_count")
        tc = _assert_int(self.task_count, "ValidatedStage5B3Bundle.task_count")
        if fc <= 0 or tc <= 0:
            raise CampaignCommitmentError(
                "Fixture count and task count must be positive"
            )


@dataclass(frozen=True)
class CommitmentDeclaration:
    schema_version: int
    dataset_name: str
    campaign_id: str
    campaign_commitment_status: str
    prospective_timing_qualified: bool
    prospective_claim_authorized: bool
    evidence_counting_authorized: bool
    commitment_deadline_at: datetime
    campaign_target: CampaignTarget
    prospective_replay_status: str
    fixture_count: int
    task_count: int
    source_bundle: dict[str, FileIdentity]
    upstream_protocols: dict[str, FileIdentity]
    generator_git_sha: str
    timing_authority: dict[str, Any]
    selected_offset_seconds: None
    selection_authorized: bool
    production_approval_authorized: bool
    market_statuses: dict[str, str]
    safety: dict[str, bool]
    no_production_approval: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "campaign_id": self.campaign_id,
            "campaign_commitment_status": self.campaign_commitment_status,
            "prospective_timing_qualified": self.prospective_timing_qualified,
            "prospective_claim_authorized": self.prospective_claim_authorized,
            "evidence_counting_authorized": self.evidence_counting_authorized,
            "commitment_deadline_at": serialize_utc(self.commitment_deadline_at),
            "campaign_target": self.campaign_target.to_mapping(),
            "prospective_replay_status": self.prospective_replay_status,
            "fixture_count": self.fixture_count,
            "task_count": self.task_count,
            "source_bundle": {
                name: identity.to_mapping()
                for name, identity in sorted(self.source_bundle.items())
            },
            "upstream_protocols": {
                name: identity.to_mapping()
                for name, identity in sorted(self.upstream_protocols.items())
            },
            "generator_git_sha": self.generator_git_sha,
            "timing_authority": self.timing_authority,
            "selected_offset_seconds": None,
            "selection_authorized": False,
            "production_approval_authorized": False,
            "market_statuses": self.market_statuses,
            "safety": self.safety,
            "no_production_approval": self.no_production_approval,
        }


@dataclass(frozen=True)
class DeadlineValidationResult:
    path: Path
    campaign_id: str
    commitment_sha256: str
    commitment_deadline_at: datetime
    server_observed_at: datetime
    prospective_timing_qualified: bool

    def to_mapping(self) -> dict[str, Any]:
        return {
            "relative_path": str(self.path).replace("\\", "/"),
            "campaign_id": self.campaign_id,
            "commitment_sha256": self.commitment_sha256,
            "commitment_deadline_at": serialize_utc(self.commitment_deadline_at),
            "server_observed_at": serialize_utc(self.server_observed_at),
            "prospective_timing_qualified": self.prospective_timing_qualified,
            "prospective_claim_authorized": False,
        }


def build_expected_protocol_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dataset_name": PROTOCOL_DATASET_NAME,
        "stage": "5B4",
        "upstream_contracts": {
            "stage_5b2_protocol": "win-either-half-prospective-replay-protocol-v1",
            "stage_5b3_protocol": "win-either-half-prospective-capture-campaign-protocol-v1",
            "exact_protocol_bytes_required": True,
            "exact_stage_5b3_bundle_bytes_required": True,
        },
        "commitment_root": "artifacts/research-commitments/win-either-half",
        "commitment_filename_contract": {
            "pattern": "<campaign_id>.json",
            "campaign_id_pattern": "^WEH-CAP-[0-9A-F]{24}$",
            "one_campaign_per_file": True,
            "new_file_only": True,
            "modification_forbidden": True,
            "rename_forbidden": True,
            "copy_forbidden": True,
            "deletion_forbidden": True,
            "symlinks_forbidden": True,
        },
        "declaration_contract": {
            "campaign_commitment_status": DECLARATION_STATUS,
            "prospective_timing_qualified": False,
            "prospective_claim_authorized": False,
            "evidence_counting_authorized": False,
            "local_wall_clock_used": False,
            "local_file_timestamp_authoritative": False,
            "git_author_timestamp_authoritative": False,
            "git_committer_timestamp_authoritative": False,
            "source_bundle_bytes_frozen": True,
            "campaign_target_frozen": True,
            "commitment_deadline_frozen": True,
        },
        "github_deadline_contract": {
            "event": "pull_request",
            "time_source": "GITHUB_HOSTED_RUNNER_UTC",
            "comparison": "SERVER_OBSERVED_AT_LESS_THAN_OR_EQUAL_TO_COMMITMENT_DEADLINE_AT",
            "base_revision_verifier_required": True,
            "pull_request_target_forbidden": True,
            "repository_write_permission_required": False,
            "secrets_required": False,
            "successful_check_qualifies_timing_only": True,
            "prospective_claim_authorized": False,
        },
        "stage_5b3_bundle_contract": {
            "tasks_filename": STAGE_5B3_TASKS_FILENAME,
            "summary_filename": STAGE_5B3_SUMMARY_FILENAME,
            "manifest_filename": STAGE_5B3_MANIFEST_FILENAME,
            "campaign_commitment_status": "UNFROZEN_LOCAL_PLAN",
            "prospective_claim_authorized": False,
            "selected_offset_seconds": None,
            "selection_authorized": False,
            "production_approval_authorized": False,
            "minimum_tasks_per_fixture": 12,
            "candidate_offsets_seconds": [86400, 21600, 10800, 3600, 1800, 900],
            "permitted_markets": [
                "HOME_WIN_EITHER_HALF",
                "AWAY_WIN_EITHER_HALF",
            ],
        },
        "attestation_contract": {
            "dataset_name": ATTESTATION_DATASET_NAME,
            "contains_github_run_id": True,
            "contains_github_run_attempt": True,
            "contains_base_sha": True,
            "contains_head_sha": True,
            "contains_server_observed_at": True,
            "contains_commitment_deadline_at": True,
            "contains_commitment_sha256": True,
            "contains_per_declaration_result": True,
            "prospective_timing_qualified_on_success": True,
            "prospective_claim_authorized": False,
        },
        "forbidden_fields": sorted(FORBIDDEN_FIELDS),
        "safety": dict(GENERATED_SAFETY_CONTRACT),
    }


def validate_protocol_contract(
    payload: Mapping[str, Any],
    raw_bytes: bytes,
    *,
    committed_path: Path = DEFAULT_PROTOCOL_PATH,
) -> None:
    if committed_path.is_symlink() or not committed_path.is_file():
        raise CampaignCommitmentError(
            f"Committed Stage 5B4 protocol path must be a regular non-symlink file: {committed_path}"
        )
    committed_raw = committed_path.read_bytes()
    if raw_bytes != committed_raw:
        raise CampaignCommitmentError(
            "Stage 5B4 campaign commitment protocol bytes differ from committed protocol file"
        )
    try:
        committed_payload = json.loads(committed_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CampaignCommitmentError(
            "Committed Stage 5B4 protocol file must be valid UTF-8 JSON"
        ) from error
    if payload != committed_payload:
        raise CampaignCommitmentError(
            "Stage 5B4 campaign commitment protocol parsed content differs from committed protocol file"
        )
    expected = build_expected_protocol_contract()
    if payload != expected:
        raise CampaignCommitmentError(
            "Stage 5B4 campaign commitment protocol payload differs from Python expected contract"
        )


def validate_stage_5b3_protocol(
    payload: Mapping[str, Any],
    raw_bytes: bytes,
    *,
    committed_path: Path = DEFAULT_STAGE_5B3_PROTOCOL_PATH,
) -> None:
    try:
        validate_stage_5b3_protocol_raw(
            payload, raw_bytes, committed_path=committed_path
        )
    except ValueError as error:
        raise CampaignCommitmentError(
            f"Stage 5B3 protocol validation failed: {error}"
        ) from error


def _safe_read_file(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CampaignCommitmentError(f"{label} must be a non-symlink file: {path}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise CampaignCommitmentError(f"Could not read {label}: {path}") from error


def validate_stage_5b3_bundle(
    *,
    tasks_path: Path,
    summary_path: Path,
    manifest_path: Path,
) -> ValidatedStage5B3Bundle:
    if tasks_path.name != STAGE_5B3_TASKS_FILENAME:
        raise CampaignCommitmentError(
            f"Tasks filename must be {STAGE_5B3_TASKS_FILENAME}"
        )
    if summary_path.name != STAGE_5B3_SUMMARY_FILENAME:
        raise CampaignCommitmentError(
            f"Summary filename must be {STAGE_5B3_SUMMARY_FILENAME}"
        )
    if manifest_path.name != STAGE_5B3_MANIFEST_FILENAME:
        raise CampaignCommitmentError(
            f"Manifest filename must be {STAGE_5B3_MANIFEST_FILENAME}"
        )

    tasks_raw = _safe_read_file(tasks_path, "Stage 5B3 tasks")
    summary_raw = _safe_read_file(summary_path, "Stage 5B3 summary")
    manifest_raw = _safe_read_file(manifest_path, "Stage 5B3 manifest")

    try:
        summary = json.loads(summary_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CampaignCommitmentError(
            "Stage 5B3 summary must be valid UTF-8 JSON"
        ) from error
    if not isinstance(summary, Mapping):
        raise CampaignCommitmentError("Stage 5B3 summary must be a JSON object")

    try:
        manifest = json.loads(manifest_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CampaignCommitmentError(
            "Stage 5B3 manifest must be valid UTF-8 JSON"
        ) from error
    if not isinstance(manifest, Mapping):
        raise CampaignCommitmentError("Stage 5B3 manifest must be a JSON object")

    lines = tasks_raw.decode("utf-8").splitlines()
    if not lines:
        raise CampaignCommitmentError("Stage 5B3 tasks file cannot be empty")

    task_rows: list[dict[str, Any]] = []
    for line_idx, line in enumerate(lines, start=1):
        if not line.strip():
            raise CampaignCommitmentError(
                f"Stage 5B3 tasks file contains blank line at line {line_idx}"
            )
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise CampaignCommitmentError(
                f"Stage 5B3 tasks row {line_idx} is invalid JSON"
            ) from error
        if not isinstance(row, dict):
            raise CampaignCommitmentError(
                f"Stage 5B3 tasks row {line_idx} must be a JSON object"
            )
        task_rows.append(row)

    assert_no_forbidden_fields(task_rows, "Stage 5B3 tasks")
    assert_no_forbidden_fields(summary, "Stage 5B3 summary")

    if manifest.get("safety") != STAGE_5B3_SAFETY_CONTRACT:
        raise CampaignCommitmentError(
            "Stage 5B3 manifest safety contract drifted from exact expectation"
        )
    manifest_clean = dict(manifest)
    manifest_clean.pop("safety")
    assert_no_forbidden_fields(manifest_clean, "Stage 5B3 manifest")

    expected_task_keys = {
        "schema_version",
        "line",
        "task_id",
        "task_state",
        "campaign_id",
        "fixture_identifier",
        "market_id",
        "offset_seconds_before_kickoff",
        "scheduled_at",
        "capture_window_opens_at",
        "capture_window_closes_at",
        "provider_identifier",
        "source",
        "bookmaker_identifier",
        "capture_method",
    }
    task_ids: set[str] = set()
    fixture_task_keys: set[tuple[str, str, int]] = set()
    fixture_ids: set[str] = set()
    campaign_ids: set[str] = set()
    targets: set[tuple[str, str, str, str]] = set()

    for idx, task in enumerate(task_rows, start=1):
        if set(task.keys()) != expected_task_keys:
            raise CampaignCommitmentError(
                f"Task row {idx} keys differ from exact Stage 5B3 task schema"
            )
        if task["schema_version"] != 1 or task["line"] is not None:
            raise CampaignCommitmentError(f"Task row {idx} schema/line invalid")
        if task["task_state"] != "PLANNED":
            raise CampaignCommitmentError(f"Task row {idx} state must be PLANNED")

        m_id = _assert_str(task["market_id"], f"Task {idx} market_id")
        if m_id not in {"HOME_WIN_EITHER_HALF", "AWAY_WIN_EITHER_HALF"}:
            raise CampaignCommitmentError(f"Task {idx} market {m_id} not permitted")

        offset = _assert_int(
            task["offset_seconds_before_kickoff"], f"Task {idx} offset"
        )
        if offset not in FROZEN_CANDIDATE_OFFSETS_SECONDS:
            raise CampaignCommitmentError(f"Task {idx} offset {offset} not permitted")

        t_id = _assert_str(task["task_id"], f"Task {idx} task_id")
        if t_id in task_ids:
            raise CampaignCommitmentError(f"Duplicate task_id {t_id} at row {idx}")
        task_ids.add(t_id)

        c_id = _assert_str(task["campaign_id"], f"Task {idx} campaign_id")
        campaign_ids.add(c_id)

        fix_id = _assert_str(task["fixture_identifier"], f"Task {idx} fixture_identifier")
        fixture_ids.add(fix_id)

        ft_key = (fix_id, m_id, offset)
        if ft_key in fixture_task_keys:
            raise CampaignCommitmentError(
                f"Duplicate (fixture, market, offset) tuple {ft_key} at row {idx}"
            )
        fixture_task_keys.add(ft_key)

        target_tuple = (
            _assert_str(task["provider_identifier"], "provider"),
            _assert_str(task["source"], "source"),
            _assert_str(task["bookmaker_identifier"], "bookmaker"),
            _assert_str(task["capture_method"], "method"),
        )
        targets.add(target_tuple)

        sched_dt = parse_utc(task["scheduled_at"], f"Task {idx} scheduled_at")
        open_dt = parse_utc(
            task["capture_window_opens_at"], f"Task {idx} window_opens"
        )
        close_dt = parse_utc(
            task["capture_window_closes_at"], f"Task {idx} window_closes"
        )
        if (sched_dt - open_dt).total_seconds() != 300:
            raise CampaignCommitmentError(
                f"Task {idx} scheduled_at must be opens_at + 300s"
            )
        if (close_dt - sched_dt).total_seconds() != 300:
            raise CampaignCommitmentError(
                f"Task {idx} closes_at must be scheduled_at + 300s"
            )

    if len(campaign_ids) != 1:
        raise CampaignCommitmentError("Tasks must share exactly one campaign_id")
    campaign_id = next(iter(campaign_ids))
    if not CAMPAIGN_ID_PATTERN.match(campaign_id):
        raise CampaignCommitmentError(f"Invalid task campaign_id: {campaign_id}")

    if len(targets) != 1:
        raise CampaignCommitmentError("Tasks must share exactly one campaign target")
    p_id, src, b_id, c_method = next(iter(targets))
    target = CampaignTarget(
        provider_identifier=p_id,
        source=src,
        bookmaker_identifier=b_id,
        capture_method=c_method,
    )

    if len(task_rows) != len(fixture_ids) * 12:
        raise CampaignCommitmentError(
            "Every fixture must have exactly 12 tasks (2 markets x 6 offsets)"
        )

    min_window_open = min(
        parse_utc(t["capture_window_opens_at"], "window_open") for t in task_rows
    )

    # Validate Summary
    if summary.get("schema_version") != 1:
        raise CampaignCommitmentError("Summary schema_version must be 1")
    if summary.get("campaign_id") != campaign_id:
        raise CampaignCommitmentError("Summary campaign_id mismatch")
    if summary.get("campaign_commitment_status") != "UNFROZEN_LOCAL_PLAN":
        raise CampaignCommitmentError(
            "Summary campaign_commitment_status must be UNFROZEN_LOCAL_PLAN"
        )
    if summary.get("prospective_claim_authorized") is not False:
        raise CampaignCommitmentError("Summary prospective_claim_authorized must be false")
    if summary.get("selected_offset_seconds") is not None:
        raise CampaignCommitmentError("Summary selected_offset_seconds must be null")
    if summary.get("selection_authorized") is not False:
        raise CampaignCommitmentError("Summary selection_authorized must be false")

    m_statuses = summary.get("market_statuses", {})
    if m_statuses.get("HOME_WIN_EITHER_HALF") != "DISABLED" or m_statuses.get("AWAY_WIN_EITHER_HALF") != "DISABLED":
        raise CampaignCommitmentError("Summary markets must both be DISABLED")

    deadline_dt = parse_utc(
        summary.get("commitment_deadline_at"), "summary commitment_deadline_at"
    )
    if deadline_dt != min_window_open:
        raise CampaignCommitmentError(
            "Summary commitment_deadline_at must equal earliest window_opens_at"
        )

    if summary.get("fixture_count") != len(fixture_ids):
        raise CampaignCommitmentError("Summary fixture_count mismatch")
    if summary.get("task_count") != len(task_rows):
        raise CampaignCommitmentError("Summary task_count mismatch")

    # Validate Manifest
    if manifest.get("schema_version") != 1:
        raise CampaignCommitmentError("Manifest schema_version must be 1")
    if manifest.get("campaign_id") != campaign_id:
        raise CampaignCommitmentError("Manifest campaign_id mismatch")

    m_registry = manifest.get("market_registry", [])
    if not isinstance(m_registry, (list, dict)) or len(m_registry) != len(MARKET_REGISTRY):
        raise CampaignCommitmentError(
            f"Manifest market_registry must contain all {len(MARKET_REGISTRY)} markets"
        )
    ms_registry = manifest.get("model_status_registry", {})
    if ms_registry.get("HOME_WIN_EITHER_HALF") != "DISABLED" or ms_registry.get("AWAY_WIN_EITHER_HALF") != "DISABLED":
        raise CampaignCommitmentError("Manifest model status registry markets must both be DISABLED")

    if manifest.get("selected_offset_seconds") is not None:
        raise CampaignCommitmentError("Manifest selected_offset_seconds must be null")
    if manifest.get("selection_authorized") is not False:
        raise CampaignCommitmentError("Manifest selection_authorized must be false")
    if manifest.get("production_approval_authorized") is not False:
        raise CampaignCommitmentError("Manifest production_approval_authorized must be false")

    m_outputs = manifest.get("outputs", {})
    if not isinstance(m_outputs, dict) or set(m_outputs.keys()) != {"tasks", "summary"}:
        raise CampaignCommitmentError("Manifest outputs keys invalid")

    t_out = m_outputs["tasks"]
    if (
        t_out.get("byte_size") != len(tasks_raw)
        or t_out.get("sha256") != sha256_bytes(tasks_raw)
        or t_out.get("rows") != len(task_rows)
    ):
        raise CampaignCommitmentError("Manifest tasks output identity mismatch")

    s_out = m_outputs["summary"]
    if (
        s_out.get("byte_size") != len(summary_raw)
        or s_out.get("sha256") != sha256_bytes(summary_raw)
        or s_out.get("rows") != 1
    ):
        raise CampaignCommitmentError("Manifest summary output identity mismatch")

    # Verify logical manifest hash
    manifest_pre = dict(manifest)
    manifest_pre.pop("logical_manifest_sha256", None)
    expected_logical_sha = sha256_bytes(canonical_json_bytes(manifest_pre, pretty=True))
    if manifest.get("logical_manifest_sha256") != expected_logical_sha:
        raise CampaignCommitmentError("Manifest logical_manifest_sha256 mismatch")

    tasks_ident = FileIdentity(
        relative_name=STAGE_5B3_TASKS_FILENAME,
        byte_size=len(tasks_raw),
        sha256=sha256_bytes(tasks_raw),
        rows=len(task_rows),
    )
    summary_ident = FileIdentity(
        relative_name=STAGE_5B3_SUMMARY_FILENAME,
        byte_size=len(summary_raw),
        sha256=sha256_bytes(summary_raw),
        rows=1,
    )
    manifest_ident = FileIdentity(
        relative_name=STAGE_5B3_MANIFEST_FILENAME,
        byte_size=len(manifest_raw),
        sha256=sha256_bytes(manifest_raw),
        rows=1,
    )

    prospective_replay_status = _assert_str(
        summary.get("prospective_replay_status"), "summary prospective_replay_status"
    )

    return ValidatedStage5B3Bundle(
        campaign_id=campaign_id,
        target=target,
        prospective_replay_status=prospective_replay_status,
        commitment_deadline_at=deadline_dt,
        fixture_count=len(fixture_ids),
        task_count=len(task_rows),
        tasks_identity=tasks_ident,
        summary_identity=summary_ident,
        manifest_identity=manifest_ident,
    )


def build_commitment_declaration(
    *,
    bundle: ValidatedStage5B3Bundle,
    stage_5b3_protocol_raw: bytes,
    commitment_protocol_raw: bytes,
    generator_git_sha: str,
) -> CommitmentDeclaration:
    validate_git_sha(generator_git_sha, "generator_git_sha")

    stage_5b3_proto_ident = FileIdentity(
        relative_name=DEFAULT_STAGE_5B3_PROTOCOL_PATH.name,
        byte_size=len(stage_5b3_protocol_raw),
        sha256=sha256_bytes(stage_5b3_protocol_raw),
        rows=None,
    )
    stage_5b4_proto_ident = FileIdentity(
        relative_name=DEFAULT_PROTOCOL_PATH.name,
        byte_size=len(commitment_protocol_raw),
        sha256=sha256_bytes(commitment_protocol_raw),
        rows=None,
    )

    timing_authority = {
        "time_source": "GITHUB_HOSTED_RUNNER_UTC",
        "local_wall_clock_used": False,
        "local_file_timestamp_authoritative": False,
        "git_author_timestamp_authoritative": False,
        "git_committer_timestamp_authoritative": False,
        "deadline_verification_rule": (
            "Qualified only when PR containing new declaration is checked by "
            "base-revision verifier and server_observed_at <= commitment_deadline_at."
        ),
    }

    return CommitmentDeclaration(
        schema_version=SCHEMA_VERSION,
        dataset_name=DECLARATION_DATASET_NAME,
        campaign_id=bundle.campaign_id,
        campaign_commitment_status=DECLARATION_STATUS,
        prospective_timing_qualified=False,
        prospective_claim_authorized=False,
        evidence_counting_authorized=False,
        commitment_deadline_at=bundle.commitment_deadline_at,
        campaign_target=bundle.target,
        prospective_replay_status=bundle.prospective_replay_status,
        fixture_count=bundle.fixture_count,
        task_count=bundle.task_count,
        source_bundle={
            "tasks": bundle.tasks_identity,
            "summary": bundle.summary_identity,
            "manifest": bundle.manifest_identity,
        },
        upstream_protocols={
            "stage_5b3_protocol": stage_5b3_proto_ident,
            "stage_5b4_protocol": stage_5b4_proto_ident,
        },
        generator_git_sha=generator_git_sha,
        timing_authority=timing_authority,
        selected_offset_seconds=None,
        selection_authorized=False,
        production_approval_authorized=False,
        market_statuses={
            "HOME_WIN_EITHER_HALF": "DISABLED",
            "AWAY_WIN_EITHER_HALF": "DISABLED",
        },
        safety=dict(GENERATED_SAFETY_CONTRACT),
        no_production_approval=(
            "Stage 5B4 pre-registers a Stage 5B3 campaign schedule for timing "
            "qualification only. It contains no odds, selects no offset, enables no "
            "market, and authorizes no bet."
        ),
    )


def validate_declaration_mapping(
    payload: Mapping[str, Any],
    *,
    expected_path: Path | None = None,
) -> CommitmentDeclaration:
    if not isinstance(payload, Mapping):
        raise CampaignCommitmentError("Declaration payload must be a JSON object")

    if payload.get("safety") != GENERATED_SAFETY_CONTRACT:
        raise CampaignCommitmentError(
            "Declaration safety contract drifted from exact expectation"
        )
    payload_clean = dict(payload)
    payload_clean.pop("safety")
    assert_no_forbidden_fields(payload_clean, "Declaration")

    expected_keys = [
        "schema_version",
        "dataset_name",
        "campaign_id",
        "campaign_commitment_status",
        "prospective_timing_qualified",
        "prospective_claim_authorized",
        "evidence_counting_authorized",
        "commitment_deadline_at",
        "campaign_target",
        "prospective_replay_status",
        "fixture_count",
        "task_count",
        "source_bundle",
        "upstream_protocols",
        "generator_git_sha",
        "timing_authority",
        "selected_offset_seconds",
        "selection_authorized",
        "production_approval_authorized",
        "market_statuses",
        "safety",
        "no_production_approval",
    ]
    if list(payload.keys()) != expected_keys:
        raise CampaignCommitmentError(
            "Declaration keys/order differ from exact Stage 5B4 schema"
        )

    if payload["schema_version"] != 1:
        raise CampaignCommitmentError("Declaration schema_version must be 1")
    if payload["dataset_name"] != DECLARATION_DATASET_NAME:
        raise CampaignCommitmentError(
            f"Declaration dataset_name must be {DECLARATION_DATASET_NAME}"
        )

    c_id = _assert_str(payload["campaign_id"], "campaign_id")
    if not CAMPAIGN_ID_PATTERN.match(c_id):
        raise CampaignCommitmentError(f"Declaration campaign_id invalid: {c_id}")

    if expected_path is not None:
        if expected_path.name != f"{c_id}.json":
            raise CampaignCommitmentError(
                f"Declaration filename must be {c_id}.json, got {expected_path.name}"
            )

    if payload["campaign_commitment_status"] != DECLARATION_STATUS:
        raise CampaignCommitmentError(
            f"Declaration campaign_commitment_status must be {DECLARATION_STATUS}"
        )
    if payload["prospective_timing_qualified"] is not False:
        raise CampaignCommitmentError(
            "Declaration prospective_timing_qualified must be false before GitHub check"
        )
    if payload["prospective_claim_authorized"] is not False:
        raise CampaignCommitmentError(
            "Declaration prospective_claim_authorized must be false"
        )
    if payload["evidence_counting_authorized"] is not False:
        raise CampaignCommitmentError(
            "Declaration evidence_counting_authorized must be false"
        )

    deadline_dt = parse_utc(
        payload["commitment_deadline_at"], "commitment_deadline_at"
    )

    t_map = payload["campaign_target"]
    if not isinstance(t_map, Mapping):
        raise CampaignCommitmentError("campaign_target must be a object")
    target = CampaignTarget(
        provider_identifier=_assert_str(t_map.get("provider_identifier"), "target.provider"),
        source=_assert_str(t_map.get("source"), "target.source"),
        bookmaker_identifier=_assert_str(t_map.get("bookmaker_identifier"), "target.bookmaker"),
        capture_method=_assert_str(t_map.get("capture_method"), "target.method"),
    )

    p_status = _assert_str(
        payload["prospective_replay_status"], "prospective_replay_status"
    )
    f_count = _assert_int(payload["fixture_count"], "fixture_count")
    t_count = _assert_int(payload["task_count"], "task_count")
    if f_count <= 0 or t_count <= 0:
        raise CampaignCommitmentError("fixture_count and task_count must be positive")

    sb_map = payload["source_bundle"]
    if not isinstance(sb_map, Mapping) or set(sb_map.keys()) != {"manifest", "summary", "tasks"}:
        raise CampaignCommitmentError("source_bundle must contain tasks, summary, manifest")
    source_bundle = {
        k: FileIdentity(
            relative_name=_assert_str(v.get("relative_name"), f"source_bundle.{k}.name"),
            byte_size=_assert_int(v.get("byte_size"), f"source_bundle.{k}.size"),
            sha256=validate_sha256(v.get("sha256"), f"source_bundle.{k}.sha256"),
            rows=v.get("rows"),
        )
        for k, v in sb_map.items()
    }

    up_map = payload["upstream_protocols"]
    if not isinstance(up_map, Mapping) or set(up_map.keys()) != {"stage_5b3_protocol", "stage_5b4_protocol"}:
        raise CampaignCommitmentError("upstream_protocols must contain stage_5b3_protocol and stage_5b4_protocol")
    upstream_protocols = {
        k: FileIdentity(
            relative_name=_assert_str(v.get("relative_name"), f"upstream_protocols.{k}.name"),
            byte_size=_assert_int(v.get("byte_size"), f"upstream_protocols.{k}.size"),
            sha256=validate_sha256(v.get("sha256"), f"upstream_protocols.{k}.sha256"),
            rows=v.get("rows"),
        )
        for k, v in up_map.items()
    }

    gen_sha = validate_git_sha(payload["generator_git_sha"], "generator_git_sha")

    if payload["selected_offset_seconds"] is not None:
        raise CampaignCommitmentError("selected_offset_seconds must be null")
    if payload["selection_authorized"] is not False:
        raise CampaignCommitmentError("selection_authorized must be false")
    if payload["production_approval_authorized"] is not False:
        raise CampaignCommitmentError("production_approval_authorized must be false")

    m_statuses = payload["market_statuses"]
    if not isinstance(m_statuses, dict) or m_statuses.get("HOME_WIN_EITHER_HALF") != "DISABLED" or m_statuses.get("AWAY_WIN_EITHER_HALF") != "DISABLED":
        raise CampaignCommitmentError("Declaration market_statuses must both be DISABLED")

    return CommitmentDeclaration(
        schema_version=1,
        dataset_name=DECLARATION_DATASET_NAME,
        campaign_id=c_id,
        campaign_commitment_status=DECLARATION_STATUS,
        prospective_timing_qualified=False,
        prospective_claim_authorized=False,
        evidence_counting_authorized=False,
        commitment_deadline_at=deadline_dt,
        campaign_target=target,
        prospective_replay_status=p_status,
        fixture_count=f_count,
        task_count=t_count,
        source_bundle=source_bundle,
        upstream_protocols=upstream_protocols,
        generator_git_sha=gen_sha,
        timing_authority=dict(payload["timing_authority"]),
        selected_offset_seconds=None,
        selection_authorized=False,
        production_approval_authorized=False,
        market_statuses={"HOME_WIN_EITHER_HALF": "DISABLED", "AWAY_WIN_EITHER_HALF": "DISABLED"},
        safety=dict(GENERATED_SAFETY_CONTRACT),
        no_production_approval=_assert_str(payload["no_production_approval"], "no_production_approval"),
    )


def validate_deadline(
    declaration: CommitmentDeclaration,
    *,
    server_observed_at: datetime,
    commitment_sha256: str | None = None,
) -> DeadlineValidationResult:
    if server_observed_at.tzinfo is None or server_observed_at.utcoffset() != timezone.utc.utcoffset(None):
        raise CampaignCommitmentError("server_observed_at must be timezone-aware UTC")

    if commitment_sha256 is None:
        decl_bytes = canonical_json_bytes(declaration.to_mapping(), pretty=True)
        c_sha = sha256_bytes(decl_bytes)
    else:
        c_sha = validate_sha256(commitment_sha256, "commitment_sha256")

    # Strict UTC comparison: server_observed_at <= commitment_deadline_at
    qualified = server_observed_at <= declaration.commitment_deadline_at

    return DeadlineValidationResult(
        path=COMMITMENT_ROOT / f"{declaration.campaign_id}.json",
        campaign_id=declaration.campaign_id,
        commitment_sha256=c_sha,
        commitment_deadline_at=declaration.commitment_deadline_at,
        server_observed_at=server_observed_at,
        prospective_timing_qualified=qualified,
    )
