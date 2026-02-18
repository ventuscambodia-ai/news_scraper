"""
Auto News Scraper - Instagram Sender
Posts to Instagram via the official Graph API (Content Publishing API).

Flow:
  1. Upload local media to a temp public host (0x0.st) to get a URL
  2. Create a media container: POST /{ig_account_id}/media
  3. Publish the container: POST /{ig_account_id}/media_publish

Requires: INSTAGRAM_ACCOUNT_ID + INSTAGRAM_ACCESS_TOKEN
"""

import asyncio
import logging
import time
from pathlib import Path

import requests as http_requests

import config

logger = logging.getLogger("sender.instagram")

GRAPH_API_BASE = f"https://graph.facebook.com/{config.FACEBOOK_API_VERSION}"

# Rate limiting: track posts
_post_timestamps = []
_MAX_POSTS_PER_DAY = 25
_MIN_DELAY_BETWEEN_POSTS = 30  # seconds


def _format_instagram_caption(post_data: dict) -> str:
    """
    Format post content for Instagram caption.
    IG captions max 2200 chars; no HTML, just plain text + emojis.
    """
    parts = []

    source = post_data.get("source", "unknown")
    channel_name = post_data.get("channel_name", "Unknown")

    if source == "telegram":
        parts.append(f"📡 Telegram • {channel_name}")
    elif source == "x":
        parts.append(f"🐦 X (Twitter) • {channel_name}")
    elif source == "facebook":
        parts.append(f"📘 Facebook • {channel_name}")
    else:
        parts.append(f"📰 {source} • {channel_name}")

    parts.append("")
    parts.append("─" * 30)
    parts.append("")

    text = post_data.get("text", "")
    if text:
        if len(text) > 2000:
            text = text[:2000] + "..."
        parts.append(text)

    original_link = post_data.get("original_link")
    if original_link:
        parts.append("")
        parts.append(f"🔗 Original: {original_link}")

    caption = "\n".join(parts)
    # Hard limit
    if len(caption) > 2200:
        caption = caption[:2197] + "..."
    return caption


def _check_rate_limit() -> bool:
    """Check if we're within the daily posting limit."""
    global _post_timestamps
    now = time.time()
    day_ago = now - 86400
    _post_timestamps = [t for t in _post_timestamps if t > day_ago]

    if len(_post_timestamps) >= _MAX_POSTS_PER_DAY:
        logger.warning(f"⚠️  Instagram daily limit reached ({_MAX_POSTS_PER_DAY} posts/day)")
        return False

    if _post_timestamps and (now - _post_timestamps[-1]) < _MIN_DELAY_BETWEEN_POSTS:
        remaining = _MIN_DELAY_BETWEEN_POSTS - (now - _post_timestamps[-1])
        logger.info(f"⏳ Instagram rate limit delay: waiting {remaining:.0f}s")
        return False  # caller should retry later

    return True


def _upload_to_temp_host(file_path: str) -> str:
    """
    Upload a local file to a temporary public host to get a URL.
    Instagram Graph API requires publicly accessible media URLs.
    Uses 0x0.st (supports images and videos, no auth required).
    """
    # Try 0x0.st first
    try:
        with open(file_path, "rb") as f:
            resp = http_requests.post(
                "https://0x0.st",
                files={"file": f},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=120,
            )
        if resp.status_code == 200:
            url = resp.text.strip()
            logger.debug(f"📤 Uploaded to temp host (0x0.st): {url}")
            return url
        else:
            logger.warning(f"⚠️  0x0.st upload failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.warning(f"⚠️  0x0.st upload error: {e}")

    # Fallback to uguu.se
    try:
        logger.info("🔄 Retrying upload with uguu.se...")
        with open(file_path, "rb") as f:
            resp = http_requests.post(
                "https://uguu.se/upload.php?output=text",
                files={"files[]": f},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=120,
            )
        if resp.status_code == 200:
            url = resp.text.strip()
            logger.debug(f"📤 Uploaded to temp host (uguu.se): {url}")
            return url
        else:
            logger.warning(f"⚠️  uguu.se upload failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.warning(f"⚠️  uguu.se upload error: {e}")

    # Fallback to catbox.moe (Last Resort)
    try:
        logger.info("🔄 Retrying upload with catbox.moe...")
        with open(file_path, "rb") as f:
            resp = http_requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": f},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=120,
            )
        if resp.status_code == 200:
            url = resp.text.strip()
            logger.debug(f"📤 Uploaded to temp host (catbox.moe): {url}")
            return url
        else:
            logger.error(f"❌ catbox.moe upload failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"❌ catbox.moe upload error: {e}")

    return None


async def send_to_instagram(post_data: dict) -> bool:
    """
    Post to Instagram via the Graph API.

    Supports:
        - Photo posts (image + caption)
        - Video posts (video + caption)
        - Text-only: SKIPPED (IG requires media)

    Args:
        post_data: Dict with keys: source, source_id, channel_name, text,
                   media_path, media_type, original_link

    Returns:
        True if posted successfully, False otherwise
    """
    account_id = config.INSTAGRAM_ACCOUNT_ID
    access_token = config.INSTAGRAM_ACCESS_TOKEN

    if not account_id or not access_token:
        # Only warn if explicitly enabled but missing credentials
        if config.INSTAGRAM_POSTING_ENABLED:
            logger.warning("⚠️  Instagram Enabled but missing Account ID or Token. Check Railway variables!")
        else:
            logger.warning("⏭️  Instagram configured to SKIP (Env Var INSTAGRAM_POSTING_ENABLED=False)")
        return False

    settings = config.load_settings()
    if not settings.get("instagram_posting_enabled", False):
        logger.warning("⏭️  Instagram posting disabled in Settings (Check Dashboard!)")
        return False

    media_names = post_data.get("media_paths", [])
    
    # Check for Carousel (Album)
    if media_names and len(media_names) > 1:
        logger.info(f"📸 Preparing Instagram Carousel with {len(media_names)} items")
        try:
            caption = _format_instagram_caption(post_data)
            return await _post_carousel(account_id, access_token, caption, media_names)
        except Exception as e:
             logger.error(f"❌ Instagram Carousel error: {e}", exc_info=True)
             return False

    media_path = post_data.get("media_path")
    media_type = post_data.get("media_type")

    # Instagram requires media — skip text-only posts
    if not media_path or not Path(media_path).exists():
        logger.info("ℹ️  Skipped Instagram: Post has no media (IG requires photo/video)")
        return False

    # Rate limit check
    if not _check_rate_limit():
        logger.warning("⏭️  Instagram rate limited, skipping this post")
        return False

    try:
        caption = _format_instagram_caption(post_data)

        # Upload media to temp host to get public URL
        loop = asyncio.get_event_loop()
        public_url = await loop.run_in_executor(None, _upload_to_temp_host, media_path)

        if not public_url:
            logger.error("❌ Failed to get public URL for Instagram media")
            return False

        result = False

        if media_type == "photo":
            result = await _post_photo(account_id, access_token, caption, public_url)
        elif media_type == "video":
            result = await _post_video(account_id, access_token, caption, public_url)
        else:
            logger.debug(f"⏭️  Unsupported IG media type: {media_type}")
            return False

        if result:
            _post_timestamps.append(time.time())
            logger.info(f"✅ Posted to Instagram: {post_data.get('channel_name', '')}")
        else:
            logger.error("❌ Failed to post to Instagram")

        return result

    except Exception as e:
        logger.error(f"❌ Instagram sender error: {e}", exc_info=True)
        return False



def _wait_for_media_processing(container_id: str, token: str, max_retries: int = 10) -> bool:
    """
    Poll the container status until it is FINISHED or fails.
    Returns True if ready to publish, False on error/timeout.
    """
    url = f"{GRAPH_API_BASE}/{container_id}"
    params = {"fields": "status_code", "access_token": token}
    
    for i in range(max_retries):
        try:
            resp = http_requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status_code", "")
                if status == "FINISHED":
                    return True
                elif status == "ERROR":
                    logger.error(f"❌ Media container {container_id} failed processing")
                    return False
                elif status == "IN_PROGRESS":
                    pass # Continue waiting
                else: 
                     # Sometimes empty or ready immediately without status_code field for images?
                     # If status_code is missing, it might be ready.
                     # But for 9007 error, it usually means IN_PROGRESS.
                     pass
            
            time.sleep(2) # Wait 2s between checks
        except Exception as e:
            logger.warning(f"⚠️ Error checking status: {e}")
            time.sleep(2)
            
    return True # Assume ready if timeout, or try anyway? 
    # Actually if we time out, we should probably return True and let publish try (and fail if not ready).
    # But better to return False if we know it's stuck. 
    # Let's return True to attempt publish as last resort.


async def _post_photo(account_id: str, token: str, caption: str, image_url: str) -> bool:
    """Post a photo to Instagram via Graph API."""
    loop = asyncio.get_event_loop()

    def _create_and_publish():
        # Step 1: Create media container
        container_url = f"{GRAPH_API_BASE}/{account_id}/media"
        container_resp = http_requests.post(container_url, data={
            "image_url": image_url,
            "caption": caption,
            "access_token": token,
        }, timeout=30)

        if container_resp.status_code != 200:
            logger.error(f"❌ IG container creation failed: {container_resp.status_code} - {container_resp.text}")
            return False

        container_data = container_resp.json()
        creation_id = container_data.get("id")
        if not creation_id:
            logger.error(f"❌ IG no creation_id returned: {container_data}")
            return False

        # Wait for processing (Fix for 9007 error)
        _wait_for_media_processing(creation_id, token)

        # Step 2: Publish the container
        publish_url = f"{GRAPH_API_BASE}/{account_id}/media_publish"
        publish_resp = http_requests.post(publish_url, data={
            "creation_id": creation_id,
            "access_token": token,
        }, timeout=30)

        if publish_resp.status_code == 200:
            post_id = publish_resp.json().get("id")
            logger.debug(f"📸 Instagram photo posted: {post_id}")
            return True
        else:
            logger.error(f"❌ IG publish failed: {publish_resp.status_code} - {publish_resp.text}")
            return False

    return await loop.run_in_executor(None, _create_and_publish)


async def _post_video(account_id: str, token: str, caption: str, video_url: str) -> bool:
    """Post a video (Reel) to Instagram via Graph API. Polls for processing completion."""
    loop = asyncio.get_event_loop()

    def _create_container():
        container_url = f"{GRAPH_API_BASE}/{account_id}/media"
        container_resp = http_requests.post(container_url, data={
            "video_url": video_url,
            "caption": caption,
            "media_type": "REELS",
            "access_token": token,
        }, timeout=60)

        if container_resp.status_code != 200:
            logger.error(f"❌ IG video container failed: {container_resp.status_code} - {container_resp.text}")
            return None

        return container_resp.json().get("id")

    creation_id = await loop.run_in_executor(None, _create_container)
    if not creation_id:
        return False

    # Poll for video processing (uses _wait_for_media_processing logic but custom for video timeout/logic)
    # Actually we can reuse _wait_for_media_processing but video takes longer.
    # Let's keep existing _post_video logic or enable reuse.
    # Existing _post_video logic is fine.

    # Poll for video processing completion (can take a while)
    max_polls = 30
    for i in range(max_polls):
        await asyncio.sleep(10)  # Check every 10 seconds

        def _check_status():
            status_url = f"{GRAPH_API_BASE}/{creation_id}"
            resp = http_requests.get(status_url, params={
                "fields": "status_code",
                "access_token": token,
            }, timeout=15)
            if resp.status_code == 200:
                return resp.json().get("status_code")
            return None

        status = await loop.run_in_executor(None, _check_status)

        if status == "FINISHED":
            # Publish
            def _publish():
                publish_url = f"{GRAPH_API_BASE}/{account_id}/media_publish"
                resp = http_requests.post(publish_url, data={
                    "creation_id": creation_id,
                    "access_token": token,
                }, timeout=30)
                if resp.status_code == 200:
                    post_id = resp.json().get("id")
                    logger.debug(f"🎬 Instagram video posted: {post_id}")
                    return True
                else:
                    logger.error(f"❌ IG video publish failed: {resp.status_code} - {resp.text}")
                    return False

            return await loop.run_in_executor(None, _publish)

        elif status == "ERROR":
            logger.error("❌ Instagram video processing failed")
            return False
        else:
            logger.debug(f"⏳ IG video processing... ({i+1}/{max_polls})")

    logger.error("❌ Instagram video processing timed out")
    return False


async def _post_carousel(account_id: str, token: str, caption: str, media_items: list) -> bool:
    """
    Post a Carousel (Sidecar) to Instagram.
    Args:
        media_items: List of dicts {'path': str, 'type': str}
    """
    loop = asyncio.get_event_loop()

    def _execute_carousel():
        # Step 1: Upload all media and create Item Containers
        child_ids = []
        
        for item in media_items:
            path = item.get("path")
            mtype = item.get("type", "photo")
            
            if not path or not Path(path).exists():
                continue

            # Upload to temp host
            media_url = _upload_to_temp_host(path)
            if not media_url:
                continue

            # Create Item Container
            url = f"{GRAPH_API_BASE}/{account_id}/media"
            payload = {
                "access_token": token,
                "is_carousel_item": "true",
            }
            
            if mtype == "video":
                payload["video_url"] = media_url
                payload["media_type"] = "VIDEO" # Video in carousel
            else:
                payload["image_url"] = media_url
                # image doesn't need media_type param for item container if image_url is present, 
                # but 'IMAGE' is default.

            resp = http_requests.post(url, data=payload, timeout=60)
            
            if resp.status_code != 200:
                logger.error(f"❌ IG carousel item failed: {resp.text}")
                continue
                
            child_id = resp.json().get("id")
            if child_id:
                # Wait for item to be ready before adding to list? 
                # Docs say "Ensure all items are FINISHED before creating carousel container".
                _wait_for_media_processing(child_id, token)
                child_ids.append(child_id)
            
            # Rate limit safety
            time.sleep(2)

        if not child_ids:
            logger.error("❌ No valid items created for carousel")
            return False

        # Step 2: Create Carousel Container
        carousel_url = f"{GRAPH_API_BASE}/{account_id}/media"
        carousel_payload = {
            "media_type": "CAROUSEL",
            "caption": caption,
            "children": ",".join(child_ids), # Comma-separated IDs
            "access_token": token,
        }
        
        resp = http_requests.post(carousel_url, data=carousel_payload, timeout=60)
        if resp.status_code != 200:
             logger.error(f"❌ IG carousel container failed: {resp.text}")
             return False

        creation_id = resp.json().get("id")
        if not creation_id:
             return False

        # Wait for carousel container? 
        # "Once the container is created, you can publish it." 
        # But maybe safer to wait too.
        _wait_for_media_processing(creation_id, token)

        # Step 3: Publish
        publish_url = f"{GRAPH_API_BASE}/{account_id}/media_publish"
        pub_resp = http_requests.post(publish_url, data={
            "creation_id": creation_id,
            "access_token": token,
        }, timeout=60)

        if pub_resp.status_code == 200:
            post_id = pub_resp.json().get("id")
            logger.info(f"✅ Posted Carousel to Instagram: {post_id}")
            return True
        else:
            logger.error(f"❌ IG carousel publish failed: {pub_resp.text}")
            return False

    return await loop.run_in_executor(None, _execute_carousel)

