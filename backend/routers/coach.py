"""Coach router — ARIA coaching Ruth in the moment (ask questions, next move on a lead)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from database import get_db, Lead
from agents.coach import coach_answer, coach_next_move, QUICK_PROMPTS

router = APIRouter(prefix="/coach", tags=["coach"])


class AskRequest(BaseModel):
    question: str
    lead_id: Optional[int] = None


@router.get("/prompts")
def prompts():
    return QUICK_PROMPTS


@router.post("/ask")
async def ask(req: AskRequest, db: Session = Depends(get_db)):
    if not req.question.strip():
        raise HTTPException(400, "Ask a question")
    ctx = ""
    if req.lead_id:
        lead = db.query(Lead).filter(Lead.id == req.lead_id).first()
        if lead:
            ctx = (f"{lead.first_name} {lead.last_name}, {lead.address or ''} {lead.city or ''}, "
                   f"temp {lead.temperature}, stage {lead.stage or 'new'}, "
                   f"score {lead.score}, situation {lead.life_event or 'unknown'}")
    answer = await coach_answer(req.question, ctx)
    return {"answer": answer}


@router.post("/next-move/{lead_id}")
async def next_move(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    from routers.leads import _serialize_lead
    answer = await coach_next_move(_serialize_lead(lead))
    return {"lead_id": lead_id, "answer": answer}
