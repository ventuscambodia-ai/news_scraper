"""
Auto News Scraper - Telegram Channel Scraper
Uses Telethon user client to listen for new messages in monitored channels in real-time.
"""

import asyncio
import logging
from telethon import TelegramClient, events
from telethon.tl.types import (
    MessageMediaPhoto,
    MessageMediaDocument,
    DocumentAttributeVideo,
    DocumentAttributeAnimated,
)

import config
from database import is_duplicate, mark_sent, log_activity
from filters.content_filter import should_forward
from media.media_handler import download_telegram_media
from sender.telegram_sender import send_to_channel
from sender.facebook_sender import send_to_facebook

logger = logging.getLogger("scraper.telegram")


class TelegramScraper:
    """Monitors multiple Telegram channels for new posts in real-time."""

    def __init__(self):
        self.client = None
        self.running = False

    async def start(self):
        """Initialize and start the Telegram user client."""
        api_id = config.TELEGRAM_API_ID
        api_hash = config.TELEGRAM_API_HASH

        if not api_id or not api_hash:
            logger.warning("⚠️  Telegram API credentials not configured. Skipping Telegram scraper.")
            await log_activity("warning", "Telegram API credentials not configured", "telegram")
            return

        try:
            api_id = int(api_id)
        except ValueError:
            logger.error("❌ TELEGRAM_API_ID must be a number")
            return

        self.client = TelegramClient(
            str(config.BASE_DIR / config.TELEGRAM_SESSION_NAME),
            api_id,
            api_hash
        )

        await self.client.start(phone=config.TELEGRAM_PHONE)
        self.running = True

        logger.info("✅ Telegram user client connected")
        await log_activity("info", "Telegram scraper started", "telegram")

        # Get monitored channels from settings
        settings = config.load_settings()
        channels = settings.get("telegram_sources", [])

        if not channels:
            logger.warning("⚠️  No Telegram channels configured to monitor")
            await log_activity("warning", "No Telegram channels configured", "telegram")
            return

        logger.info(f"📡 Monitoring {len(channels)} Telegram channel(s): {channels}")
        await log_activity("info", f"Monitoring {len(channels)} channel(s): {', '.join(str(c) for c in channels)}", "telegram")

        # Register event handler for new messages
        @self.client.on(events.NewMessage(chats=channels))
        async def on_new_message(event):
            await self._handle_message(event)

        # Keep running until stopped
        try:
            await self.client.run_until_disconnected()
        except asyncio.CancelledError:
            logger.info("🛑 Telegram scraper stopped")

    async def _handle_message(self, event):
        """Process a new message from a monitored channel."""
        try:
            message = event.message
            source_id = f"tg_{message.chat_id}_{message.id}"
            text = message.text or message.message or ""

            if not text and not message.media:
                return  # Skip empty messages

            # Get channel/chat info
            chat = await event.get_chat()
            channel_name = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat.id)

            # Check for duplicates
            if await is_duplicate("telegram", source_id):
                logger.debug(f"⏭️  Duplicate skipped: {source_id}")
                return

            # Apply content filter
            settings = config.load_settings()
            if not should_forward(text, settings):
                logger.debug(f"🚫 Filtered out: {text[:50]}...")
                await log_activity("debug", f"Filtered out message from {channel_name}", "telegram")
                return

            logger.info(f"📨 New post from [{channel_name}]: {text[:80]}...")

            # Download media if present
            media_path = None
            media_type = None

            if message.media:
                media_path, media_type = await download_telegram_media(self.client, message)

            # Prepare post data
            post_data = {
                "source": "telegram",
                "source_id": source_id,
                "channel_name": channel_name,
                "text": text,
                "media_path": media_path,
                "media_type": media_type,  # "photo" or "video"
                "original_link": None,  # No link for Telegram posts per user spec
            }

            # Send to Telegram channel
            tg_sent = await send_to_channel(post_data)

            # Send to Facebook page
            fb_sent = False
            if settings.get("facebook_posting_enabled", False):
                fb_sent = await send_to_facebook(post_data)

            # Cleanup media file after ALL senders have finished
            if media_path:
                from media.media_handler import cleanup_media
                cleanup_media(media_path)

            # Mark as sent
            await mark_sent(
                "telegram", source_id, text,
                title=text[:100] if text else channel_name,
                telegram=tg_sent, facebook=fb_sent
            )

            await log_activity(
                "info",
                f"Forwarded from [{channel_name}] → TG:{'✅' if tg_sent else '❌'} FB:{'✅' if fb_sent else '⏭️'}",
                "telegram"
            )

        except Exception as e:
            logger.error(f"❌ Error processing Telegram message: {e}", exc_info=True)
            await log_activity("error", f"Error: {str(e)}", "telegram")

    async def stop(self):
        """Stop the Telegram scraper."""
        self.running = False
        if self.client:
            await self.client.disconnect()
            logger.info("🛑 Telegram client disconnected")

    async def reload_channels(self):
        """Reload monitored channels (called when settings change)."""
        # Telethon doesn't easily support dynamic channel changes
        # A restart is needed for channel list changes
        logger.info("🔄 Channel list changed - restart required for changes to take effect")
        await log_activity("info", "Channel list updated - restart scraper to apply", "telegram")
