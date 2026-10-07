"""Transport routes for provider-free run reads and cooperative cancel intent."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.schemas import (
    CancelIntentDTO,
    RunEventsPageDTO,
    RunHistoryPageDTO,
    RunReceiptDTO,
    RunSnapshotDTO,
)
from api.v1.common import error_response, invalid_response, parse_cursor, parse_uint, query_values
from services.athena_read_service import ReadServiceError


router = APIRouter(prefix="/api/v1", tags=["runs"])
_STATES = {"QUEUED", "RUNNING", "CANCEL_REQUESTED", "TERMINAL", "CANCELLED", "INTERRUPTED"}
_PROFILES = {"MAIN", "SHADOW"}
_QUERY_ERRORS = {"INVALID_CURSOR", "INVALID_LIMIT", "INVALID_FILTER"}


def _query_error(exc: ValueError) -> JSONResponse:
    code = str(exc)
    return invalid_response(code if code in _QUERY_ERRORS else "INVALID_FILTER")


@router.get("/runs/{run_id}", response_model=RunSnapshotDTO)
def get_run_snapshot(run_id: str, request: Request):
    try:
        result = request.app.state.read_service.get_run_snapshot(run_id)
        return RunSnapshotDTO.model_validate(result.to_dict())
    except ReadServiceError as exc:
        return error_response(exc)


@router.get("/runs/{run_id}/events", response_model=RunEventsPageDTO)
def get_run_events(run_id: str, request: Request):
    try:
        query = query_values(request, {"after_sequence", "limit"})
        after_sequence = parse_uint(query.get("after_sequence"), default=0, name="after_sequence",
                                    minimum=0, maximum=2**63 - 1)
        limit = parse_uint(query.get("limit"), default=50, name="limit", minimum=1, maximum=200)
        page = request.app.state.read_service.list_run_events(
            run_id, after_sequence=after_sequence, limit=limit
        )
        events = [event.to_dict() for event in page.events]
        next_cursor = events[-1]["sequence"] if events else None
        return RunEventsPageDTO.model_validate({"events": events, "next_cursor": next_cursor})
    except ValueError as exc:
        return _query_error(exc)
    except ReadServiceError as exc:
        return error_response(exc)


@router.get("/runs/{run_id}/receipt", response_model=RunReceiptDTO)
def get_run_receipt(run_id: str, request: Request):
    try:
        result = request.app.state.read_service.get_verified_receipt(run_id)
        return RunReceiptDTO.model_validate(result.to_dict())
    except ReadServiceError as exc:
        return error_response(exc)


@router.post("/runs/{run_id}/cancel", response_model=CancelIntentDTO)
def cancel_run(run_id: str, request: Request):
    try:
        result = request.app.state.read_service.request_cancel(run_id)
        return CancelIntentDTO.model_validate(result.to_dict())
    except ReadServiceError as exc:
        return error_response(exc)


@router.get("/runs", response_model=RunHistoryPageDTO)
def list_runs(request: Request):
    try:
        query = query_values(request, {"cursor", "limit", "state", "profile"})
        cursor = parse_cursor(query.get("cursor"))
        limit = parse_uint(query.get("limit"), default=50, name="limit", minimum=1, maximum=100)
        state = query.get("state")
        profile = query.get("profile")
        if state is not None and state not in _STATES:
            raise ValueError("INVALID_FILTER")
        if profile is not None and profile not in _PROFILES:
            raise ValueError("INVALID_FILTER")
        page = request.app.state.read_service.list_runs(
            cursor=cursor, limit=limit, state=state, profile=profile
        )
        return RunHistoryPageDTO.model_validate({
            "items": [item.to_dict() for item in page.items],
            "next_cursor": page.next_cursor,
        })
    except ValueError as exc:
        return _query_error(exc)
    except ReadServiceError as exc:
        return error_response(exc)


__all__ = ["router"]
