"""
Scripts library — built-in coach scripts (read-only) + Ruth's own uploaded scripts (editable).
Lets her upload new scripts (typed or as a .txt/.md file) and delete the ones she added.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from database import get_db, Script
from agents.scripts import SCRIPT_LIBRARY

router = APIRouter(prefix="/scripts", tags=["scripts"])

# Friendly labels for the built-in library keys.
BUILTIN_META = {
    "expired_brandon_mulrenin": ("Expired Listing", "Brandon Mulrenin"),
    "fsbo_tom_ferry": ("FSBO Script", "Tom Ferry"),
    "commission_objection": ("Commission Objection", "Mike Ferry"),
}


def _builtin_title(key: str) -> tuple[str, str]:
    if key in BUILTIN_META:
        return BUILTIN_META[key]
    # Derive something readable from the key, e.g. "wait_objection" -> "Wait Objection"
    return (key.replace("_", " ").title(), "")


class ScriptCreate(BaseModel):
    title: str
    content: str
    author: Optional[str] = ""
    category: Optional[str] = "Custom"


def _serialize(s: Script) -> dict:
    return {
        "id": s.id, "title": s.title, "category": s.category, "author": s.author,
        "content": s.content, "deletable": True,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("/")
def list_scripts(db: Session = Depends(get_db)):
    """All scripts: built-in (read-only) + the user's uploaded ones (deletable)."""
    builtin = []
    for key, content in SCRIPT_LIBRARY.items():
        title, author = _builtin_title(key)
        builtin.append({"id": f"builtin:{key}", "title": title, "author": author,
                        "category": "Built-in", "content": content, "deletable": False})
    custom = [_serialize(s) for s in
              db.query(Script).order_by(Script.created_at.desc()).all()]
    return {"builtin": builtin, "custom": custom}


@router.post("/")
def create_script(req: ScriptCreate, db: Session = Depends(get_db)):
    if not req.title.strip() or not req.content.strip():
        raise HTTPException(400, "Title and content are required")
    s = Script(title=req.title.strip(), content=req.content,
               author=(req.author or "").strip(), category=(req.category or "Custom").strip())
    db.add(s)
    db.commit()
    db.refresh(s)
    return _serialize(s)


@router.post("/upload")
async def upload_script(file: UploadFile = File(...), title: Optional[str] = Form(None),
                        author: Optional[str] = Form(""), category: Optional[str] = Form("Custom"),
                        db: Session = Depends(get_db)):
    """Upload a script as a text file (.txt / .md)."""
    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("latin-1", errors="ignore")
    if not content.strip():
        raise HTTPException(400, "The uploaded file is empty")
    name = (title or file.filename or "Uploaded script").rsplit(".", 1)[0]
    s = Script(title=name, content=content, author=(author or "").strip(),
               category=(category or "Custom").strip())
    db.add(s)
    db.commit()
    db.refresh(s)
    return _serialize(s)


@router.delete("/{script_id}")
def delete_script(script_id: int, db: Session = Depends(get_db)):
    s = db.query(Script).filter(Script.id == script_id).first()
    if not s:
        raise HTTPException(404, "Script not found (built-in scripts can't be deleted)")
    db.delete(s)
    db.commit()
    return {"id": script_id, "status": "deleted"}
