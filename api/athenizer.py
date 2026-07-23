from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.betting_service import BettingService

router = APIRouter(prefix="/api/athenizer", tags=["Athenizer"])
betting_svc = BettingService()

class VetRequest(BaseModel):
    bookmaker: str
    booking_code: str

class SplitRequest(BaseModel):
    bookmaker: str
    booking_code: str
    split_count: int = 2

@router.post("/vet")
def vet_booking_code(req: VetRequest):
    """Vets a booking code from a bookmaker against ATHENA logic."""
    try:
        result = betting_svc.vet_code(req.bookmaker, req.booking_code)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to vet code"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/split")
def split_booking_code(req: SplitRequest):
    """Fetches a code and splits it into multiple smaller slips."""
    try:
        result = betting_svc.vet_code(req.bookmaker, req.booking_code)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to resolve code for splitting"))
        
        splits = betting_svc.split_slip(result, req.split_count)
        return {"success": True, "splits": splits}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
