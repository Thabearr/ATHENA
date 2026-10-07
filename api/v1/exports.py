"""Server-owned local export identity routes."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.schemas import ExportRecordDTO
from api.v1.common import error_response, invalid_response, parse_export_request
from services.athena_read_service import ReadServiceError


router = APIRouter(prefix="/api/v1", tags=["exports"])


@router.post("/exports", response_model=ExportRecordDTO, status_code=201)
async def create_export(request: Request):
    try:
        export_request = await parse_export_request(request)
        record = request.app.state.read_service.create_export(export_request)
        return ExportRecordDTO.model_validate(record.to_dict())
    except ValueError as exc:
        code = str(exc)
        return invalid_response(code if code in {"INVALID_EXPORT_REQUEST", "INVALID_EXPORT_KIND"}
                                else "INVALID_EXPORT_REQUEST")
    except ReadServiceError as exc:
        return error_response(exc)


@router.get("/exports/{export_id}", response_model=ExportRecordDTO)
def get_export(export_id: str, request: Request):
    try:
        record = request.app.state.read_service.get_export(export_id)
        return ExportRecordDTO.model_validate(record.to_dict())
    except ReadServiceError as exc:
        return error_response(exc)


__all__ = ["router"]
