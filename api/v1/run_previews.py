"""HTTP adaptation for immutable run previews and fail-closed admission."""
from __future__ import annotations

import json
from typing import Any, Type

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from api.schemas import (
    ErrorDTO,
    RunAdmissionAcceptedDTO,
    RunAdmissionDTO,
    RunPreviewIntentDTO,
    RunPreviewResponseDTO,
)
from services.athena_preview_service import (
    AdmissionResult,
    AthenaPreviewAdmissionService,
    PreviewAdmissionError,
)


router = APIRouter(prefix="/api/v1")
_MAX_BODY_BYTES = 16_384


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON value")


def _error(code: str) -> PreviewAdmissionError:
    safe = {
        "INVALID_INTENT": (422, "Preview intent is invalid.", "never"),
        "TARGET_TOTAL_ODDS_NOT_SUPPORTED": (422, "target_total_odds is not supported.", "never"),
        "UNSUPPORTED_BOOKIE": (422, "Only the reviewed SportyBet adapter is supported.", "never"),
        "INVALID_DATE": (422, "Dates must be one through seven unique canonical dates.", "never"),
        "PREVIEW_DIGEST_MISMATCH": (409, "The preview identity did not match.", "never"),
        "DURABLE_RUN_STORE_UNAVAILABLE": (503, "Durable run admission is not available in this application.", "after_delay"),
        "CURRENT_AUTHORITY_UNAVAILABLE": (503, "Current request authority could not be verified.", "after_delay"),
    }
    status, message, retry = safe[code]
    return PreviewAdmissionError(status, code, message, retry)


async def _parse_dto(request: Request, dto_type: Type[BaseModel]) -> BaseModel:
    try:
        raw = await request.body()
        if len(raw) > _MAX_BODY_BYTES:
            raise ValueError("request body is too large")
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise _error("INVALID_INTENT") from None
    if type(value) is not dict:
        raise _error("INVALID_INTENT")
    if dto_type is RunPreviewIntentDTO and value.get("target_total_odds") is not None:
        raise _error("TARGET_TOTAL_ODDS_NOT_SUPPORTED")
    try:
        return dto_type.model_validate(value, strict=True)
    except ValidationError as exc:
        locations = {tuple(item.get("loc", ())) for item in exc.errors(include_url=False)}
        top_fields = {location[0] for location in locations if location}
        if "bookie" in top_fields:
            raise _error("UNSUPPORTED_BOOKIE") from None
        if dto_type is RunPreviewIntentDTO and "dates" in top_fields:
            raise _error("INVALID_DATE") from None
        if dto_type is RunAdmissionDTO and "execution_envelope_sha256" in top_fields:
            raise _error("PREVIEW_DIGEST_MISMATCH") from None
        raise _error("INVALID_INTENT") from None


def _service(request: Request) -> AthenaPreviewAdmissionService:
    service = getattr(request.app.state, "preview_admission_service", None)
    if type(service) is not AthenaPreviewAdmissionService:
        raise _error("CURRENT_AUTHORITY_UNAVAILABLE")
    return service


def _error_response(exc: PreviewAdmissionError) -> JSONResponse:
    payload = ErrorDTO(
        code=exc.code,
        safe_message=exc.safe_message,
        retry_class=exc.retry_class,
    )
    return JSONResponse(payload.model_dump(exclude_none=True), status_code=exc.status_code)


@router.post("/run-previews", status_code=200)
async def create_run_preview(request: Request):
    try:
        dto = await _parse_dto(request, RunPreviewIntentDTO)
        assert type(dto) is RunPreviewIntentDTO
        value = await run_in_threadpool(
            _service(request).preview,
            dates=dto.dates,
            target_legs=dto.target_legs,
            target_total_odds=dto.target_total_odds,
            bookie=dto.bookie,
            profile=dto.profile,
            acquire_sources=dto.acquire_sources,
            create_share_code=dto.create_share_code,
        )
        return RunPreviewResponseDTO.model_validate(value, strict=True).model_dump()
    except PreviewAdmissionError as exc:
        return _error_response(exc)
    except Exception:
        return _error_response(_error("CURRENT_AUTHORITY_UNAVAILABLE"))


@router.post("/runs", status_code=202)
async def admit_run(request: Request):
    try:
        dto = await _parse_dto(request, RunAdmissionDTO)
        assert type(dto) is RunAdmissionDTO
        result: AdmissionResult = await run_in_threadpool(
            _service(request).admit,
            preview_id=dto.preview_id,
            execution_envelope_sha256=dto.execution_envelope_sha256,
            idempotency_key=dto.idempotency_key,
        )
        payload = RunAdmissionAcceptedDTO(
            run_id=result.run_id,
            admission_state=result.disposition,
        )
        return JSONResponse(payload.model_dump(), status_code=202)
    except PreviewAdmissionError as exc:
        return _error_response(exc)
    except Exception:
        return _error_response(_error("DURABLE_RUN_STORE_UNAVAILABLE"))


__all__ = ["router"]
