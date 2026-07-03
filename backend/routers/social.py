from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from database import get_db, SocialPost
from agents.social import (
    generate_post_suite, generate_video_script,
    save_post_to_queue, publish_approved_post
)

router = APIRouter(prefix="/social", tags=["social"])


class GeneratePostRequest(BaseModel):
    content_type: str = "listing"   # listing, market_update, just_sold, open_house, tip, custom
    subject: str
    details: Optional[dict] = None
    image_url: Optional[str] = None
    listing_id: Optional[int] = None


class VideoScriptRequest(BaseModel):
    video_type: str = "market_update"
    topic: str
    duration_minutes: int = 3
    platform: str = "youtube"


class PublishRequest(BaseModel):
    platforms: list[str]  # ["facebook", "instagram", "twitter", "linkedin"]


@router.post("/generate")
async def generate_posts(req: GeneratePostRequest, db: Session = Depends(get_db)):
    """Generate post suite for all platforms — saved to approval queue."""
    content = await generate_post_suite(
        req.content_type, req.subject, req.details, req.image_url
    )
    if "error" in content:
        raise HTTPException(500, content["error"])

    post_id = save_post_to_queue(db, {
        "content_type": req.content_type,
        "subject": req.subject,
        "content": content,
        "image_url": req.image_url,
        "listing_id": req.listing_id,
        "platforms": ["facebook", "instagram", "twitter", "linkedin", "youtube", "tiktok"]
    })
    return {"post_id": post_id, "status": "pending_approval", "content": content}


@router.get("/queue")
def get_queue(status: Optional[str] = "pending_approval", db: Session = Depends(get_db)):
    """Get all posts in the approval queue."""
    query = db.query(SocialPost)
    if status:
        query = query.filter(SocialPost.status == status)
    posts = query.order_by(SocialPost.created_at.desc()).all()
    return [_serialize(p) for p in posts]


@router.get("/queue/{post_id}")
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")
    return _serialize(post)


@router.post("/queue/{post_id}/approve")
async def approve_and_publish(post_id: int, req: PublishRequest, db: Session = Depends(get_db)):
    """Approve a post and publish to selected platforms."""
    result = await publish_approved_post(db, post_id, req.platforms)
    return result


@router.post("/queue/{post_id}/reject")
def reject_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")
    post.status = "rejected"
    db.commit()
    return {"status": "rejected"}


@router.post("/queue/{post_id}/edit")
def edit_post(post_id: int, updates: dict, db: Session = Depends(get_db)):
    """Edit generated content before approving."""
    post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")
    content = dict(post.generated_content or {})
    for platform, platform_updates in updates.items():
        if platform in content:
            content[platform].update(platform_updates)
        else:
            content[platform] = platform_updates
    post.generated_content = content
    db.commit()
    return {"post_id": post_id, "status": "updated"}


@router.post("/video-script")
async def create_video_script(req: VideoScriptRequest):
    """Generate a full video script for YouTube or TikTok."""
    result = await generate_video_script(
        req.video_type, req.topic, req.duration_minutes, req.platform
    )
    return result


@router.get("/credentials-status")
def credentials_status():
    """Check which social platforms are configured."""
    from config import settings
    return {
        "facebook": bool(settings.facebook_page_access_token and settings.facebook_page_id),
        "instagram": bool(settings.facebook_page_access_token and settings.instagram_account_id),
        "twitter": bool(settings.twitter_api_key and settings.twitter_access_token),
        "linkedin": bool(settings.linkedin_access_token and settings.linkedin_person_urn),
        "youtube": "manual_upload",
        "tiktok": "manual_upload",
        "nextdoor": "manual_upload"
    }


def _serialize(p: SocialPost) -> dict:
    return {
        "id": p.id,
        "content_type": p.content_type,
        "subject": p.subject,
        "status": p.status,
        "image_url": p.image_url,
        "platforms": p.platforms,
        "content": p.generated_content,
        "publish_results": p.publish_results,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "scheduled_for": p.scheduled_for.isoformat() if p.scheduled_for else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
