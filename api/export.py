"""Audited bookmaker-export preparation API."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from workers.bookie_automator import BookieAutomator


router = APIRouter()


class ExportRequest(BaseModel):
    bookmaker: str
    acca_data: dict


@router.post("/api/export")
@router.post("/api/export_code", deprecated=True)
def prepare_bookmaker_export(req: ExportRequest):
    """Prepare a slip without claiming that a bookmaker registered it."""
    try:
        return BookieAutomator().prepare_export(req.bookmaker, req.acca_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


__all__ = ["ExportRequest", "prepare_bookmaker_export", "router"]
