"""Compliance router — the Compliance sub-agent's safety check on sales & marketing content."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from agents.attorney import check_compliance

router = APIRouter(prefix="/compliance", tags=["compliance"])


class CheckRequest(BaseModel):
    text: str
    kind: Optional[str] = "general"   # listing | email | text | flyer | general


@router.post("/check")
async def check(req: CheckRequest):
    if not req.text.strip():
        raise HTTPException(400, "Provide text to check")
    return await check_compliance(req.text, req.kind or "general")
