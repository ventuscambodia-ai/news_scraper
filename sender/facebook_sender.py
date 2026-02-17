"""
Auto News Scraper - Facebook Page Sender
Posts to a Facebook Page via the Graph API.
"""

import asyncio
import logging
from pathlib import Path

import requests

import config
from media.media_handler import cleanup_media

logger = logging.getLogger("sender.facebook")

GRAPH_API_BASE = f"https://graph.facebook.com/{config.FACEBOOK_API_VERSION}"


def _format_facebook_post(post_data: dict) -> str:
    """
    Format post content for Facebook.

    Format:
        📰 Source: Channel/Account Name

        Post text content here...

        🔗 Original: https://x.com/...
    """
    parts = []

    source = post_data.get("source", "unknown")
    channel_name = post_data.get("channel_name", "Unknown")

    if source == "telegram":
        parts.append(f"📡 Telegram • {channel_name}")
    elif source == "x":
        parts.append(f"🐦 X (Twitter) • {channel_name}")
    else:
        parts.append(f"📰 {source} • {channel_name}")

    parts.append("")
    parts.append("─" * 30)
    parts.append("")

    text = post_data.get("text", "")
    if text:
        if len(text) > 5000:
            text = text[:5000] + "..."
        parts.append(text)

    original_link = post_data.get("original_link")
    if original_link:
        parts.append("")
        parts.append(f"🔗 Original: {original_link}")

    return "\n".join(parts)


async def send_to_facebook(post_data: dict) -> bool:
    """
    Post to the Facebook Page.

    Supports:
        - Text-only posts
        - Text + photo posts
        - Text + video posts

    Args:
        post_data: Dict with keys: source, source_id, channel_name, text,
                   media_path, media_type, original_link

    Returns:
        True if posted successfully, False otherwise
    """
    page_token = config.FACEBOOK_PAGE_ACCESS_TOKEN
    page_id = config.FACEBOOK_PAGE_ID

    if not page_token or not page_id:
        logger.debug("⏭️  Facebook not configured, skipping")
        return False

    settings = config.load_settings()
    if not settings.get("facebook_posting_enabled", False):
        logger.debug("⏭️  Facebook posting disabled")
        return False

    try:
        message_text = _format_facebook_post(post_data)
        media_path = post_data.get("media_path")
        media_type = post_data.get("media_type")

        result = False

        if media_path and Path(media_path).exists():
            if media_type == "photo":
                result = await _post_photo(page_id, page_token, message_text, media_path)
            elif media_type == "video":
                result = await _post_video(page_id, page_token, message_text, media_path)
            else:
                result = await _post_text(page_id, page_token, message_text)
        else:
            result = await _post_text(page_id, page_token, message_text)

        if result:
            logger.info(f"✅ Posted to Facebook: {post_data.get('channel_name', '')}")
        else:
            logger.error(f"❌ Failed to post to Facebook")

        return result

    except Exception as e:
        logger.error(f"❌ Facebook sender error: {e}", exc_info=True)
        return False


async def _post_text(page_id: str, token: str, message: str) -> bool:
    """Post a text-only update to the Facebook Page."""
    url = f"{GRAPH_API_BASE}/{page_id}/feed"
    payload = {
        "message": message,
        "access_token": token,
    }

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None, lambda: requests.post(url, data=payload)
    )

    if response.status_code == 200:
        post_id = response.json().get("id")
        logger.debug(f"📘 Facebook text post created: {post_id}")
        return True
    else:
        logger.error(f"❌ Facebook text post failed: {response.status_code} - {response.text}")
        return False


async def _post_photo(page_id: str, token: str, message: str, photo_path: str) -> bool:
    """Post a photo with caption to the Facebook Page."""
    url = f"{GRAPH_API_BASE}/{page_id}/photos"

    loop = asyncio.get_event_loop()

    def _upload():
        with open(photo_path, "rb") as photo_file:
            return requests.post(
                url,
                data={"message": message, "access_token": token},
                files={"source": photo_file},
            )

    response = await loop.run_in_executor(None, _upload)

    if response.status_code == 200:
        post_id = response.json().get("id")
        logger.debug(f"📘 Facebook photo post created: {post_id}")
        return True
    else:
        logger.error(f"❌ Facebook photo post failed: {response.status_code} - {response.text}")
        return False


async def _post_video(page_id: str, token: str, message: str, video_path: str) -> bool:
    """Post a video with description to the Facebook Page."""
    url = f"{GRAPH_API_BASE}/{page_id}/videos"

    loop = asyncio.get_event_loop()

    def _upload():
        with open(video_path, "rb") as video_file:
            return requests.post(
                url,
                data={"description": message, "access_token": token},
                files={"source": video_file},
            )

    response = await loop.run_in_executor(None, _upload)

    if response.status_code == 200:
        post_id = response.json().get("id")
        logger.debug(f"📘 Facebook video post created: {post_id}")
        return True
    else:
        logger.error(f"❌ Facebook video post failed: {response.status_code} - {response.text}")
        return False
