"""Retained provider-free fixture browsing route."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.schemas import RetainedFixturePageDTO
from api.v1.common import error_response, invalid_response, parse_cursor, parse_date, parse_uint, query_values
from services.athena_read_service import ReadServiceError


router = APIRouter(prefix="/api/v1", tags=["fixtures"])


@router.get("/fixtures", response_model=RetainedFixturePageDTO)
def list_retained_fixtures(request: Request):
    try:
        query = query_values(request, {"cursor", "limit", "scope", "date_from", "date_to"})
        cursor = parse_cursor(query.get("cursor"))
        limit = parse_uint(query.get("limit"), default=50, name="limit", minimum=1, maximum=100)
        scope = query.get("scope")
        if scope is not None and scope not in {"club", "international"}:
            raise ValueError("INVALID_FILTER")
        date_from = parse_date(query.get("date_from"))
        date_to = parse_date(query.get("date_to"))
        page = request.app.state.read_service.list_retained_fixtures(
            cursor=cursor, limit=limit, scope=scope, date_from=date_from, date_to=date_to
        )
        return RetainedFixturePageDTO.model_validate({
            "items": [item.to_dict() for item in page.items],
            "next_cursor": page.next_cursor,
        })
    except ValueError as exc:
        code = str(exc)
        return invalid_response(code if code in {"INVALID_CURSOR", "INVALID_LIMIT", "INVALID_FILTER"}
                                else "INVALID_FILTER")
    except ReadServiceError as exc:
        return error_response(exc)


__all__ = ["router"]
