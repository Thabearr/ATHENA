"""Strict transport DTOs for the versioned local preview/admission API."""
from __future__ import annotations

from datetime import date
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator


_SHA256_TEXT = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


class StrictTransportDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class RunPreviewIntentDTO(StrictTransportDTO):
    dates: list[StrictStr] = Field(min_length=1, max_length=7)
    target_legs: StrictInt = Field(ge=1, le=50)
    target_total_odds: None
    bookie: Literal["sportybet"]
    profile: Literal["main", "shadow"]
    acquire_sources: StrictBool
    create_share_code: StrictBool

    @field_validator("dates")
    @classmethod
    def validate_concrete_dates(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("dates must be unique")
        for value in values:
            if len(value) != 10 or value[4:5] != "-" or value[7:8] != "-" or not value.isascii():
                raise ValueError("date must be canonical YYYY-MM-DD")
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("date must be canonical YYYY-MM-DD") from exc
            if parsed.isoformat() != value:
                raise ValueError("date must be canonical YYYY-MM-DD")
        return values


class RunAdmissionDTO(StrictTransportDTO):
    preview_id: StrictStr
    execution_envelope_sha256: StrictStr
    idempotency_key: StrictStr

    @field_validator("execution_envelope_sha256")
    @classmethod
    def validate_envelope_digest(cls, value: str) -> str:
        if type(value) is not str or _SHA256_TEXT.fullmatch(value) is None:
            raise ValueError("execution_envelope_sha256 must be lowercase SHA-256 text")
        return value


class ErrorDTO(StrictTransportDTO):
    code: StrictStr
    safe_message: StrictStr
    retry_class: Literal["never", "after_refresh", "after_delay"]
    run_id: StrictStr | None = None
    stage: StrictStr | None = None
    diagnostic_id: StrictStr | None = None


class AdmissionBlockerDTO(StrictTransportDTO):
    contract: Literal["AdmissionBlocker"]
    code: Literal["REQUEST_AUTHORITY_MISMATCH"]
    operation: Literal["ACQUIRE_SOURCES", "CREATE_SHARE_CODE"]
    capability: Literal["provider_acquisition", "share_code_generation"]
    reason: StrictStr


class RunPreviewResponseDTO(StrictTransportDTO):
    preview_id: StrictStr
    request_sha256: StrictStr
    execution_envelope_sha256: StrictStr
    preview_sha256: StrictStr
    dates: list[StrictStr]
    target_legs: StrictInt
    target_total_odds: None
    bookie: Literal["sportybet"]
    profile: Literal["main", "shadow"]
    acquire_sources: StrictBool
    create_share_code: StrictBool
    place_wager: Literal[False]
    allowed_operations: list[Literal["ACQUIRE_SOURCES", "CREATE_SHARE_CODE"]]
    denied_operations: list[Literal["ACQUIRE_SOURCES", "CREATE_SHARE_CODE"]]
    blockers: list[AdmissionBlockerDTO]
    expires_at: StrictStr
    source_identity: dict[str, Any]
    preview_scope: Literal["LOCAL_READ_ONLY_NO_EXECUTION_AUTHORITY"]


class RunAdmissionAcceptedDTO(StrictTransportDTO):
    run_id: StrictStr
    admission_state: Literal["admitted", "idempotent_replay"]


RunStateDTO = Literal["QUEUED", "RUNNING", "CANCEL_REQUESTED", "TERMINAL", "CANCELLED", "INTERRUPTED"]
RunProfileDTO = Literal["MAIN", "SHADOW"]
ReceiptStateDTO = Literal["NOT_PRODUCED", "VERIFIED", "INTEGRITY_BLOCKED", "UNKNOWN"]


class RunSnapshotDTO(StrictTransportDTO):
    run_id: StrictStr
    state: RunStateDTO
    state_version: StrictInt | None
    created_at: StrictStr | None
    updated_at: StrictStr | None
    last_proven_stage: StrictStr | None
    counts: dict[StrictStr, StrictInt | None] | None
    target_legs: StrictInt | None
    selected_leg_count: StrictInt | None
    shortfall: StrictInt | None
    execution_state: StrictStr | None
    business_result: StrictStr | None
    delivery_state: StrictStr | None
    receipt_state: ReceiptStateDTO
    request_identity_ref: StrictStr | None
    release_identity_ref: StrictStr | None


class RunEventPayloadDTO(StrictTransportDTO):
    stage: StrictStr | None = None
    state: RunStateDTO | None = None
    business_result: StrictStr | None = None
    selected_leg_count: StrictInt | None = None
    shortfall: StrictInt | None = None
    diagnostic_id: StrictStr | None = None


class RunEventDTO(StrictTransportDTO):
    sequence: StrictInt
    kind: Literal["STATE_CHANGED", "STAGE_STARTED", "STAGE_COMPLETED", "BUSINESS_RESULT", "CANCEL_REQUESTED", "DIAGNOSTIC"]
    state_version: StrictInt | None
    observed_at: StrictStr
    payload: RunEventPayloadDTO


class RunEventsPageDTO(StrictTransportDTO):
    events: list[RunEventDTO]
    next_cursor: StrictInt | None


class RunReceiptDTO(StrictTransportDTO):
    receipt_sha256: StrictStr
    status: StrictStr
    observed_at: StrictStr
    exact_commit_sha: StrictStr
    request_identity_ref: StrictStr
    target_legs: StrictInt
    selected_leg_count: StrictInt
    shortfall: StrictInt
    delivery_state: Literal["NOT_REQUESTED", "NOT_PRODUCED", "RESULT_RECORDED"]
    wager_placed: Literal[False]


class RunHistoryEntryDTO(StrictTransportDTO):
    run_id: StrictStr
    state: RunStateDTO
    state_version: StrictInt | None
    created_at: StrictStr | None
    updated_at: StrictStr | None
    profile: RunProfileDTO | None


class RunHistoryPageDTO(StrictTransportDTO):
    items: list[RunHistoryEntryDTO]
    next_cursor: StrictStr | None


class RetainedFixtureDTO(StrictTransportDTO):
    fixture_id: StrictStr
    kickoff_at: StrictStr
    competition_id: StrictStr
    competition_name: StrictStr
    home: StrictStr
    away: StrictStr
    scope: Literal["club", "international"]


class RetainedFixturePageDTO(StrictTransportDTO):
    items: list[RetainedFixtureDTO]
    next_cursor: StrictStr | None


class CancelIntentDTO(StrictTransportDTO):
    run_id: StrictStr
    disposition: Literal["requested", "already_requested", "already_terminal"]
    state: RunStateDTO
    state_version: StrictInt | None


class ExportRequestDTO(StrictTransportDTO):
    run_id: StrictStr | None = None
    receipt_sha256: StrictStr | None = None
    kind: StrictStr
    redaction_mode: Literal["standard", "strict"] = "standard"

    @field_validator("receipt_sha256")
    @classmethod
    def validate_receipt_identity(cls, value: str | None) -> str | None:
        if value is not None and (type(value) is not str or _SHA256_TEXT.fullmatch(value) is None):
            raise ValueError("receipt identity must be lowercase SHA-256 text")
        return value

    @field_validator("run_id")
    @classmethod
    def validate_export_run_identity(cls, value: str | None) -> str | None:
        if value is not None and (type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value, re.ASCII)):
            raise ValueError("run identity is invalid")
        return value

    @field_validator("kind")
    @classmethod
    def validate_export_kind(cls, value: str) -> str:
        if type(value) is not str or value not in {"run_summary_json", "verified_receipt_json"}:
            raise ValueError("export kind is unsupported")
        return value

    @model_validator(mode="after")
    def validate_export_source_identity(self):
        if (self.run_id is None) == (self.receipt_sha256 is None):
            raise ValueError("exactly one export source identity is required")
        return self


class ExportRecordDTO(StrictTransportDTO):
    export_id: StrictStr
    kind: Literal["run_summary_json", "verified_receipt_json"]
    redaction_mode: Literal["standard", "strict"]
    run_id: StrictStr | None
    receipt_sha256: StrictStr | None
    logical_path: StrictStr
    created_at: StrictStr
    sha256: StrictStr
    byte_count: StrictInt


__all__ = [
    "AdmissionBlockerDTO",
    "CancelIntentDTO",
    "ErrorDTO",
    "ExportRecordDTO",
    "ExportRequestDTO",
    "RetainedFixtureDTO",
    "RetainedFixturePageDTO",
    "RunAdmissionAcceptedDTO",
    "RunAdmissionDTO",
    "RunEventDTO",
    "RunEventPayloadDTO",
    "RunEventsPageDTO",
    "RunHistoryEntryDTO",
    "RunHistoryPageDTO",
    "RunPreviewIntentDTO",
    "RunPreviewResponseDTO",
    "RunReceiptDTO",
    "RunSnapshotDTO",
]
