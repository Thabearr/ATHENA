import os
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from build_acca import AccaBuilder
from workers.fotmob_advanced_scraper import FotMobAdvancedScraper
from api.athenizer import router as athenizer_router

app = FastAPI(title="ATHENA Desktop API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(athenizer_router)

from typing import Optional

class GenerateRequest(BaseModel):
    days: int = 1
    folds: int = 20
    league: Optional[str] = None
    strict: bool = True

@app.get("/api/status")
def get_status():
    """Return basic health and stats of the ATHENA engine."""
    weights_path = "config/model_weights.json"
    weights_exist = os.path.exists(weights_path)
    return {
        "status": "online",
        "engine": "ATHENA v3.0",
        "weights_loaded": weights_exist
    }

@app.get("/api/leagues")
def get_available_leagues(days: int = Query(1, ge=1, le=14)):
    """Fetch unique leagues available in the upcoming days."""
    try:
        scraper = FotMobAdvancedScraper()
        matches = scraper.fetch_upcoming_matches(days_ahead=days)
        
        # Extract unique leagues
        leagues = sorted(list(set([m['league'] for m in matches if m.get('league')])))
        return {"leagues": leagues}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fixtures")
def get_upcoming_fixtures(days: int = Query(1, ge=1, le=14)):
    """Fetch raw upcoming fixtures for the next N days."""
    try:
        scraper = FotMobAdvancedScraper()
        matches = scraper.fetch_upcoming_matches(days_ahead=days)
        return {"fixtures": matches}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate")
def generate_acca(req: GenerateRequest):
    """Generate an accumulator using the ATHENA pipeline."""
    try:
        builder = AccaBuilder()
        acca = builder.build(
            days=req.days,
            fold_size=req.folds,
            strict=req.strict,
            league=req.league
        )
        if not acca.get("success"):
            raise HTTPException(status_code=400, detail=acca.get("error", "Generation failed"))
        return acca
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ExportRequest(BaseModel):
    bookmaker: str
    acca_data: dict

@app.post("/api/export_code")
def export_booking_code(req: ExportRequest):
    """Trigger the Playwright automator to generate a booking code."""
    try:
        from workers.bookie_automator import BookieAutomator
        automator = BookieAutomator()
        code = automator.generate_booking_code(req.bookmaker, req.acca_data)
        if not code or "NO_LEGS" in code or "UNSUPPORTED" in code:
            raise HTTPException(status_code=400, detail=code)
        return {"success": True, "code": code}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8500)
