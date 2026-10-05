import os
import sys
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi import FastAPI, APIRouter, HTTPException, Query
from pydantic import BaseModel
# Retained development API only. The trusted shell uses api.app_factory.
# Provider implementations and legacy routers are imported only on explicit use.
router = APIRouter()


def AccaBuilder():
    from services.legacy_acca_builder_compat import AccaBuilder
    return AccaBuilder()


def FotMobAdvancedScraper():
    from workers.fotmob_advanced_scraper import FotMobAdvancedScraper
    return FotMobAdvancedScraper()


from typing import Optional

_CACHE_TTL_SECONDS = 300
_fixtures_cache = {}


def _get_cached_fixtures(days: int):
    cache_key = f"days:{days}"
    now = time.time()
    cached = _fixtures_cache.get(cache_key)
    if cached and now - cached["timestamp"] < _CACHE_TTL_SECONDS:
        return cached["data"]

    scraper = FotMobAdvancedScraper()
    matches = scraper.fetch_upcoming_matches(days_ahead=days)
    _fixtures_cache[cache_key] = {"timestamp": now, "data": matches}
    return matches

class GenerateRequest(BaseModel):
    days: int = 1
    folds: int = 20
    league: Optional[str] = None
    strict: bool = True

@router.get("/api/status")
def get_status():
    """Compatibility liveness has no model/provider readiness authority."""
    return {"status": "deprecated_compatibility", "health_endpoint": "/api/v1/health",
            "model_readiness": "unproven", "provider_authority": False}

@router.get("/api/leagues")
def get_available_leagues(days: int = Query(1, ge=1, le=14)):
    """Fetch unique leagues available in the upcoming days."""
    try:
        matches = _get_cached_fixtures(days)
        
        # Extract unique leagues
        leagues = sorted(list(set([m['league'] for m in matches if m.get('league')])))
        return {"leagues": leagues}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/fixtures")
def get_upcoming_fixtures(days: int = Query(1, ge=1, le=14)):
    """Fetch raw upcoming fixtures for the next N days."""
    try:
        matches = _get_cached_fixtures(days)
        return {"fixtures": matches}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/generate")
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

_compatibility_app = None


def create_compatibility_app(*, development_compatibility=False):
    if development_compatibility is not True:
        raise ValueError("explicit development compatibility is required")
    from api.athenizer import router as athenizer_router
    from api.export import router as export_router
    legacy = FastAPI(title="ATHENA retained development compatibility API")
    legacy.include_router(router)
    legacy.include_router(athenizer_router)
    legacy.include_router(export_router)
    # Original screens remain available only on this explicit development app.
    # The installed/supported factory never mounts these compatibility assets.
    from pathlib import Path
    from fastapi.responses import FileResponse
    ui = Path(__file__).resolve().parents[1] / "ui"
    for route, filename in (("/", "legacy-index.html"), ("/app.js", "legacy-app.js"), ("/styles.css", "styles.css")):
        def make_asset(name):
            def serve():
                return FileResponse(ui / name)
            return serve
        legacy.add_api_route(route, make_asset(filename), methods=["GET"])
    return legacy


def __getattr__(name):
    # Existing development imports explicitly request this compatibility object.
    # Merely importing api.server performs no provider or API construction.
    if name == "app":
        global _compatibility_app
        if _compatibility_app is None:
            _compatibility_app = create_compatibility_app(development_compatibility=True)
        return _compatibility_app
    raise AttributeError(name)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_compatibility_app(development_compatibility=True), host="127.0.0.1", port=0)
