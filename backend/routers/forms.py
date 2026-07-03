"""
Transaction Form Prep — fills a lead's contact + property details into the standard CA
agent-completed forms, so the agent doesn't re-type client info into every form.

IMPORTANT: The official C.A.R. forms are copyrighted and must be completed in the licensed
system (zipForms / DocuSign). ARIA does NOT reproduce those forms — it prepares the field
DATA (a fill-in sheet) that the agent transfers into the official form. Everything here is a
working DRAFT for the licensed agent to review; it is not legal advice or a binding document.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from database import get_db, Lead, Listing
from config import settings

router = APIRouter(prefix="/forms", tags=["forms"])

DISCLAIMER = ("DRAFT — auto-filled from your records. Transfer these values into the official "
              "C.A.R. form in zipForms/DocuSign. Review every field; this is not legal advice "
              "or a binding document.")

# The agent-completed CA forms ARIA prepares data for.
FORM_CATALOG = {
    "rla":       {"name": "Residential Listing Agreement (RLA)"},
    "rpa":       {"name": "Residential Purchase Agreement (RPA)"},
    "ad":        {"name": "Disclosure Regarding Agency Relationship (AD)"},
    "tds":       {"name": "Transfer Disclosure Statement (TDS) — agent section"},
    "avid":      {"name": "Agent Visual Inspection Disclosure (AVID)"},
    "spq":       {"name": "Seller Property Questionnaire (SPQ) — cover"},
    "net_sheet": {"name": "Seller Estimated Net Sheet"},
}


@router.get("/catalog")
def catalog():
    return [{"key": k, **v} for k, v in FORM_CATALOG.items()]


class PrepareRequest(BaseModel):
    lead_id: Optional[int] = None
    listing_id: Optional[int] = None
    buyer_name: Optional[str] = ""   # optional, for the RPA


def _ctx(lead: Optional[Lead], listing: Optional[Listing], buyer_name: str) -> dict:
    def g(obj, attr, default=""):
        return getattr(obj, attr, default) if obj else default
    seller = f"{g(lead,'first_name')} {g(lead,'last_name')}".strip()
    price = g(listing, "list_price") or g(lead, "estimated_value") or ""
    return {
        "seller_name": seller or "(seller)",
        "buyer_name": buyer_name or "(buyer)",
        "property_address": g(listing, "address") or g(lead, "address"),
        "city": g(listing, "city") or g(lead, "city"),
        "state": g(lead, "state") or "CA",
        "zip": g(listing, "zip_code") or g(lead, "zip_code"),
        "list_price": price,
        "bedrooms": g(listing, "bedrooms") or g(lead, "bedrooms"),
        "bathrooms": g(listing, "bathrooms") or g(lead, "bathrooms"),
        "sqft": g(listing, "sqft") or g(lead, "sqft"),
        "year_built": g(listing, "year_built") or g(lead, "year_built"),
        "seller_email": g(lead, "email"),
        "seller_phone": g(lead, "phone"),
        "agent_name": settings.agent_name,
        "agent_dre": settings.agent_license or "(DRE #)",
        "broker": settings.broker_name,
        "agent_phone": settings.agent_phone,
        "agent_email": settings.agent_email,
        "prepared_date": datetime.now().strftime("%B %d, %Y"),
    }


def _money(v):
    try:
        return f"${float(v):,.0f}" if v not in ("", None) else ""
    except (ValueError, TypeError):
        return str(v)


def _fields(form_key: str, c: dict) -> list[dict]:
    agent_block = [
        {"label": "Listing Agent", "value": c["agent_name"]},
        {"label": "DRE License #", "value": c["agent_dre"]},
        {"label": "Brokerage", "value": c["broker"]},
        {"label": "Agent Phone", "value": c["agent_phone"]},
        {"label": "Agent Email", "value": c["agent_email"]},
    ]
    prop = [
        {"label": "Property Address", "value": c["property_address"]},
        {"label": "City", "value": c["city"]},
        {"label": "State", "value": c["state"]},
        {"label": "ZIP", "value": c["zip"]},
    ]
    if form_key == "rla":
        return [{"label": "Seller(s)", "value": c["seller_name"]}, *prop,
                {"label": "List Price", "value": _money(c["list_price"])},
                {"label": "Bedrooms", "value": c["bedrooms"]},
                {"label": "Bathrooms", "value": c["bathrooms"]},
                {"label": "Living Area (sqft)", "value": c["sqft"]},
                {"label": "Year Built", "value": c["year_built"]},
                {"label": "Listing Date", "value": c["prepared_date"]}, *agent_block]
    if form_key == "rpa":
        return [{"label": "Buyer(s)", "value": c["buyer_name"]},
                {"label": "Seller(s)", "value": c["seller_name"]}, *prop,
                {"label": "Offer / Purchase Price", "value": _money(c["list_price"])},
                {"label": "Date Prepared", "value": c["prepared_date"]}, *agent_block]
    if form_key == "ad":
        return [{"label": "Seller(s)", "value": c["seller_name"]}, *prop, *agent_block,
                {"label": "Date", "value": c["prepared_date"]}]
    if form_key == "tds":
        return [{"label": "Property Address", "value": c["property_address"]},
                {"label": "City / State / ZIP", "value": f"{c['city']}, {c['state']} {c['zip']}"},
                {"label": "Seller(s)", "value": c["seller_name"]},
                {"label": "Agent Completing (Listing Agent)", "value": c["agent_name"]},
                {"label": "DRE License #", "value": c["agent_dre"]},
                {"label": "Date", "value": c["prepared_date"]}]
    if form_key == "avid":
        return [*prop, {"label": "Inspecting Agent", "value": c["agent_name"]},
                {"label": "DRE License #", "value": c["agent_dre"]},
                {"label": "Date of Inspection", "value": c["prepared_date"]},
                {"label": "Areas to document", "value": "Entry, Living, Kitchen, Bedrooms, "
                 "Bathrooms, Garage, Exterior, Yard (add observations per area)"}]
    if form_key == "spq":
        return [{"label": "Seller(s)", "value": c["seller_name"]}, *prop,
                {"label": "Date", "value": c["prepared_date"]}, *agent_block]
    if form_key == "net_sheet":
        price = c["list_price"]
        try:
            p = float(price); comm = p * 0.05; title = p * 0.011; misc = 3500
            net = p - comm - title - misc
            return [{"label": "Seller(s)", "value": c["seller_name"]}, *prop,
                    {"label": "Estimated Sale Price", "value": _money(p)},
                    {"label": "Est. Commission (≈5%)", "value": _money(comm)},
                    {"label": "Est. Title/Escrow (≈1.1%)", "value": _money(title)},
                    {"label": "Est. Misc Closing", "value": _money(misc)},
                    {"label": "Estimated Net to Seller", "value": _money(net)},
                    {"label": "Date", "value": c["prepared_date"]}]
        except (ValueError, TypeError):
            return [{"label": "Seller(s)", "value": c["seller_name"]}, *prop,
                    {"label": "Estimated Sale Price", "value": "(add price to the lead/listing)"}]
    return prop


@router.post("/prepare")
def prepare(req: PrepareRequest, db: Session = Depends(get_db)):
    if not (req.lead_id or req.listing_id):
        raise HTTPException(400, "Provide a lead_id or listing_id")
    lead = db.query(Lead).filter(Lead.id == req.lead_id).first() if req.lead_id else None
    listing = db.query(Listing).filter(Listing.id == req.listing_id).first() if req.listing_id else None
    if req.lead_id and not lead:
        raise HTTPException(404, "Lead not found")
    c = _ctx(lead, listing, req.buyer_name or "")
    forms = [{"key": k, "name": v["name"], "fields": _fields(k, c)}
             for k, v in FORM_CATALOG.items()]
    return {"disclaimer": DISCLAIMER, "prepared_for": c["seller_name"],
            "property": c["property_address"], "forms": forms}
