from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from agents.research import get_market_snapshot, run_cma, track_expired_listings, get_neighborhood_report

router = APIRouter(prefix="/market", tags=["market"])


class CMARequest(BaseModel):
    address: str
    city: Optional[str] = ""
    state: Optional[str] = ""
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    sqft: Optional[int] = None


@router.get("/snapshot/{area}")
async def market_snapshot(area: str):
    data = await get_market_snapshot(area)
    return data


@router.post("/cma")
async def cma_report(req: CMARequest):
    result = await run_cma(req.address, req.bedrooms, req.bathrooms, req.sqft,
                           req.city, req.state)
    return result


@router.get("/expired/{city}")
async def expired_listings(city: str):
    results = await track_expired_listings(city)
    return {"city": city, "expired_leads": results}


@router.get("/neighborhood-report/{neighborhood}")
async def neighborhood_report(neighborhood: str):
    report = await get_neighborhood_report(neighborhood)
    return {"neighborhood": neighborhood, "report": report}


SANTA_CLARA_AREAS = [
    "Willow Glen", "Los Gatos", "Saratoga", "Cupertino",
    "Sunnyvale", "Campbell", "Almaden Valley", "Evergreen",
    "Silver Creek", "Berryessa"
]


@router.get("/areas")
def list_areas():
    return {"areas": SANTA_CLARA_AREAS}
