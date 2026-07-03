from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from database import get_db, Listing, Lead, ChecklistItem
from agents.marketing import (
    write_mls_description, write_social_posts,
    write_listing_presentation, write_email_sequence
)
from agents.documents import generate_all_documents
from agents.research import run_cma
from agents.calendar_agent import schedule_open_house

router = APIRouter(prefix="/listings", tags=["listings"])


class ListingCreate(BaseModel):
    lead_id: Optional[int] = None
    address: str
    city: str
    zip_code: str
    list_price: float
    bedrooms: int
    bathrooms: float
    sqft: int
    lot_size: Optional[str] = None
    year_built: Optional[int] = None
    property_type: str = "Single Family Residence"
    hoa_fee: float = 0
    showing_instructions: Optional[str] = ""


@router.get("/")
def list_listings(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Listing)
    if status:
        query = query.filter(Listing.status == status)
    return [_serialize(l) for l in query.all()]


@router.post("/")
async def create_listing(data: ListingCreate, db: Session = Depends(get_db)):
    listing = Listing(**data.dict())
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return _serialize(listing)


@router.get("/{listing_id}")
def get_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(404, "Listing not found")
    return _serialize(listing)


@router.post("/{listing_id}/mls-description")
async def generate_mls_description(listing_id: int, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(404, "Listing not found")
    description = await write_mls_description(_serialize(listing))
    listing.mls_description = description
    db.commit()
    return {"listing_id": listing_id, "mls_description": description}


@router.post("/{listing_id}/social-posts")
async def generate_social_posts(listing_id: int, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(404, "Listing not found")
    posts = await write_social_posts(_serialize(listing), listing.mls_description or "")
    return {"listing_id": listing_id, "posts": posts}


@router.post("/{listing_id}/documents")
async def generate_documents(listing_id: int, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(404, "Listing not found")

    seller_data = {}
    if listing.lead_id:
        lead = db.query(Lead).filter(Lead.id == listing.lead_id).first()
        if lead:
            seller_data = {
                "full_name": f"{lead.first_name} {lead.last_name}",
                "email": lead.email, "phone": lead.phone
            }

    cma = await run_cma(listing.address, listing.bedrooms, listing.bathrooms,
                        listing.sqft, listing.city)
    result = await generate_all_documents(_serialize(listing), seller_data, cma)
    return result


@router.post("/{listing_id}/presentation")
async def generate_presentation(listing_id: int, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(404, "Listing not found")

    cma = await run_cma(listing.address, listing.bedrooms, listing.bathrooms,
                        listing.sqft, listing.city)
    seller_data = {}
    if listing.lead_id:
        lead = db.query(Lead).filter(Lead.id == listing.lead_id).first()
        if lead:
            seller_data = {"full_name": f"{lead.first_name} {lead.last_name}"}

    presentation = await write_listing_presentation(_serialize(listing), cma, seller_data)
    return {"listing_id": listing_id, "presentation": presentation, "cma": cma}


@router.post("/{listing_id}/open-house")
async def schedule_open_house_endpoint(listing_id: int, date_iso: str,
                                       duration_hours: float = 2, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(404, "Listing not found")
    dt = datetime.fromisoformat(date_iso)
    result = schedule_open_house(_serialize(listing), dt, duration_hours)
    return result


@router.put("/{listing_id}/status")
def update_status(listing_id: int, status: str, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(404, "Listing not found")
    listing.status = status
    listing.updated_at = datetime.utcnow()
    db.commit()
    return {"listing_id": listing_id, "new_status": status}


def _serialize(l: Listing) -> dict:
    return {
        "id": l.id, "lead_id": l.lead_id, "mls_number": l.mls_number,
        "address": l.address, "city": l.city, "zip_code": l.zip_code,
        "list_price": l.list_price, "sale_price": l.sale_price,
        "bedrooms": l.bedrooms, "bathrooms": l.bathrooms,
        "sqft": l.sqft, "lot_size": l.lot_size, "year_built": l.year_built,
        "property_type": l.property_type, "hoa_fee": l.hoa_fee,
        "status": l.status,
        "list_date": l.list_date.isoformat() if l.list_date else None,
        "close_date": l.close_date.isoformat() if l.close_date else None,
        "mls_description": l.mls_description,
        "showing_instructions": l.showing_instructions,
        "escrow_number": l.escrow_number,
        "inspection_date": l.inspection_date.isoformat() if l.inspection_date else None,
        "contingency_removal_date": l.contingency_removal_date.isoformat() if l.contingency_removal_date else None,
        "close_escrow_date": l.close_escrow_date.isoformat() if l.close_escrow_date else None,
        "created_at": l.created_at.isoformat() if l.created_at else None,
    }


# ── Transaction checklist (listing → close) ───────────────────────────────────
DEFAULT_MILESTONES = [
    "Listing agreement signed (RLA)",
    "Disclosures sent (TDS / SPQ via Glide)",
    "Photos & staging done",
    "Listed on MLS",
    "Marketing launched",
    "Offer received",
    "Offer accepted — escrow opened",
    "Inspections complete",
    "Appraisal complete",
    "Contingencies removed",
    "Loan funded",
    "Closed & recorded",
]


def _ck(item: ChecklistItem) -> dict:
    return {"id": item.id, "label": item.label, "done": item.done, "sort": item.sort,
            "done_at": item.done_at.isoformat() if item.done_at else None}


@router.get("/{listing_id}/checklist")
def get_checklist(listing_id: int, db: Session = Depends(get_db)):
    """Get a listing's transaction checklist, seeding the standard milestones on first use."""
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(404, "Listing not found")
    items = (db.query(ChecklistItem).filter(ChecklistItem.listing_id == listing_id)
             .order_by(ChecklistItem.sort.asc()).all())
    if not items:
        for i, label in enumerate(DEFAULT_MILESTONES):
            db.add(ChecklistItem(listing_id=listing_id, label=label, sort=i))
        db.commit()
        items = (db.query(ChecklistItem).filter(ChecklistItem.listing_id == listing_id)
                 .order_by(ChecklistItem.sort.asc()).all())
    done = sum(1 for it in items if it.done)
    return {"listing_id": listing_id, "total": len(items), "done": done,
            "percent": round(done / len(items) * 100) if items else 0,
            "items": [_ck(it) for it in items]}


class ChecklistToggle(BaseModel):
    done: bool


@router.put("/checklist/{item_id}")
def toggle_checklist(item_id: int, req: ChecklistToggle, db: Session = Depends(get_db)):
    item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Checklist item not found")
    item.done = req.done
    item.done_at = datetime.utcnow() if req.done else None
    db.commit()
    return _ck(item)


class ChecklistAdd(BaseModel):
    label: str


@router.post("/{listing_id}/checklist")
def add_checklist_item(listing_id: int, req: ChecklistAdd, db: Session = Depends(get_db)):
    if not req.label.strip():
        raise HTTPException(400, "Label required")
    maxsort = (db.query(ChecklistItem).filter(ChecklistItem.listing_id == listing_id).count())
    item = ChecklistItem(listing_id=listing_id, label=req.label.strip(), sort=maxsort)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _ck(item)


@router.delete("/checklist/{item_id}")
def delete_checklist_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Checklist item not found")
    db.delete(item)
    db.commit()
    return {"id": item_id, "status": "deleted"}
