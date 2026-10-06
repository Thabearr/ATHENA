"""Strict transport DTOs for the versioned local preview/admission API."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator


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


__all__ = [
    "AdmissionBlockerDTO",
    "ErrorDTO",
    "RunAdmissionAcceptedDTO",
    "RunAdmissionDTO",
    "RunPreviewIntentDTO",
    "RunPreviewResponseDTO",
]
