"""
Team / multi-user foundation — a roster of brokerage team members.

The app still uses one shared login for now; this provides the team list, roles, and the data the
manager view + lead assignment build on. (Per-user logins can layer on later.)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from database import get_db, TeamMember, Lead

router = APIRouter(prefix="/team", tags=["team"])

ROLES = ["agent", "manager", "admin", "transaction_coordinator"]


class MemberCreate(BaseModel):
    name: str
    email: Optional[str] = ""
    phone: Optional[str] = ""
    role: Optional[str] = "agent"
    notes: Optional[str] = ""


def _serialize(m: TeamMember, lead_count: int = 0) -> dict:
    return {
        "id": m.id, "name": m.name, "email": m.email, "phone": m.phone,
        "role": m.role, "active": m.active, "notes": m.notes,
        "assigned_leads": lead_count,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("/")
def list_members(db: Session = Depends(get_db)):
    members = db.query(TeamMember).order_by(TeamMember.created_at.asc()).all()
    out = []
    for m in members:
        count = (db.query(Lead).filter(Lead.assigned_to == m.id,
                                       Lead.is_deleted.isnot(True)).count())
        out.append(_serialize(m, count))
    return out


@router.get("/roles")
def list_roles():
    return ROLES


@router.get("/overview")
def manager_overview(db: Session = Depends(get_db)):
    """Manager view: each member's pipeline (totals, temperature, stage) + team-wide rollups."""
    active = db.query(Lead).filter(Lead.is_deleted.isnot(True)).all()
    members = db.query(TeamMember).order_by(TeamMember.created_at.asc()).all()

    def blank():
        return {"total": 0, "hot": 0, "warm": 0, "cold": 0, "not_ready": 0, "by_stage": {}}

    def tally(bucket, lead):
        bucket["total"] += 1
        temp = (lead.temperature or "cold")
        if temp in bucket:
            bucket[temp] += 1
        stage = lead.stage.value if lead.stage else "new"
        bucket["by_stage"][stage] = bucket["by_stage"].get(stage, 0) + 1

    per_member = {m.id: {"id": m.id, "name": m.name, "role": m.role, **blank()} for m in members}
    unassigned = blank()
    team_totals = blank()

    for lead in active:
        tally(team_totals, lead)
        if lead.assigned_to and lead.assigned_to in per_member:
            tally(per_member[lead.assigned_to], lead)
        else:
            tally(unassigned, lead)

    return {
        "team_totals": team_totals,
        "unassigned": unassigned,
        "members": list(per_member.values()),
        "member_count": len(members),
    }


@router.post("/")
def add_member(req: MemberCreate, db: Session = Depends(get_db)):
    if not req.name.strip():
        raise HTTPException(400, "Name is required")
    role = req.role if req.role in ROLES else "agent"
    m = TeamMember(name=req.name.strip(), email=(req.email or "").strip(),
                   phone=(req.phone or "").strip(), role=role, notes=(req.notes or "").strip())
    db.add(m)
    db.commit()
    db.refresh(m)
    return _serialize(m)


@router.put("/{member_id}")
def update_member(member_id: int, updates: dict, db: Session = Depends(get_db)):
    m = db.query(TeamMember).filter(TeamMember.id == member_id).first()
    if not m:
        raise HTTPException(404, "Team member not found")
    for k, v in updates.items():
        if hasattr(m, k) and k not in ("id", "created_at"):
            if k == "role" and v not in ROLES:
                continue
            setattr(m, k, v)
    db.commit()
    return _serialize(m)


@router.delete("/{member_id}")
def remove_member(member_id: int, db: Session = Depends(get_db)):
    m = db.query(TeamMember).filter(TeamMember.id == member_id).first()
    if not m:
        raise HTTPException(404, "Team member not found")
    # Unassign their leads so nothing points at a deleted member.
    for lead in db.query(Lead).filter(Lead.assigned_to == member_id).all():
        lead.assigned_to = None
    db.delete(m)
    db.commit()
    return {"id": member_id, "status": "deleted"}
