"""Deterministic Stage 5B4 Win Either Half prospective campaign commitment contract and validation.

This module provides deterministic validation and construction of Stage 5B4 campaign
commitment declarations. A Stage 5B4 declaration pre-registers a Stage 5B3 capture
campaign schedule before the earliest capture window opens, creating an immutable
public commitment baseline for prospective timing qualification in PR workflows.
It contains no odds, selects no offset, enables no market, and authorizes no bet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from domain.markets import MARKET_REGISTRY, MarketId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.win_either_half_capture_campaign import (
    ATTEMPT_WINDOW_SECONDS,
    EXPECTED_TASKS_PER_FIXTURE,
    FROZEN_CANDIDATE_OFFSETS_SECONDS,
    MINIMUM_FIXTURES_FOR_INTERPRETATION,
    PERMITTED_ATTEMPT_RESULTS,
    PERMITTED_MARKETS,
    PERMITTED_QUOTE_OUTCOMES,
    PERMITTED_SOURCE_STATUSES,
    assert_market_safety as assert_stage_5b3_market_safety,
    market_registry_snapshot,
    model_status_snapshot,
    validate_campaign_protocol as validate_stage_5b3_campaign_protocol,
)


SCHEMA_VERSION = 1
DATASET_NAME = "win-either-half-campaign-commitment-v1"
PROTOCOL_DATASET_NAME = "win-either-half-campaign-commitment-protocol-v1"
ATTESTATION_DATASET_NAME = "win-either-half-campaign-commitment-attestation-v1"
DECLARATION_DATASET_NAME = "win-either-half-campaign-commitment-declaration-v1"
DECLARATION_STATUS = "FROZEN_PROSPECTIVE_CAMPAIGN_COMMITTED"

DEFAULT_PROTOCOL_PATH = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "research-protocols"
    / "win-either-half-campaign-commitment-v1.json"
)

DEFAULT_STAGE_5B3_PROTOCOL_PATH = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "research-protocols"
    / "win-either-half-prospective-capture-campaign-v1.json"
)

STAGE_5B3_PROTOCOL_DATASET_NAME = (
    "win-either-half-prospective-capture-campaign-protocol-v1"
)

STAGE_5B3_TASKS_FILENAME = "capture-campaign-tasks-v1.jsonl"
STAGE_5B3_SUMMARY_FILENAME = "capture-campaign-summary-v1.json"
STAGE_5B3_MANIFEST_FILENAME = "capture-campaign-manifest-v1.json"

COMMITMENT_ROOT = Path("artifacts/research-commitments/win-either-half")

CAMPAIGN_ID_PATTERN = re.compile(r"^WEH-CAP-[0-9A-F]{24}$")
TASK_ID_PATTERN = re.compile(r"^WEH-TASK-[0-9A-F]{24}$")

PERMITTED_PROSPECTIVE_REPLAY_STATUSES = tuple(PERMITTED_SOURCE_STATUSES)

EXPECTED_DECLARATION_KEYS = frozenset(
    {
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
    }
)

EXPECTED_STAGE_5B3_TASK_KEYS = frozenset(
    {
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
)

EXPECTED_STAGE_5B3_SUMMARY_KEYS = frozenset(
    {
        "schema_version",
        "dataset_name",
        "campaign_id",
        "provider_identifier",
        "source",
        "bookmaker_identifier",
        "capture_method",
        "prospective_replay_status",
        "anchor_at",
        "fixture_count",
        "task_count",
        "expected_tasks_per_fixture",
        "expected_task_count",
        "candidate_offsets_seconds",
        "attempt_window_seconds",
        "permitted_markets",
        "expected_attempt_results",
        "expected_quote_outcomes",
        "earliest_scheduled_at",
        "latest_scheduled_at",
        "earliest_window_opens_at",
        "latest_window_closes_at",
        "minimum_fixtures_for_interpretation",
        "interpretation_eligible",
        "campaign_commitment_status",
        "prospective_claim_authorized",
        "commitment_deadline_at",
        "tracked_commitment_required_before_first_window",
        "selected_offset_seconds",
        "selection_authorized",
        "production_approval_authorized",
        "market_statuses",
        "no_production_approval",
    }
)

EXPECTED_STAGE_5B3_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "dataset_name",
        "generator",
        "generator_commit",
        "tracked_worktree_clean",
        "campaign_id",
        "provider_identifier",
        "campaign_target",
        "prospective_replay_status",
        "anchor_at",
        "candidate_offsets_seconds",
        "attempt_window_seconds",
        "expected_tasks_per_fixture",
        "minimum_fixtures_for_interpretation",
        "interpretation_eligible",
        "commitment",
        "task_identity",
        "deterministic_ordering",
        "market_registry",
        "model_status_registry",
        "selected_offset_seconds",
        "selection_authorized",
        "production_approval_authorized",
        "safety",
        "inputs",
        "outputs",
        "summary_accounting",
        "no_production_approval",
        "logical_manifest_sha256",
    }
)

TIMING_AUTHORITY_CONTRACT: dict[str, Any] = {
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

NO_PRODUCTION_APPROVAL_STATEMENT = (
    "Stage 5B4 pre-registers a Stage 5B3 campaign schedule for timing "
    "qualification only. It contains no odds, selects no offset, enables no "
    "market, and authorizes no bet."
)

STAGE_5B3_NO_PRODUCTION_APPROVAL_STATEMENT = (
    "Stage 5B3 creates an unfrozen local capture schedule only. It is not "
    "trusted proof of pre-registration. It collects no odds, selects no "
    "offset, enables no market, and issues no bet."
)

GENERATED_SAFETY_CONTRACT: dict[str, bool] = {
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

PROTOCOL_SAFETY_CONTRACT: dict[str, bool] = {
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

FORBIDDEN_FIELDS = frozenset(
    {
        "acca_selection",
        "away_goals",
        "bet",
        "bet_decision",
        "bookmaker_odds",
        "calibrated_probability",
        "decision_label",
        "decimal_odds",
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
    }
)


class CampaignCommitmentError(ValueError):
    """Raised when commitment contract or validation fails closed."""


@dataclass(frozen=True)
class FileIdentity:
    relative_name: str
    byte_size: int
    sha256: str
    rows: int | None = None

    def __post_init__(self) -> None:
        _assert_str(self.relative_name, "FileIdentity.relative_name")
        validate_sha256(self.sha256, "FileIdentity.sha256")
        if not isinstance(self.byte_size, int) or self.byte_size < 0:
            raise CampaignCommitmentError(
                "FileIdentity.byte_size must be a non-negative integer"
            )
        if self.rows is not None and (
            not isinstance(self.rows, int) or self.rows < 0
        ):
            raise CampaignCommitmentError(
                "FileIdentity.rows must be a non-negative integer or None"
            )

    def to_mapping(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "relative_name": self.relative_name,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
        }
        if self.rows is not None:
            payload["rows"] = self.rows
        return payload


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

    def to_mapping(self) -> dict[str, str]:
        return {
            "provider_identifier": self.provider_identifier,
            "source": self.source,
            "bookmaker_identifier": self.bookmaker_identifier,
            "capture_method": self.capture_method,
        }


@dataclass(frozen=True)
class SourceBundleAccounting:
    tasks_filename: str
    tasks_sha256: str
    summary_filename: str
    summary_sha256: str
    manifest_filename: str
    manifest_sha256: str
    manifest_logical_sha256: str

    def __post_init__(self) -> None:
        if self.tasks_filename != STAGE_5B3_TASKS_FILENAME:
            raise CampaignCommitmentError(
                f"Invalid tasks_filename: {self.tasks_filename}"
            )
        if self.summary_filename != STAGE_5B3_SUMMARY_FILENAME:
            raise CampaignCommitmentError(
                f"Invalid summary_filename: {self.summary_filename}"
            )
        if self.manifest_filename != STAGE_5B3_MANIFEST_FILENAME:
            raise CampaignCommitmentError(
                f"Invalid manifest_filename: {self.manifest_filename}"
            )
        validate_sha256(self.tasks_sha256, "tasks_sha256")
        validate_sha256(self.summary_sha256, "summary_sha256")
        validate_sha256(self.manifest_sha256, "manifest_sha256")
        validate_sha256(self.manifest_logical_sha256, "manifest_logical_sha256")

    def to_mapping(self) -> dict[str, str]:
        return {
            "tasks_filename": self.tasks_filename,
            "tasks_sha256": self.tasks_sha256,
            "summary_filename": self.summary_filename,
            "summary_sha256": self.summary_sha256,
            "manifest_filename": self.manifest_filename,
            "manifest_sha256": self.manifest_sha256,
            "manifest_logical_sha256": self.manifest_logical_sha256,
        }


@dataclass(frozen=True)
class UpstreamProtocols:
    stage_5b2_protocol_sha256: str
    stage_5b3_protocol_sha256: str
    stage_5b4_protocol_sha256: str

    def __post_init__(self) -> None:
        validate_sha256(self.stage_5b2_protocol_sha256, "stage_5b2_protocol_sha256")
        validate_sha256(self.stage_5b3_protocol_sha256, "stage_5b3_protocol_sha256")
        validate_sha256(self.stage_5b4_protocol_sha256, "stage_5b4_protocol_sha256")

    def to_mapping(self) -> dict[str, str]:
        return {
            "stage_5b2_protocol_sha256": self.stage_5b2_protocol_sha256,
            "stage_5b3_protocol_sha256": self.stage_5b3_protocol_sha256,
            "stage_5b4_protocol_sha256": self.stage_5b4_protocol_sha256,
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


@dataclass(frozen=True)
class CommitmentDeclaration:
    campaign_id: str
    commitment_deadline_at: datetime
    campaign_target: CampaignTarget
    prospective_replay_status: str
    fixture_count: int
    task_count: int
    source_bundle: dict[str, FileIdentity] | Mapping[str, FileIdentity] | SourceBundleAccounting
    upstream_protocols: dict[str, FileIdentity] | Mapping[str, FileIdentity] | UpstreamProtocols
    generator_git_sha: str
    schema_version: int = SCHEMA_VERSION
    dataset_name: str = DECLARATION_DATASET_NAME
    campaign_commitment_status: str = DECLARATION_STATUS
    prospective_timing_qualified: bool = False
    prospective_claim_authorized: bool = False
    evidence_counting_authorized: bool = False
    timing_authority: dict[str, Any] = field(
        default_factory=lambda: dict(TIMING_AUTHORITY_CONTRACT)
    )
    selected_offset_seconds: int | None = None
    selection_authorized: bool = False
    production_approval_authorized: bool = False
    market_statuses: dict[str, str] = field(
        default_factory=lambda: {
            "HOME_WIN_EITHER_HALF": "DISABLED",
            "AWAY_WIN_EITHER_HALF": "DISABLED",
        }
    )
    safety: dict[str, bool] = field(
        default_factory=lambda: dict(GENERATED_SAFETY_CONTRACT)
    )
    no_production_approval: str = NO_PRODUCTION_APPROVAL_STATEMENT

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise CampaignCommitmentError(
                f"schema_version must be {SCHEMA_VERSION}, got {self.schema_version}"
            )
        if self.dataset_name != DECLARATION_DATASET_NAME:
            raise CampaignCommitmentError(
                f"dataset_name must be {DECLARATION_DATASET_NAME}, got {self.dataset_name}"
            )
        if not CAMPAIGN_ID_PATTERN.match(self.campaign_id):
            raise CampaignCommitmentError(
                f"campaign_id format invalid: {self.campaign_id}"
            )
        if self.campaign_commitment_status != DECLARATION_STATUS:
            raise CampaignCommitmentError(
                f"campaign_commitment_status must be {DECLARATION_STATUS}"
            )
        if self.prospective_timing_qualified is not False:
            raise CampaignCommitmentError(
                "prospective_timing_qualified must initialize to False"
            )
        if self.prospective_claim_authorized is not False:
            raise CampaignCommitmentError(
                "prospective_claim_authorized must be False"
            )
        if self.evidence_counting_authorized is not False:
            raise CampaignCommitmentError(
                "evidence_counting_authorized must be False"
            )
        if not isinstance(self.commitment_deadline_at, datetime):
            raise CampaignCommitmentError(
                "commitment_deadline_at must be datetime"
            )
        if self.prospective_replay_status not in PERMITTED_PROSPECTIVE_REPLAY_STATUSES:
            raise CampaignCommitmentError(
                f"Invalid prospective_replay_status: {self.prospective_replay_status}"
            )
        if not isinstance(self.fixture_count, int) or self.fixture_count <= 0:
            raise CampaignCommitmentError("fixture_count must be a positive integer")
        if not isinstance(self.task_count, int) or self.task_count != self.fixture_count * 12:
            raise CampaignCommitmentError(
                f"task_count must equal fixture_count * 12 ({self.fixture_count * 12}), got {self.task_count}"
            )
        validate_git_sha(self.generator_git_sha, "generator_git_sha")
        if self.timing_authority != TIMING_AUTHORITY_CONTRACT:
            raise CampaignCommitmentError("timing_authority contract drifted")
        if self.selected_offset_seconds is not None:
            raise CampaignCommitmentError("selected_offset_seconds must be None")
        if self.selection_authorized is not False:
            raise CampaignCommitmentError("selection_authorized must be False")
        if self.production_approval_authorized is not False:
            raise CampaignCommitmentError(
                "production_approval_authorized must be False"
            )
        if self.market_statuses != {
            "HOME_WIN_EITHER_HALF": "DISABLED",
            "AWAY_WIN_EITHER_HALF": "DISABLED",
        }:
            raise CampaignCommitmentError("market_statuses must have both DISABLED")
        if self.safety != GENERATED_SAFETY_CONTRACT:
            raise CampaignCommitmentError("safety contract drifted")
        if self.no_production_approval != NO_PRODUCTION_APPROVAL_STATEMENT:
            raise CampaignCommitmentError("no_production_approval statement drifted")

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
            "source_bundle": (
                self.source_bundle.to_mapping()
                if hasattr(self.source_bundle, "to_mapping")
                else {k: v.to_mapping() for k, v in self.source_bundle.items()}
            ),
            "upstream_protocols": (
                self.upstream_protocols.to_mapping()
                if hasattr(self.upstream_protocols, "to_mapping")
                else {k: v.to_mapping() for k, v in self.upstream_protocols.items()}
            ),
            "generator_git_sha": self.generator_git_sha,
            "timing_authority": dict(self.timing_authority),
            "selected_offset_seconds": self.selected_offset_seconds,
            "selection_authorized": self.selection_authorized,
            "production_approval_authorized": self.production_approval_authorized,
            "market_statuses": dict(self.market_statuses),
            "safety": dict(self.safety),
            "no_production_approval": self.no_production_approval,
        }


@dataclass(frozen=True)
class DeadlineValidationResult:
    campaign_id: str
    commitment_sha256: str
    commitment_deadline_at: datetime
    server_observed_at: datetime
    prospective_timing_qualified: bool
    prospective_claim_authorized: bool = False

    def __post_init__(self) -> None:
        if not CAMPAIGN_ID_PATTERN.match(self.campaign_id):
            raise CampaignCommitmentError(
                f"campaign_id format invalid: {self.campaign_id}"
            )
        validate_sha256(self.commitment_sha256, "commitment_sha256")
        if not isinstance(self.commitment_deadline_at, datetime):
            raise CampaignCommitmentError("commitment_deadline_at must be datetime")
        if not isinstance(self.server_observed_at, datetime):
            raise CampaignCommitmentError("server_observed_at must be datetime")
        if not isinstance(self.prospective_timing_qualified, bool):
            raise CampaignCommitmentError(
                "prospective_timing_qualified must be boolean"
            )
        if self.prospective_claim_authorized is not False:
            raise CampaignCommitmentError(
                "prospective_claim_authorized must always be False"
            )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "commitment_sha256": self.commitment_sha256,
            "commitment_deadline_at": serialize_utc(self.commitment_deadline_at),
            "server_observed_at": serialize_utc(self.server_observed_at),
            "prospective_timing_qualified": self.prospective_timing_qualified,
            "prospective_claim_authorized": self.prospective_claim_authorized,
        }


def _assert_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CampaignCommitmentError(f"{label} must be a non-empty string")
    return value


def _assert_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CampaignCommitmentError(f"{label} must be an integer")
    return value


def assert_market_safety() -> None:
    assert_stage_5b3_market_safety()


def build_expected_protocol_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dataset_name": "win-either-half-campaign-commitment-protocol-v1",
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
            "campaign_id_pattern": r"^WEH-CAP-[0-9A-F]{24}$",
            "one_campaign_per_file": True,
            "new_file_only": True,
            "modification_forbidden": True,
            "rename_forbidden": True,
            "copy_forbidden": True,
            "deletion_forbidden": True,
            "symlinks_forbidden": True,
        },
        "declaration_contract": {
            "campaign_commitment_status": "TRACKED_DECLARATION_PENDING_GITHUB_DEADLINE_CHECK",
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
            "tasks_filename": "capture-campaign-tasks-v1.jsonl",
            "summary_filename": "capture-campaign-summary-v1.json",
            "manifest_filename": "capture-campaign-manifest-v1.json",
            "campaign_commitment_status": "UNFROZEN_LOCAL_PLAN",
            "prospective_claim_authorized": False,
            "selected_offset_seconds": None,
            "selection_authorized": False,
            "production_approval_authorized": False,
            "minimum_tasks_per_fixture": 12,
            "candidate_offsets_seconds": [
                86400,
                21600,
                10800,
                3600,
                1800,
                900,
            ],
            "permitted_markets": [
                "HOME_WIN_EITHER_HALF",
                "AWAY_WIN_EITHER_HALF",
            ],
        },
        "attestation_contract": {
            "dataset_name": "win-either-half-campaign-commitment-deadline-attestation-v1",
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
        "forbidden_fields": [
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
        ],
        "safety": {
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
        },
    }


def validate_git_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise CampaignCommitmentError(f"{label} must be a full 40-hex Git SHA")
    return value.lower()


def validate_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise CampaignCommitmentError(f"{label} must be a 64-character hexadecimal SHA-256")
    return value.lower()


def parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise CampaignCommitmentError(f"{label} must be a string timestamp")
    if not (value.endswith("Z") or "+00:00" in value):
        raise CampaignCommitmentError(f"{label} must be formatted as UTC ISO-8601")
    iso_val = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_val)
    except ValueError as error:
        raise CampaignCommitmentError(f"{label} invalid ISO timestamp: {value}") from error
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(None):
        raise CampaignCommitmentError(f"{label} must have UTC timezone")
    return dt


def serialize_utc(dt: datetime) -> str:
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(None):
        raise CampaignCommitmentError("Timestamp must have UTC timezone")
    formatted = dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    return formatted.replace("+00:00", "Z")


def canonical_json_bytes(value: Any, *, pretty: bool) -> bytes:
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


def assert_no_forbidden_fields(data: Any, context: str = "") -> None:
    if isinstance(data, Mapping):
        for k, v in data.items():
            if k in ("safety", "forbidden_fields"):
                continue
            if k in FORBIDDEN_FIELDS:
                raise CampaignCommitmentError(
                    f"Forbidden field '{k}' detected in {context}"
                )
            assert_no_forbidden_fields(v, f"{context}.{k}" if context else str(k))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            assert_no_forbidden_fields(item, f"{context}[{i}]")


def validate_protocol_contract(
    payload: Mapping[str, Any],
    raw_bytes: bytes,
    *,
    committed_path: Path | None = None,
) -> None:
    if not isinstance(payload, Mapping):
        raise CampaignCommitmentError("Stage 5B4 protocol payload must be a JSON object")

    if payload.get("safety") != PROTOCOL_SAFETY_CONTRACT:
        raise CampaignCommitmentError("Stage 5B4 protocol safety contract drifted")
    assert_no_forbidden_fields(payload, "Stage 5B4 protocol")

    expected = build_expected_protocol_contract()
    if payload != expected:
        raise CampaignCommitmentError("Stage 5B4 protocol payload drifted from Python contract")

    committed = committed_path or DEFAULT_PROTOCOL_PATH
    if not committed.is_file():
        raise CampaignCommitmentError(f"Committed protocol file missing: {committed}")
    committed_bytes = committed.read_bytes()
    if committed_bytes != raw_bytes:
        raise CampaignCommitmentError(
            "Stage 5B4 protocol bytes do not match exact committed protocol bytes"
        )


def validate_stage_5b3_protocol(
    payload: Mapping[str, Any],
    raw_bytes: bytes,
    *,
    committed_path: Path | None = None,
) -> None:
    try:
        validate_stage_5b3_campaign_protocol(
            payload,
            raw_bytes,
            committed_path=committed_path or DEFAULT_STAGE_5B3_PROTOCOL_PATH,
        )
    except Exception as error:
        raise CampaignCommitmentError(
            f"Stage 5B3 protocol validation failed: {error}"
        ) from error


def validate_stage_5b3_bundle(
    *,
    tasks_path: Path,
    summary_path: Path,
    manifest_path: Path,
) -> ValidatedStage5B3Bundle:
    assert_market_safety()

    for p, label in [
        (tasks_path, "Tasks file"),
        (summary_path, "Summary file"),
        (manifest_path, "Manifest file"),
    ]:
        if p.is_symlink() or not p.is_file():
            raise CampaignCommitmentError(f"{label} must be a regular non-symlink file: {p}")

    tasks_raw = tasks_path.read_bytes()
    summary_raw = summary_path.read_bytes()
    manifest_raw = manifest_path.read_bytes()

    try:
        summary = json.loads(summary_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CampaignCommitmentError("Stage 5B3 summary must be valid UTF-8 JSON") from error

    try:
        manifest = json.loads(manifest_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CampaignCommitmentError("Stage 5B3 manifest must be valid UTF-8 JSON") from error

    if not isinstance(summary, Mapping) or not isinstance(manifest, Mapping):
        raise CampaignCommitmentError("Summary and Manifest must be JSON objects")

    assert_no_forbidden_fields(summary, "Stage 5B3 summary")
    assert_no_forbidden_fields(manifest, "Stage 5B3 manifest")

    if summary.get("safety") is not None:
        assert_no_forbidden_fields(summary.get("safety"), "Stage 5B3 summary safety")
    if manifest.get("safety") != STAGE_5B3_SAFETY_CONTRACT:
        raise CampaignCommitmentError("Stage 5B3 manifest safety contract drifted")

    # Parse and validate task rows
    task_lines = [line for line in tasks_raw.splitlines() if line.strip()]
    if not task_lines:
        raise CampaignCommitmentError("Stage 5B3 tasks file is empty")

    task_rows: list[dict[str, Any]] = []
    seen_task_ids: set[str] = set()
    fixture_ids: set[str] = set()
    fixture_tasks: dict[str, list[dict[str, Any]]] = {}
    scheduled_dts: list[datetime] = []
    open_dts: list[datetime] = []
    close_dts: list[datetime] = []

    campaign_id: str | None = None
    target: CampaignTarget | None = None

    for idx, line in enumerate(task_lines, start=1):
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CampaignCommitmentError(f"Task line {idx} must be valid UTF-8 JSON") from error

        if not isinstance(row, dict):
            raise CampaignCommitmentError(f"Task line {idx} must be a JSON object")

        if set(row.keys()) != EXPECTED_STAGE_5B3_TASK_KEYS:
            raise CampaignCommitmentError(f"Task line {idx} keys differ from exact Stage 5B3 schema")

        assert_no_forbidden_fields(row, f"Task line {idx}")

        if row.get("schema_version") != 1:
            raise CampaignCommitmentError(f"Task line {idx} schema_version must be 1")
        if row.get("line") is not None:
            raise CampaignCommitmentError(f"Task line {idx} line must be null")
        if row.get("task_state") != "PLANNED":
            raise CampaignCommitmentError(f"Task line {idx} task_state must be PLANNED")

        t_id = _assert_str(row.get("task_id"), f"Task line {idx} task_id")
        if not TASK_ID_PATTERN.match(t_id):
            raise CampaignCommitmentError(f"Task line {idx} task_id invalid pattern: {t_id}")
        if t_id in seen_task_ids:
            raise CampaignCommitmentError(f"Duplicate task_id {t_id} at line {idx}")
        seen_task_ids.add(t_id)

        c_id = _assert_str(row.get("campaign_id"), f"Task line {idx} campaign_id")
        if not CAMPAIGN_ID_PATTERN.match(c_id):
            raise CampaignCommitmentError(f"Task line {idx} campaign_id invalid pattern: {c_id}")

        if campaign_id is None:
            campaign_id = c_id
        elif campaign_id != c_id:
            raise CampaignCommitmentError(f"Mixed campaign_id in tasks: {campaign_id} vs {c_id}")

        f_id = _assert_str(row.get("fixture_identifier"), f"Task line {idx} fixture_identifier")
        fixture_ids.add(f_id)
        fixture_tasks.setdefault(f_id, []).append(row)

        m_id = row.get("market_id")
        if m_id not in {"HOME_WIN_EITHER_HALF", "AWAY_WIN_EITHER_HALF"}:
            raise CampaignCommitmentError(f"Task line {idx} invalid market_id: {m_id}")

        offset = row.get("offset_seconds_before_kickoff")
        if offset not in FROZEN_CANDIDATE_OFFSETS_SECONDS:
            raise CampaignCommitmentError(f"Task line {idx} invalid offset: {offset}")

        sched_dt = parse_utc(row.get("scheduled_at"), f"Task line {idx} scheduled_at")
        open_dt = parse_utc(row.get("capture_window_opens_at"), f"Task line {idx} capture_window_opens_at")
        close_dt = parse_utc(row.get("capture_window_closes_at"), f"Task line {idx} capture_window_closes_at")

        scheduled_dts.append(sched_dt)
        open_dts.append(open_dt)
        close_dts.append(close_dt)

        if (sched_dt - open_dt).total_seconds() != ATTEMPT_WINDOW_SECONDS:
            raise CampaignCommitmentError(f"Task line {idx} window open must be exactly 300s before scheduled")
        if (close_dt - sched_dt).total_seconds() != ATTEMPT_WINDOW_SECONDS:
            raise CampaignCommitmentError(f"Task line {idx} window close must be exactly 300s after scheduled")

        row_target = CampaignTarget(
            provider_identifier=_assert_str(row.get("provider_identifier"), f"Task line {idx} provider_identifier"),
            source=_assert_str(row.get("source"), f"Task line {idx} source"),
            bookmaker_identifier=_assert_str(row.get("bookmaker_identifier"), f"Task line {idx} bookmaker_identifier"),
            capture_method=_assert_str(row.get("capture_method"), f"Task line {idx} capture_method"),
        )
        if target is None:
            target = row_target
        elif target != row_target:
            raise CampaignCommitmentError(f"Task line {idx} target mismatch across bundle")

        task_rows.append(row)

    if campaign_id is None or target is None:
        raise CampaignCommitmentError("Empty task set")

    # Verify per-fixture Cartesian product of 2 markets x 6 offsets = 12 tasks
    for f_id, f_tasks in fixture_tasks.items():
        if len(f_tasks) != EXPECTED_TASKS_PER_FIXTURE:
            raise CampaignCommitmentError(
                f"Fixture {f_id} has {len(f_tasks)} tasks, expected exactly {EXPECTED_TASKS_PER_FIXTURE}"
            )
        f_tuples = {(t["market_id"], t["offset_seconds_before_kickoff"]) for t in f_tasks}
        expected_tuples = {
            (m.value, off)
            for m in PERMITTED_MARKETS
            for off in FROZEN_CANDIDATE_OFFSETS_SECONDS
        }
        if f_tuples != expected_tuples:
            raise CampaignCommitmentError(
                f"Fixture {f_id} tasks do not match exact Cartesian product of markets and offsets"
            )

    if len(task_rows) != len(fixture_ids) * EXPECTED_TASKS_PER_FIXTURE:
        raise CampaignCommitmentError(
            f"Total task count {len(task_rows)} != fixture_count {len(fixture_ids)} * {EXPECTED_TASKS_PER_FIXTURE}"
        )

    min_window_open = min(open_dts)

    # Validate Summary schema and fields
    if set(summary.keys()) != EXPECTED_STAGE_5B3_SUMMARY_KEYS:
        raise CampaignCommitmentError("Summary keys differ from exact Stage 5B3 schema")
    if summary.get("schema_version") != 1:
        raise CampaignCommitmentError("Summary schema_version must be 1")
    if summary.get("dataset_name") != "win-either-half-capture-campaign-summary-v1":
        raise CampaignCommitmentError("Summary dataset_name invalid")
    if summary.get("campaign_id") != campaign_id:
        raise CampaignCommitmentError("Summary campaign_id mismatch")
    if summary.get("provider_identifier") != target.provider_identifier:
        raise CampaignCommitmentError("Summary provider_identifier mismatch")
    if summary.get("source") != target.source:
        raise CampaignCommitmentError("Summary source mismatch")
    if summary.get("bookmaker_identifier") != target.bookmaker_identifier:
        raise CampaignCommitmentError("Summary bookmaker_identifier mismatch")
    if summary.get("capture_method") != target.capture_method:
        raise CampaignCommitmentError("Summary capture_method mismatch")

    p_status = _assert_str(summary.get("prospective_replay_status"), "summary prospective_replay_status")
    if p_status not in PERMITTED_PROSPECTIVE_REPLAY_STATUSES:
        raise CampaignCommitmentError(f"Summary prospective_replay_status invalid: {p_status}")

    parse_utc(summary.get("anchor_at"), "summary anchor_at")

    if summary.get("fixture_count") != len(fixture_ids):
        raise CampaignCommitmentError("Summary fixture_count mismatch")
    if summary.get("task_count") != len(task_rows):
        raise CampaignCommitmentError("Summary task_count mismatch")
    if summary.get("expected_tasks_per_fixture") != EXPECTED_TASKS_PER_FIXTURE:
        raise CampaignCommitmentError("Summary expected_tasks_per_fixture mismatch")
    if summary.get("expected_task_count") != len(fixture_ids) * EXPECTED_TASKS_PER_FIXTURE:
        raise CampaignCommitmentError("Summary expected_task_count mismatch")
    if summary.get("candidate_offsets_seconds") != list(FROZEN_CANDIDATE_OFFSETS_SECONDS):
        raise CampaignCommitmentError("Summary candidate_offsets_seconds mismatch")
    if summary.get("attempt_window_seconds") != ATTEMPT_WINDOW_SECONDS:
        raise CampaignCommitmentError("Summary attempt_window_seconds mismatch")
    if summary.get("permitted_markets") != [m.value for m in PERMITTED_MARKETS]:
        raise CampaignCommitmentError("Summary permitted_markets mismatch")
    if summary.get("expected_attempt_results") != list(PERMITTED_ATTEMPT_RESULTS):
        raise CampaignCommitmentError("Summary expected_attempt_results mismatch")
    if summary.get("expected_quote_outcomes") != list(PERMITTED_QUOTE_OUTCOMES):
        raise CampaignCommitmentError("Summary expected_quote_outcomes mismatch")

    if summary.get("earliest_scheduled_at") != serialize_utc(min(scheduled_dts)):
        raise CampaignCommitmentError("Summary earliest_scheduled_at mismatch")
    if summary.get("latest_scheduled_at") != serialize_utc(max(scheduled_dts)):
        raise CampaignCommitmentError("Summary latest_scheduled_at mismatch")
    if summary.get("earliest_window_opens_at") != serialize_utc(min(open_dts)):
        raise CampaignCommitmentError("Summary earliest_window_opens_at mismatch")
    if summary.get("latest_window_closes_at") != serialize_utc(max(close_dts)):
        raise CampaignCommitmentError("Summary latest_window_closes_at mismatch")

    if summary.get("minimum_fixtures_for_interpretation") != MINIMUM_FIXTURES_FOR_INTERPRETATION:
        raise CampaignCommitmentError("Summary minimum_fixtures_for_interpretation mismatch")
    expected_eligible = bool(len(fixture_ids) >= MINIMUM_FIXTURES_FOR_INTERPRETATION)
    if summary.get("interpretation_eligible") is not expected_eligible:
        raise CampaignCommitmentError("Summary interpretation_eligible mismatch")

    if summary.get("campaign_commitment_status") != "UNFROZEN_LOCAL_PLAN":
        raise CampaignCommitmentError("Summary campaign_commitment_status must be UNFROZEN_LOCAL_PLAN")
    if summary.get("prospective_claim_authorized") is not False:
        raise CampaignCommitmentError("Summary prospective_claim_authorized must be false")
    if summary.get("tracked_commitment_required_before_first_window") is not True:
        raise CampaignCommitmentError("Summary tracked_commitment_required_before_first_window must be true")

    deadline_dt = parse_utc(summary.get("commitment_deadline_at"), "summary commitment_deadline_at")
    if deadline_dt != min_window_open:
        raise CampaignCommitmentError("Summary commitment_deadline_at must equal earliest window_opens_at")

    if summary.get("selected_offset_seconds") is not None:
        raise CampaignCommitmentError("Summary selected_offset_seconds must be null")
    if summary.get("selection_authorized") is not False:
        raise CampaignCommitmentError("Summary selection_authorized must be false")
    if summary.get("production_approval_authorized") is not False:
        raise CampaignCommitmentError("Summary production_approval_authorized must be false")

    m_statuses = summary.get("market_statuses")
    if not isinstance(m_statuses, dict) or m_statuses != {"HOME_WIN_EITHER_HALF": "DISABLED", "AWAY_WIN_EITHER_HALF": "DISABLED"}:
        raise CampaignCommitmentError("Summary market_statuses must both be DISABLED")

    _assert_str(summary.get("no_production_approval"), "Summary no_production_approval")

    # Validate Manifest schema and fields
    if set(manifest.keys()) != EXPECTED_STAGE_5B3_MANIFEST_KEYS:
        raise CampaignCommitmentError("Manifest keys differ from exact Stage 5B3 schema")
    if manifest.get("schema_version") != 1:
        raise CampaignCommitmentError("Manifest schema_version must be 1")
    if manifest.get("dataset_name") != "win-either-half-capture-campaign-manifest-v1":
        raise CampaignCommitmentError("Manifest dataset_name invalid")
    if manifest.get("generator") != "scripts/manage_win_either_half_capture_campaign.py":
        raise CampaignCommitmentError("Manifest generator invalid")
    validate_git_sha(manifest.get("generator_commit"), "Manifest generator_commit")
    if manifest.get("tracked_worktree_clean") is not True:
        raise CampaignCommitmentError("Manifest tracked_worktree_clean must be true")
    if manifest.get("campaign_id") != campaign_id:
        raise CampaignCommitmentError("Manifest campaign_id mismatch")
    if manifest.get("provider_identifier") != target.provider_identifier:
        raise CampaignCommitmentError("Manifest provider_identifier mismatch")
    if manifest.get("campaign_target") != target.to_mapping():
        raise CampaignCommitmentError("Manifest campaign_target mismatch")
    if manifest.get("prospective_replay_status") != p_status:
        raise CampaignCommitmentError("Manifest prospective_replay_status mismatch")
    if manifest.get("anchor_at") != summary.get("anchor_at"):
        raise CampaignCommitmentError("Manifest anchor_at mismatch")
    if manifest.get("candidate_offsets_seconds") != list(FROZEN_CANDIDATE_OFFSETS_SECONDS):
        raise CampaignCommitmentError("Manifest candidate_offsets_seconds mismatch")
    if manifest.get("attempt_window_seconds") != ATTEMPT_WINDOW_SECONDS:
        raise CampaignCommitmentError("Manifest attempt_window_seconds mismatch")
    if manifest.get("expected_tasks_per_fixture") != EXPECTED_TASKS_PER_FIXTURE:
        raise CampaignCommitmentError("Manifest expected_tasks_per_fixture mismatch")
    if manifest.get("minimum_fixtures_for_interpretation") != MINIMUM_FIXTURES_FOR_INTERPRETATION:
        raise CampaignCommitmentError("Manifest minimum_fixtures_for_interpretation mismatch")
    if manifest.get("interpretation_eligible") is not expected_eligible:
        raise CampaignCommitmentError("Manifest interpretation_eligible mismatch")

    m_commitment = manifest.get("commitment")
    if not isinstance(m_commitment, dict) or m_commitment != {
        "campaign_commitment_status": "UNFROZEN_LOCAL_PLAN",
        "prospective_claim_authorized": False,
        "local_anchor_is_not_trusted_creation_time_proof": True,
        "tracked_commitment_required_before_first_window": True,
        "commitment_deadline_at": serialize_utc(min_window_open),
    }:
        raise CampaignCommitmentError("Manifest commitment object mismatch")

    m_task_ident = manifest.get("task_identity")
    if not isinstance(m_task_ident, dict) or m_task_ident != {
        "algorithm": "SHA256_CANONICAL_JSON_PREFIX_24",
        "campaign_id_fields": [
            "provider_identifier",
            "prospective_replay_status",
            "source_qualification_sha256",
            "source",
            "bookmaker_identifier",
            "capture_method",
            "anchor_at",
            "candidate_offsets_seconds",
            "attempt_window_seconds",
            "stage_5b2_protocol_sha256",
            "campaign_protocol_sha256",
            "sorted_fixtures",
        ],
        "task_id_fields": [
            "campaign_id",
            "fixture_identifier",
            "market_id",
            "offset_seconds_before_kickoff",
            "scheduled_at",
            "source",
            "bookmaker_identifier",
            "capture_method",
        ],
    }:
        raise CampaignCommitmentError("Manifest task_identity object mismatch")

    if manifest.get("deterministic_ordering") != [
        "scheduled_at",
        "fixture_identifier",
        "market_id",
        "offset_seconds_before_kickoff",
        "task_id",
    ]:
        raise CampaignCommitmentError("Manifest deterministic_ordering mismatch")

    if manifest.get("market_registry") != market_registry_snapshot():
        raise CampaignCommitmentError("Manifest market_registry mismatch")
    if manifest.get("model_status_registry") != model_status_snapshot():
        raise CampaignCommitmentError("Manifest model_status_registry mismatch")

    if manifest.get("selected_offset_seconds") is not None:
        raise CampaignCommitmentError("Manifest selected_offset_seconds must be null")
    if manifest.get("selection_authorized") is not False:
        raise CampaignCommitmentError("Manifest selection_authorized must be false")
    if manifest.get("production_approval_authorized") is not False:
        raise CampaignCommitmentError("Manifest production_approval_authorized must be false")

    m_inputs = manifest.get("inputs")
    if not isinstance(m_inputs, dict) or set(m_inputs.keys()) != {
        "source_qualification",
        "fixtures",
        "stage_5b2_protocol",
        "campaign_protocol",
    }:
        raise CampaignCommitmentError("Manifest inputs object invalid")

    m_outputs = manifest.get("outputs")
    if not isinstance(m_outputs, dict) or set(m_outputs.keys()) != {"tasks", "summary"}:
        raise CampaignCommitmentError("Manifest outputs keys invalid")

    t_out = m_outputs["tasks"]
    if (
        t_out.get("relative_name") != STAGE_5B3_TASKS_FILENAME
        or t_out.get("byte_size") != len(tasks_raw)
        or t_out.get("sha256") != sha256_bytes(tasks_raw)
        or t_out.get("rows") != len(task_rows)
    ):
        raise CampaignCommitmentError("Manifest tasks output identity mismatch")

    s_out = m_outputs["summary"]
    if (
        s_out.get("relative_name") != STAGE_5B3_SUMMARY_FILENAME
        or s_out.get("byte_size") != len(summary_raw)
        or s_out.get("sha256") != sha256_bytes(summary_raw)
        or s_out.get("rows") != 1
    ):
        raise CampaignCommitmentError("Manifest summary output identity mismatch")

    m_summary_acc = manifest.get("summary_accounting")
    if not isinstance(m_summary_acc, dict) or m_summary_acc != {
        "fixture_count": len(fixture_ids),
        "task_count": len(task_rows),
        "expected_task_count": len(fixture_ids) * EXPECTED_TASKS_PER_FIXTURE,
        "interpretation_eligible": expected_eligible,
    }:
        raise CampaignCommitmentError("Manifest summary_accounting mismatch")

    if manifest.get("no_production_approval") != "Stage 5B3 is scheduling evidence only.":
        raise CampaignCommitmentError("Manifest no_production_approval mismatch")

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

    return ValidatedStage5B3Bundle(
        campaign_id=campaign_id,
        target=target,
        prospective_replay_status=p_status,
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
    clean_sha = validate_git_sha(generator_git_sha, "generator_git_sha")

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
            "manifest": bundle.manifest_identity,
            "summary": bundle.summary_identity,
            "tasks": bundle.tasks_identity,
        },
        upstream_protocols={
            "stage_5b3_protocol": stage_5b3_proto_ident,
            "stage_5b4_protocol": stage_5b4_proto_ident,
        },
        generator_git_sha=clean_sha,
        timing_authority=dict(TIMING_AUTHORITY_CONTRACT),
        selected_offset_seconds=None,
        selection_authorized=False,
        production_approval_authorized=False,
        market_statuses={
            "HOME_WIN_EITHER_HALF": "DISABLED",
            "AWAY_WIN_EITHER_HALF": "DISABLED",
        },
        safety=dict(GENERATED_SAFETY_CONTRACT),
        no_production_approval=NO_PRODUCTION_APPROVAL_STATEMENT,
    )


def validate_declaration_mapping(
    payload: Mapping[str, Any],
    *,
    expected_path: Path | None = None,
) -> CommitmentDeclaration:
    if not isinstance(payload, Mapping):
        raise CampaignCommitmentError("Declaration payload must be a JSON object")

    if set(payload.keys()) != EXPECTED_DECLARATION_KEYS:
        raise CampaignCommitmentError(
            "Declaration keys differ from exact Stage 5B4 schema"
        )

    if payload.get("safety") != GENERATED_SAFETY_CONTRACT:
        raise CampaignCommitmentError(
            "Declaration safety contract drifted from exact expectation"
        )
    payload_clean = dict(payload)
    payload_clean.pop("safety")
    assert_no_forbidden_fields(payload_clean, "Declaration")

    if _assert_int(payload["schema_version"], "Declaration schema_version") != 1:
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
    if not isinstance(t_map, Mapping) or set(t_map.keys()) != {
        "provider_identifier",
        "source",
        "bookmaker_identifier",
        "capture_method",
    }:
        raise CampaignCommitmentError("campaign_target must be an exact object")
    target = CampaignTarget(
        provider_identifier=_assert_str(t_map["provider_identifier"], "target.provider"),
        source=_assert_str(t_map["source"], "target.source"),
        bookmaker_identifier=_assert_str(t_map["bookmaker_identifier"], "target.bookmaker"),
        capture_method=_assert_str(t_map["capture_method"], "target.method"),
    )

    p_status = _assert_str(
        payload["prospective_replay_status"], "prospective_replay_status"
    )
    if p_status not in PERMITTED_PROSPECTIVE_REPLAY_STATUSES:
        raise CampaignCommitmentError(f"prospective_replay_status {p_status} not permitted")

    f_count = _assert_int(payload["fixture_count"], "fixture_count")
    t_count = _assert_int(payload["task_count"], "task_count")
    if f_count <= 0 or t_count <= 0:
        raise CampaignCommitmentError("fixture_count and task_count must be positive")
    if t_count != f_count * EXPECTED_TASKS_PER_FIXTURE:
        raise CampaignCommitmentError(
            f"task_count {t_count} must equal fixture_count {f_count} * {EXPECTED_TASKS_PER_FIXTURE}"
        )

    sb_map = payload["source_bundle"]
    if not isinstance(sb_map, Mapping) or set(sb_map.keys()) != {"manifest", "summary", "tasks"}:
        raise CampaignCommitmentError("source_bundle must contain tasks, summary, manifest")

    tasks_sb = sb_map["tasks"]
    if not isinstance(tasks_sb, Mapping) or set(tasks_sb.keys()) != {"relative_name", "byte_size", "sha256", "rows"}:
        raise CampaignCommitmentError("source_bundle.tasks schema invalid")
    if tasks_sb.get("relative_name") != STAGE_5B3_TASKS_FILENAME:
        raise CampaignCommitmentError("source_bundle.tasks filename mismatch")
    if tasks_sb.get("rows") != t_count:
        raise CampaignCommitmentError("source_bundle.tasks rows mismatch")

    summary_sb = sb_map["summary"]
    if not isinstance(summary_sb, Mapping) or set(summary_sb.keys()) != {"relative_name", "byte_size", "sha256", "rows"}:
        raise CampaignCommitmentError("source_bundle.summary schema invalid")
    if summary_sb.get("relative_name") != STAGE_5B3_SUMMARY_FILENAME:
        raise CampaignCommitmentError("source_bundle.summary filename mismatch")
    if summary_sb.get("rows") != 1:
        raise CampaignCommitmentError("source_bundle.summary rows mismatch")

    manifest_sb = sb_map["manifest"]
    if not isinstance(manifest_sb, Mapping) or set(manifest_sb.keys()) != {"relative_name", "byte_size", "sha256", "rows"}:
        raise CampaignCommitmentError("source_bundle.manifest schema invalid")
    if manifest_sb.get("relative_name") != STAGE_5B3_MANIFEST_FILENAME:
        raise CampaignCommitmentError("source_bundle.manifest filename mismatch")
    if manifest_sb.get("rows") != 1:
        raise CampaignCommitmentError("source_bundle.manifest rows mismatch")

    source_bundle = {
        k: FileIdentity(
            relative_name=_assert_str(v["relative_name"], f"source_bundle.{k}.name"),
            byte_size=_assert_int(v["byte_size"], f"source_bundle.{k}.size"),
            sha256=validate_sha256(v["sha256"], f"source_bundle.{k}.sha256"),
            rows=_assert_int(v["rows"], f"source_bundle.{k}.rows"),
        )
        for k, v in sb_map.items()
    }

    up_map = payload["upstream_protocols"]
    if not isinstance(up_map, Mapping) or set(up_map.keys()) != {"stage_5b3_protocol", "stage_5b4_protocol"}:
        raise CampaignCommitmentError("upstream_protocols must contain stage_5b3_protocol and stage_5b4_protocol")

    p5b3_up = up_map["stage_5b3_protocol"]
    if not isinstance(p5b3_up, Mapping) or set(p5b3_up.keys()) != {"relative_name", "byte_size", "sha256"}:
        raise CampaignCommitmentError("upstream_protocols.stage_5b3_protocol schema invalid")
    if p5b3_up.get("relative_name") != DEFAULT_STAGE_5B3_PROTOCOL_PATH.name:
        raise CampaignCommitmentError("upstream_protocols.stage_5b3_protocol relative_name mismatch")

    p5b4_up = up_map["stage_5b4_protocol"]
    if not isinstance(p5b4_up, Mapping) or set(p5b4_up.keys()) != {"relative_name", "byte_size", "sha256"}:
        raise CampaignCommitmentError("upstream_protocols.stage_5b4_protocol schema invalid")
    if p5b4_up.get("relative_name") != DEFAULT_PROTOCOL_PATH.name:
        raise CampaignCommitmentError("upstream_protocols.stage_5b4_protocol relative_name mismatch")

    upstream_protocols = {
        k: FileIdentity(
            relative_name=_assert_str(v["relative_name"], f"upstream_protocols.{k}.name"),
            byte_size=_assert_int(v["byte_size"], f"upstream_protocols.{k}.size"),
            sha256=validate_sha256(v["sha256"], f"upstream_protocols.{k}.sha256"),
            rows=None,
        )
        for k, v in up_map.items()
    }

    gen_sha = validate_git_sha(payload["generator_git_sha"], "generator_git_sha")

    if payload["timing_authority"] != TIMING_AUTHORITY_CONTRACT:
        raise CampaignCommitmentError("Declaration timing_authority drifted from exact contract")

    if payload["selected_offset_seconds"] is not None:
        raise CampaignCommitmentError("selected_offset_seconds must be null")
    if payload["selection_authorized"] is not False:
        raise CampaignCommitmentError("selection_authorized must be false")
    if payload["production_approval_authorized"] is not False:
        raise CampaignCommitmentError("production_approval_authorized must be false")

    m_statuses = payload["market_statuses"]
    if not isinstance(m_statuses, dict) or m_statuses != {
        "HOME_WIN_EITHER_HALF": "DISABLED",
        "AWAY_WIN_EITHER_HALF": "DISABLED",
    }:
        raise CampaignCommitmentError("Declaration market_statuses must both be DISABLED")

    if payload["no_production_approval"] != NO_PRODUCTION_APPROVAL_STATEMENT:
        raise CampaignCommitmentError("Declaration no_production_approval mismatch")

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
        campaign_id=declaration.campaign_id,
        commitment_sha256=c_sha,
        commitment_deadline_at=declaration.commitment_deadline_at,
        server_observed_at=server_observed_at,
        prospective_timing_qualified=qualified,
    )
