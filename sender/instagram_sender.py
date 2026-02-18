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
    try:
        with open(file_path, "rb") as f:
            resp = http_requests.post(
                "https://0x0.st",
                files={"file": f},
                timeout=120,
            )
        if resp.status_code == 200:
            url = resp.text.strip()
            logger.debug(f"📤 Uploaded to temp host: {url}")
            return url
        else:
            logger.error(f"❌ Temp upload failed: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Temp upload error: {e}")
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
        logger.debug("⏭️  Instagram not configured, skipping")
        return False

    settings = config.load_settings()
    if not settings.get("instagram_posting_enabled", False):
        logger.debug("⏭️  Instagram posting disabled")
        return False

    media_path = post_data.get("media_path")
    media_type = post_data.get("media_type")

    # Instagram requires media — skip text-only posts
    if not media_path or not Path(media_path).exists():
        logger.debug("⏭️  No media for Instagram (IG requires photo/video), skipping")
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
