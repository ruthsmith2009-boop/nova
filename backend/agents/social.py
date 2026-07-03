"""
Social Media Agent — generates and publishes posts to Instagram, Facebook,
LinkedIn, Twitter/X. Generates scripts/captions for YouTube and TikTok.
All posts go through an approval queue before publishing.
"""
import json
import httpx
from datetime import datetime
from typing import Optional
from agents.brain import think, BUSINESS_KNOWLEDGE
from config import settings


# ─── Content Generation ───────────────────────────────────────────────────────

async def generate_post_suite(
    content_type: str,
    subject: str,
    details: dict = None,
    image_url: str = None
) -> dict:
    """
    Generate a full suite of platform-specific posts from one brief.

    content_type: "new_offer" | "industry_update" | "customer_win" | "promo" |
                  "tip" | "testimonial" | "spotlight" | "custom"
    subject: e.g. "New AI booking assistant for local service businesses"
    details: extra context dict
    """
    details_str = json.dumps(details or {}, indent=2)

    result = await think(
        f"""You are the marketing voice for a small business owner. Create social media posts that
attract leads and build trust. Adapt to whatever industry the subject implies — never assume real
estate or any single field.

Content type: {content_type}
Subject: {subject}
Details: {details_str}

{BUSINESS_KNOWLEDGE}

Write platform-specific posts. Choose hashtags that fit the subject and industry.
Return JSON:
{{
  "instagram": {{
    "caption": "Compelling caption with line breaks. 150-200 words. Conversational, visual, emotional. End with CTA.",
    "hashtags": "8-12 relevant hashtags for this business/industry and post",
    "first_comment_hashtags": "Additional hashtags for first comment to keep caption clean",
    "story_text": "2-3 punchy lines for Instagram Stories overlay",
    "reel_hook": "First 3 seconds script to stop the scroll"
  }},
  "facebook": {{
    "post": "Longer, more detailed. 200-300 words. Include specifics, tell a story, end with a question to drive comments.",
    "headline": "Short attention-grabbing headline (under 50 chars)",
    "link_description": "One-line description if sharing a link"
  }},
  "linkedin": {{
    "post": "Professional tone. Lead with insight or a result. 150-200 words. Good for B2B and referral network.",
    "headline": "Professional headline for the post"
  }},
  "twitter_x": {{
    "tweet": "Under 240 chars. Punchy. Key stat or hook. CTA or question.",
    "thread": ["Tweet 1/4 — hook", "Tweet 2/4 — detail", "Tweet 3/4 — insight", "Tweet 4/4 — CTA"]
  }},
  "youtube": {{
    "title": "SEO-optimized video title (include the topic + a keyword)",
    "description": "Full YouTube description — 300 words, includes timestamps, links, keywords, CTA to subscribe and get in touch",
    "tags": ["relevant", "industry", "keywords"],
    "script_outline": ["Intro (0:00) — hook and what viewer will learn", "Section 1 (1:00)", "Section 2 (2:30)", "CTA (4:00) — subscribe + contact"],
    "thumbnail_text": "Bold text for thumbnail overlay (under 6 words)"
  }},
  "tiktok": {{
    "caption": "Short, punchy TikTok caption. Max 150 chars. Use 3-5 hashtags only.",
    "hashtags": "3-5 relevant hashtags for this business/industry",
    "hook_script": "First 3 seconds spoken — must stop scroll immediately",
    "full_script": "30-60 second spoken script for the video. Energetic, fast-paced.",
    "trending_sounds_tip": "Suggest what type of audio works for this content"
  }},
  "google_business": {{
    "post": "Google Business Profile update. 100-150 words. Local, helpful, clear CTA (call/book/visit)."
  }}
}}""",
    )

    try:
        return json.loads(result)
    except Exception:
        return {"error": "Could not generate posts", "raw": result[:300]}


async def generate_video_script(
    video_type: str,
    topic: str,
    duration_minutes: int = 3,
    platform: str = "youtube"
) -> dict:
    """
    Generate a full video script for YouTube or TikTok.
    video_type: "industry_update" | "product_demo" | "tips" | "how_to" | "q_and_a"
    """
    result = await think(
        f"""Write a complete {platform} video script for a small business owner marketing their
services. Adapt to whatever industry the topic implies — never assume real estate.

Video type: {video_type}
Topic: {topic}
Target duration: {duration_minutes} minutes
Platform: {platform}

{BUSINESS_KNOWLEDGE}

Write a complete, word-for-word script including:
- Hook (first 5-10 seconds — must be compelling)
- Introduction
- Main content sections with transitions
- Data/stats to mention
- Call to action at the end (subscribe + get in touch)
- On-screen text suggestions [in brackets]
- B-roll suggestions (what to show visually)

Format clearly with timestamps.
Make it sound natural and conversational.
Include a specific, credible detail or result to establish authority."""
    )
    return {"platform": platform, "video_type": video_type, "topic": topic, "script": result}


# ─── Platform Publishers ──────────────────────────────────────────────────────

async def post_to_facebook(message: str, page_id: str, page_access_token: str,
                           image_url: str = None) -> dict:
    """Post to a Facebook Page."""
    url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
    params = {"message": message, "access_token": page_access_token}
    if image_url:
        url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
        params["url"] = image_url
        params["caption"] = message

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=params)
        data = resp.json()
        if "id" in data:
            return {"status": "posted", "post_id": data["id"],
                    "url": f"https://facebook.com/{data['id']}"}
        return {"status": "error", "error": data.get("error", {}).get("message", str(data))}


async def post_to_instagram(caption: str, instagram_account_id: str,
                            page_access_token: str, image_url: str = None) -> dict:
    """Post to Instagram Business account via Meta Graph API."""
    if not image_url:
        return {"status": "error", "error": "Instagram requires an image URL to post"}

    async with httpx.AsyncClient() as client:
        # Step 1: Create media container
        container_resp = await client.post(
            f"https://graph.facebook.com/v19.0/{instagram_account_id}/media",
            data={"image_url": image_url, "caption": caption,
                  "access_token": page_access_token}
        )
        container = container_resp.json()
        if "id" not in container:
            return {"status": "error", "error": container.get("error", {}).get("message", str(container))}

        # Step 2: Publish the container
        publish_resp = await client.post(
            f"https://graph.facebook.com/v19.0/{instagram_account_id}/media_publish",
            data={"creation_id": container["id"], "access_token": page_access_token}
        )
        result = publish_resp.json()
        if "id" in result:
            return {"status": "posted", "post_id": result["id"]}
        return {"status": "error", "error": result.get("error", {}).get("message", str(result))}


async def post_to_twitter(text: str, api_key: str, api_secret: str,
                          access_token: str, access_token_secret: str) -> dict:
    """Post a tweet via Twitter API v2."""
    import hmac, hashlib, time, base64, urllib.parse, secrets

    url = "https://api.twitter.com/2/tweets"

    # OAuth 1.0a signing
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    oauth_params = {
        "oauth_consumer_key": api_key,
        "oauth_nonce": nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp,
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }
    base_string = "&".join([
        "POST",
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote("&".join(f"{k}={urllib.parse.quote(v,safe='')}"
                                    for k,v in sorted(oauth_params.items())), safe="")
    ])
    signing_key = f"{urllib.parse.quote(api_secret, safe='')}&{urllib.parse.quote(access_token_secret, safe='')}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    oauth_params["oauth_signature"] = signature
    auth_header = "OAuth " + ", ".join(
        f'{k}="{urllib.parse.quote(v, safe="")}"' for k, v in sorted(oauth_params.items())
    )

    async with httpx.AsyncClient() as client:
        resp = await client.post(url,
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            json={"text": text}
        )
        data = resp.json()
        if "data" in data:
            return {"status": "posted", "tweet_id": data["data"]["id"],
                    "url": f"https://twitter.com/i/web/status/{data['data']['id']}"}
        return {"status": "error", "error": str(data)}


async def post_to_linkedin(text: str, access_token: str, person_urn: str) -> dict:
    """Post to LinkedIn profile."""
    payload = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers={"Authorization": f"Bearer {access_token}",
                     "Content-Type": "application/json",
                     "X-Restli-Protocol-Version": "2.0.0"},
            json=payload
        )
        if resp.status_code in (200, 201):
            post_id = resp.headers.get("x-restli-id", "unknown")
            return {"status": "posted", "post_id": post_id}
        return {"status": "error", "error": resp.text}


# ─── Queue Manager ────────────────────────────────────────────────────────────

def save_post_to_queue(db, post_data: dict) -> int:
    """Save a generated post suite to the approval queue."""
    from database import SocialPost
    post = SocialPost(
        content_type=post_data.get("content_type", "custom"),
        subject=post_data.get("subject", ""),
        platforms=post_data.get("platforms", []),
        generated_content=post_data.get("content", {}),
        image_url=post_data.get("image_url"),
        listing_id=post_data.get("listing_id"),
        status="pending_approval"
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post.id


async def publish_approved_post(db, post_id: int, selected_platforms: list[str]) -> dict:
    """Publish an approved post to selected platforms."""
    from database import SocialPost
    post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
    if not post:
        return {"error": "Post not found"}

    content = post.generated_content or {}
    results = {}

    # Load credentials from settings
    fb_token = getattr(settings, "facebook_page_access_token", "")
    fb_page_id = getattr(settings, "facebook_page_id", "")
    ig_account_id = getattr(settings, "instagram_account_id", "")
    tw_key = getattr(settings, "twitter_api_key", "")
    tw_secret = getattr(settings, "twitter_api_secret", "")
    tw_token = getattr(settings, "twitter_access_token", "")
    tw_token_secret = getattr(settings, "twitter_access_token_secret", "")
    li_token = getattr(settings, "linkedin_access_token", "")
    li_urn = getattr(settings, "linkedin_person_urn", "")

    for platform in selected_platforms:
        try:
            if platform == "facebook" and fb_token and fb_page_id:
                fb_content = content.get("facebook", {})
                msg = fb_content.get("post", post.subject)
                results["facebook"] = await post_to_facebook(msg, fb_page_id, fb_token, post.image_url)

            elif platform == "instagram" and fb_token and ig_account_id:
                ig_content = content.get("instagram", {})
                caption = ig_content.get("caption", "") + "\n\n" + ig_content.get("hashtags", "")
                results["instagram"] = await post_to_instagram(caption, ig_account_id, fb_token, post.image_url)

            elif platform == "twitter" and tw_key:
                tw_content = content.get("twitter_x", {})
                tweet = tw_content.get("tweet", post.subject[:240])
                results["twitter"] = await post_to_twitter(tweet, tw_key, tw_secret, tw_token, tw_token_secret)

            elif platform == "linkedin" and li_token:
                li_content = content.get("linkedin", {})
                msg = li_content.get("post", post.subject)
                results["linkedin"] = await post_to_linkedin(msg, li_token, li_urn)

            elif platform in ("youtube", "tiktok"):
                results[platform] = {
                    "status": "content_ready",
                    "message": f"Script and content generated. Upload manually to {platform.title()}.",
                    "content": content.get(platform, {})
                }
            else:
                results[platform] = {"status": "not_configured",
                                      "message": f"{platform} credentials not set in .env"}
        except Exception as e:
            results[platform] = {"status": "error", "error": str(e)}

    # Update post status
    any_posted = any(r.get("status") == "posted" for r in results.values())
    post.status = "published" if any_posted else "partially_published"
    post.published_at = datetime.utcnow()
    post.publish_results = results
    db.commit()

    return {"post_id": post_id, "results": results}
