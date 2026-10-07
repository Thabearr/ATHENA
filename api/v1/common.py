"""Strict transport parsing and safe error mapping for versioned reads."""
from __future__ import annotations

from datetime import date
import json
import re
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from api.schemas import ErrorDTO, ExportRequestDTO
from services.athena_read_service import ExportRequest, ReadServiceError


_CANONICAL_UINT = re.compile(r"^(?:0|[1-9][0-9]*)$", re.ASCII)
_CURSOR_TEXT = re.compile(r"^[A-Za-z0-9_-]{1,128}$", re.ASCII)
_MAX_BODY_BYTES = 16_384


class _InvalidJSON(ValueError):
    pass


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidJSON("duplicate JSON member")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise _InvalidJSON("non-finite JSON number")


def error_response(exc: ReadServiceError) -> JSONResponse:
    payload = ErrorDTO(
        code=exc.code,
        safe_message=exc.safe_message,
        retry_class=exc.retry_class,
        diagnostic_id=exc.diagnostic_id,
    )
    return JSONResponse(payload.model_dump(exclude_none=True), status_code=exc.status_code)


def invalid_response(code: str) -> JSONResponse:
    definitions = {
        "INVALID_CURSOR": ("The cursor is invalid.", "never"),
        "INVALID_LIMIT": ("The page limit is invalid.", "never"),
        "INVALID_FILTER": ("The filter is invalid.", "never"),
        "INVALID_EXPORT_REQUEST": ("The export request is invalid.", "never"),
        "INVALID_EXPORT_KIND": ("The export kind is not supported.", "never"),
    }
    message, retry = definitions.get(code, definitions["INVALID_FILTER"])
    payload = ErrorDTO(code=code, safe_message=message, retry_class=retry)
    return JSONResponse(payload.model_dump(exclude_none=True), status_code=422)


def query_values(request: Request, allowed: set[str]) -> dict[str, str]:
    pairs = request.query_params.multi_items()
    values: dict[str, str] = {}
    for key, value in pairs:
        if key not in allowed or key in values:
            raise ValueError("INVALID_FILTER")
        values[key] = value
    return values


def parse_uint(raw: str | None, *, default: int, name: str, minimum: int, maximum: int) -> int:
    if raw is None:
        return default
    code = "INVALID_CURSOR" if name == "after_sequence" else "INVALID_LIMIT"
    if _CANONICAL_UINT.fullmatch(raw) is None or len(raw) > len(str(maximum)):
        raise ValueError(code)
    value = int(raw)
    if value < minimum or value > maximum:
        raise ValueError(code)
    return value


def parse_cursor(raw: str | None) -> str | None:
    if raw is None:
        return None
    if _CURSOR_TEXT.fullmatch(raw) is None:
        raise ValueError("INVALID_CURSOR")
    return raw


def parse_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except (TypeError, ValueError):
        raise ValueError("INVALID_FILTER") from None
    if parsed.isoformat() != raw:
        raise ValueError("INVALID_FILTER")
    return parsed


async def parse_export_request(request: Request) -> ExportRequest:
    content_types = request.headers.getlist("content-type")
    if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
        raise ValueError("INVALID_EXPORT_REQUEST")
    lengths = request.headers.getlist("content-length")
    if len(lengths) > 1 or (lengths and (not lengths[0].isascii() or not lengths[0].isdigit()
                                          or len(lengths[0]) > 10)):
        raise ValueError("INVALID_EXPORT_REQUEST")
    if lengths and int(lengths[0]) > _MAX_BODY_BYTES:
        raise ValueError("INVALID_EXPORT_REQUEST")
    raw_parts = []
    total = 0
    async for part in request.stream():
        total += len(part)
        if total > _MAX_BODY_BYTES:
            raise ValueError("INVALID_EXPORT_REQUEST")
        raw_parts.append(part)
    raw = b"".join(raw_parts)
    if len(raw) > _MAX_BODY_BYTES:
        raise ValueError("INVALID_EXPORT_REQUEST")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
        dto = ExportRequestDTO.model_validate(value)
    except (UnicodeDecodeError, json.JSONDecodeError, _InvalidJSON, ValidationError, TypeError, ValueError) as exc:
        errors = exc.errors() if isinstance(exc, ValidationError) else ()
        if any("kind" in error.get("loc", ()) and error.get("type") in {"value_error", "string_type"}
               for error in errors):
            raise ValueError("INVALID_EXPORT_KIND") from None
        raise ValueError("INVALID_EXPORT_REQUEST") from None
    return ExportRequest(
        run_id=dto.run_id,
        receipt_sha256=dto.receipt_sha256,
        kind=dto.kind,
        redaction_mode=dto.redaction_mode,
    )


def get_read_service(request: Request):
    return request.app.state.read_service
