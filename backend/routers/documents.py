"""
Document Vault — stores transaction/compliance documents.

California brokers must retain transaction records for 3 years, so each upload is stamped with a
`retain_until` date (uploaded + 3 years). Files are saved on the persistent volume (so they survive
redeploys). External providers (Dropbox / SkySlope / Glide) can be connected later — their status is
reported by /documents/integrations and wiring is stubbed until the user's accounts/keys are added.
"""
import os
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db, Document
from config import settings

router = APIRouter(prefix="/documents", tags=["documents"])

RETENTION_YEARS = 3


def get_docs_dir() -> str:
    """Resolve where to store files. Prefer the configured dir; on Railway use the /data volume;
    fall back to a local ./data/documents folder for development."""
    d = settings.documents_dir
    if not d:
        d = "/data/documents" if os.path.isdir("/data") else os.path.join("data", "documents")
    os.makedirs(d, exist_ok=True)
    return d


def _serialize(doc: Document) -> dict:
    now = datetime.utcnow()
    retain = doc.retain_until
    return {
        "id": doc.id, "original_name": doc.original_name, "category": doc.category,
        "content_type": doc.content_type, "size_bytes": doc.size_bytes,
        "lead_id": doc.lead_id, "listing_id": doc.listing_id, "notes": doc.notes,
        "storage": doc.storage, "external_url": doc.external_url,
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "retain_until": retain.isoformat() if retain else None,
        "under_retention": bool(retain and retain > now),
    }


@router.get("/")
def list_documents(category: Optional[str] = None, lead_id: Optional[int] = None,
                   listing_id: Optional[int] = None, db: Session = Depends(get_db)):
    """List stored documents, optionally filtered by type, lead, or listing."""
    q = db.query(Document)
    if category:
        q = q.filter(Document.category == category)
    if lead_id is not None:
        q = q.filter(Document.lead_id == lead_id)
    if listing_id is not None:
        q = q.filter(Document.listing_id == listing_id)
    docs = q.order_by(Document.uploaded_at.desc()).all()
    return [_serialize(d) for d in docs]


@router.get("/summary")
def documents_summary(db: Session = Depends(get_db)):
    """Counts by category + total, for the vault's filter chips."""
    docs = db.query(Document).all()
    by_cat: dict = {}
    for d in docs:
        by_cat[d.category] = by_cat.get(d.category, 0) + 1
    return {"total": len(docs), "by_category": by_cat}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: Optional[str] = Form("Other"),
    lead_id: Optional[int] = Form(None),
    listing_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(""),
    db: Session = Depends(get_db),
):
    """Store a document on the volume and record it with a 3-year retention date."""
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")

    docs_dir = get_docs_dir()
    safe_ext = os.path.splitext(file.filename or "")[1][:10]
    stored_name = f"{uuid.uuid4().hex}{safe_ext}"
    path = os.path.join(docs_dir, stored_name)
    with open(path, "wb") as f:
        f.write(raw)

    now = datetime.utcnow()
    doc = Document(
        filename=stored_name, original_name=file.filename or stored_name,
        content_type=file.content_type or "", size_bytes=len(raw),
        category=(category or "Other").strip(), lead_id=lead_id, listing_id=listing_id,
        notes=(notes or "").strip(), storage="local",
        uploaded_at=now, retain_until=now + timedelta(days=365 * RETENTION_YEARS),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _serialize(doc)


@router.get("/{doc_id}/download")
def download_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    path = os.path.join(get_docs_dir(), doc.filename)
    if not os.path.exists(path):
        raise HTTPException(410, "File missing from storage")
    return FileResponse(path, filename=doc.original_name,
                        media_type=doc.content_type or "application/octet-stream")


@router.delete("/{doc_id}")
def delete_document(doc_id: int, force: bool = False, db: Session = Depends(get_db)):
    """Delete a document. Blocks deletion during the 3-year retention window unless force=true."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.retain_until and doc.retain_until > datetime.utcnow() and not force:
        raise HTTPException(
            409,
            f"This document is under the {RETENTION_YEARS}-year retention requirement until "
            f"{doc.retain_until.strftime('%b %d, %Y')}. Pass force=true to override.",
        )
    path = os.path.join(get_docs_dir(), doc.filename)
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    db.delete(doc)
    db.commit()
    return {"id": doc_id, "status": "deleted"}


@router.get("/integrations")
def integrations():
    """Which external storage providers are connected (for off-site compliance copies)."""
    return {
        "local_vault": {"connected": True, "note": f"Files stored on the app's volume, "
                        f"retained {RETENTION_YEARS} years."},
        "dropbox": {"connected": bool(settings.dropbox_access_token),
                    "note": "Add DROPBOX_ACCESS_TOKEN to auto-copy documents to Dropbox."},
        "skyslope": {"connected": bool(settings.skyslope_api_key),
                     "note": "Transaction mgmt + broker compliance. Add SKYSLOPE_API_KEY to sync."},
        "glide": {"connected": bool(settings.glide_api_key),
                  "note": "Digital disclosures. Add GLIDE_API_KEY to sync."},
    }
