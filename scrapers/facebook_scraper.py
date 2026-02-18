"""
Auto News Scraper - Facebook Page Scraper
Polls Facebook page feeds via Graph API for new posts.
"""

import asyncio
import logging
from datetime import datetime, timezone

import requests as http_requests

import config
from database import is_duplicate, mark_sent, log_activity
from filters.content_filter import should_forward
from media.media_handler import download_url_media
from sender.telegram_sender import send_to_channel
from sender.facebook_sender import send_to_facebook
from sender.instagram_sender import send_to_instagram

logger = logging.getLogger("scraper.facebook")


class FacebookScraper:
    """Polls Facebook pages for new posts via Graph API."""

    def __init__(self):
        self.running = False
        self._last_post_times = {}  # Track last seen post time per page

    async def start(self):
        """Initialize and start the Facebook scraper polling loop."""
        token = config.FACEBOOK_PAGE_ACCESS_TOKEN
        if not token:
            logger.warning("⚠️  Facebook Page Access Token not configured. Skipping Facebook scraper.")
            await log_activity("warning", "Facebook scraper not configured (no token)", "facebook")
            return

        self.running = True
        logger.info("✅ Facebook scraper initialized")
        await log_activity("info", "Facebook scraper started", "facebook")

        # Polling loop
        while self.running:
            try:
                settings = config.load_settings()
                pages = settings.get("facebook_sources", [])

                if not pages:
                    logger.debug("⚠️  No Facebook pages configured to monitor")
                    await asyncio.sleep(config.FACEBOOK_POLL_INTERVAL)
                    continue

                for page_id in pages:
                    if not self.running:
                        break
                    await self._poll_page(page_id, token, settings)
                    await asyncio.sleep(3)  # Small delay between pages

                await asyncio.sleep(config.FACEBOOK_POLL_INTERVAL)

            except asyncio.CancelledError:
                logger.info("🛑 Facebook scraper stopped")
                break
            except Exception as e:
                logger.error(f"❌ Facebook polling error: {e}", exc_info=True)
                await log_activity("error", f"Polling error: {str(e)}", "facebook")
                await asyncio.sleep(30)

    async def _poll_page(self, page_id: str, token: str, settings: dict):
        """Poll recent posts from a Facebook page."""
        try:
            url = f"https://graph.facebook.com/{config.FACEBOOK_API_VERSION}/{page_id}/feed"
            params = {
                "access_token": token,
                "fields": "id,message,created_time,full_picture,attachments{media_type,media,url,subattachments}",
                "limit": 10,
            }

            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: http_requests.get(url, params=params, timeout=30)
            )

            if resp.status_code != 200:
                error_data = resp.json().get("error", {})
                logger.error(f"❌ Facebook API error for page {page_id}: {error_data.get('message', resp.text)}")
                return

            data = resp.json()
            posts = data.get("data", [])

            if not posts:
                return

            # Get page name for display
            page_name = await self._get_page_name(page_id, token)

            for post in reversed(posts):  # Process oldest first
                await self._process_post(post, page_id, page_name, settings)

        except Exception as e:
            logger.error(f"❌ Error polling Facebook page {page_id}: {e}", exc_info=True)

    async def _get_page_name(self, page_id: str, token: str) -> str:
        """Get the page name from its ID."""
        try:
            url = f"https://graph.facebook.com/{config.FACEBOOK_API_VERSION}/{page_id}"
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: http_requests.get(url, params={
                    "access_token": token,
                    "fields": "name",
                }, timeout=10)
            )
            if resp.status_code == 200:
                return resp.json().get("name", page_id)
        except Exception:
            pass
        return page_id

    async def _process_post(self, post: dict, page_id: str, page_name: str, settings: dict):
        """Process a single Facebook post and forward it."""
        post_id = post.get("id", "")
        source_id = f"fb_{post_id}"

        # Check for duplicates
        if await is_duplicate("facebook", source_id):
            return

        text = post.get("message", "")

        if not text:
            return  # Skip posts without text

        # Apply content filter
        if not should_forward(text, settings):
            logger.debug(f"🚫 Filtered out Facebook post from {page_name}")
            return

        logger.info(f"📘 New post from [{page_name}]: {text[:80]}...")

        # Download media if present
        media_path = None
        media_type = None

        full_picture = post.get("full_picture")
        attachments = post.get("attachments", {}).get("data", [])

        if attachments:
            attachment = attachments[0]
            att_media_type = attachment.get("media_type", "")

            if att_media_type == "video":
                # Try to get video URL from media
                media_info = attachment.get("media", {})
                video_url = media_info.get("source")
                if video_url:
                    media_path, media_type = await download_url_media(video_url, "video")
            elif att_media_type == "photo" and full_picture:
                media_path, media_type = await download_url_media(full_picture, "photo")
            elif full_picture:
                media_path, media_type = await download_url_media(full_picture, "photo")
        elif full_picture:
            media_path, media_type = await download_url_media(full_picture, "photo")

        # Prepare post data
        post_data = {
            "source": "facebook",
            "source_id": source_id,
            "channel_name": page_name,
            "text": text,
            "media_path": media_path,
            "media_type": media_type,
            "original_link": f"https://facebook.com/{post_id}",
        }

        # Send to Telegram channel
        tg_sent = await send_to_channel(post_data)

        # Send to Facebook page (skip if source IS facebook to avoid loops)
        fb_sent = False

        # Send to Instagram
        ig_sent = False
        if settings.get("instagram_posting_enabled", False):
            ig_sent = await send_to_instagram(post_data)

        # Cleanup media
        if media_path:
            from media.media_handler import cleanup_media
            cleanup_media(media_path)

        # Mark as sent
        await mark_sent(
            "facebook", source_id, text,
            title=text[:100],
            telegram=tg_sent, facebook=fb_sent, instagram=ig_sent
        )

        await log_activity(
            "info",
            f"Forwarded from [{page_name}] → TG:{'✅' if tg_sent else '❌'} IG:{'✅' if ig_sent else '⏭️'}",
            "facebook"
        )

    async def stop(self):
        """Stop the Facebook scraper."""
        self.running = False
        logger.info("🛑 Facebook scraper stopped")
