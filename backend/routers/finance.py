from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from database import get_db, Expense
from agents.finance import (
    summarize, ai_categorize, monthly_report, CATEGORIES, ARIA_STACK,
)

router = APIRouter(prefix="/finance", tags=["finance"])


class ExpenseCreate(BaseModel):
    amount: float
    vendor: str
    description: Optional[str] = ""
    category: Optional[str] = None
    segment: Optional[str] = "real_estate"
    recurrence: Optional[str] = "one_time"
    is_tax_deductible: Optional[bool] = True
    payment_method: Optional[str] = None
    date: Optional[str] = None
    notes: Optional[str] = ""


def _serialize(e: Expense) -> dict:
    return {
        "id": e.id, "amount": e.amount, "vendor": e.vendor, "description": e.description,
        "category": e.category, "segment": e.segment, "recurrence": e.recurrence,
        "is_tax_deductible": e.is_tax_deductible, "payment_method": e.payment_method,
        "notes": e.notes, "date": e.date.isoformat() if e.date else None,
    }


@router.get("/categories")
def get_categories():
    return CATEGORIES


@router.get("/expenses")
def list_expenses(segment: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Expense)
    if segment:
        q = q.filter(Expense.segment == segment)
    return [_serialize(e) for e in q.order_by(Expense.date.desc()).all()]


@router.post("/expenses")
async def add_expense(req: ExpenseCreate, db: Session = Depends(get_db)):
    data = req.dict()
    # AI auto-categorize if category missing
    if not data.get("category"):
        ai = await ai_categorize(f"{req.vendor} {req.description}", req.amount)
        data["category"] = ai.get("category", "Other")
        data["segment"] = data.get("segment") or ai.get("segment", "shared")
        data["is_tax_deductible"] = ai.get("is_tax_deductible", True)
    if data.get("date"):
        data["date"] = datetime.fromisoformat(data["date"])
    else:
        data["date"] = datetime.utcnow()
    exp = Expense(**{k: v for k, v in data.items() if hasattr(Expense, k)})
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return _serialize(exp)


@router.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    exp = db.query(Expense).filter(Expense.id == expense_id).first()
    if not exp:
        raise HTTPException(404, "Expense not found")
    db.delete(exp)
    db.commit()
    return {"status": "deleted"}


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    expenses = [_serialize(e) for e in db.query(Expense).all()]
    return summarize(expenses)


@router.get("/report")
async def get_report(db: Session = Depends(get_db)):
    expenses = [_serialize(e) for e in db.query(Expense).all()]
    s = summarize(expenses)
    report = await monthly_report(expenses, s)
    return {"report": report, "summary": s}


@router.post("/seed-aria-stack")
def seed_aria_stack(db: Session = Depends(get_db)):
    """Quick-add the ARIA tool stack as recurring expenses (editable estimates)."""
    added = []
    for item in ARIA_STACK:
        existing = db.query(Expense).filter(Expense.vendor == item["vendor"]).first()
        if existing:
            continue
        exp = Expense(
            amount=item["amount"], vendor=item["vendor"], category=item["category"],
            segment=item["segment"], recurrence=item["recurrence"],
            description="ARIA tool stack", notes=item["notes"],
            is_tax_deductible=True, date=datetime.utcnow(),
        )
        db.add(exp)
        db.flush()
        added.append(exp.id)
    db.commit()
    return {"added": len(added), "skipped_existing": len(ARIA_STACK) - len(added)}
