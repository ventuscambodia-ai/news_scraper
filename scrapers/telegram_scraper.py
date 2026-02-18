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
from media.media_handler import download_telegram_media, cleanup_media
from sender.telegram_sender import send_to_channel
from sender.facebook_sender import send_to_facebook
from sender.instagram_sender import send_to_instagram

logger = logging.getLogger("scraper.telegram")


class TelegramScraper:
    """Monitors multiple Telegram channels for new posts in real-time."""

    def __init__(self):
        self.client = None
        self.running = False
        # Album buffering: grouped_id -> {messages: [], timer: Task}
        self._album_buffer = {}
        self._album_lock = asyncio.Lock()
        self._ALBUM_WAIT_SECONDS = 2  # Wait time to collect all album messages

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

        await self.client.connect()

        # Check if we have a valid session (already authorized)
        if not await self.client.is_user_authorized():
            import sys
            if sys.stdin.isatty():
                await self.client.start(phone=config.TELEGRAM_PHONE)
            else:
                logger.error("❌ Telegram session not authorized. Please authenticate locally first and deploy the session file.")
                await log_activity("error", "Telegram session not authorized — authenticate locally first", "telegram")
                await self.client.disconnect()
                return

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

            # Check if this is part of an album (grouped messages)
            if message.grouped_id:
                await self._buffer_album_message(event)
                return

            # Single message (not album)
            await self._process_single_message(event)

        except Exception as e:
            logger.error(f"❌ Error processing Telegram message: {e}", exc_info=True)
            await log_activity("error", f"Error: {str(e)}", "telegram")

    async def _process_single_message(self, event):
        """Process a single (non-album) message."""
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
            "media_type": media_type,
            "original_link": None,
        }

        # Send to Telegram channel
        tg_sent = await send_to_channel(post_data)

        # Send to Facebook page
        fb_sent = False
        if settings.get("facebook_posting_enabled", False):
            fb_sent = await send_to_facebook(post_data)

        # Send to Instagram
        ig_sent = False
        if settings.get("instagram_posting_enabled", False):
            ig_sent = await send_to_instagram(post_data)

        # Cleanup media file after ALL senders have finished
        if media_path:
            cleanup_media(media_path)

        # Mark as sent
        await mark_sent(
            "telegram", source_id, text,
            title=text[:100] if text else channel_name,
            telegram=tg_sent, facebook=fb_sent, instagram=ig_sent
        )

        await log_activity(
            "info",
            f"Forwarded from [{channel_name}] → TG:{'✅' if tg_sent else '❌'} FB:{'✅' if fb_sent else '⏭️'} IG:{'✅' if ig_sent else '⏭️'}",
            "telegram"
        )

    async def _buffer_album_message(self, event):
        """Buffer an album message and schedule processing after all parts arrive."""
        message = event.message
        grouped_id = message.grouped_id

        async with self._album_lock:
            if grouped_id not in self._album_buffer:
                self._album_buffer[grouped_id] = {
                    "messages": [],
                    "event": event,
                    "timer": None,
                }

            self._album_buffer[grouped_id]["messages"].append(message)

            # Cancel previous timer and set a new one
            if self._album_buffer[grouped_id]["timer"]:
                self._album_buffer[grouped_id]["timer"].cancel()

            self._album_buffer[grouped_id]["timer"] = asyncio.create_task(
                self._process_album_after_delay(grouped_id)
            )

    async def _process_album_after_delay(self, grouped_id):
        """Wait for all album messages to arrive, then process the album."""
        await asyncio.sleep(self._ALBUM_WAIT_SECONDS)

        async with self._album_lock:
            album_data = self._album_buffer.pop(grouped_id, None)

        if not album_data:
            return

        try:
            messages = album_data["messages"]
            event = album_data["event"]

            # Sort by message ID to maintain order
            messages.sort(key=lambda m: m.id)

            # Use the first message for metadata
            first_msg = messages[0]
            source_id = f"tg_{first_msg.chat_id}_album_{grouped_id}"

            # Combine text from all messages (usually only one has text)
            text = ""
            for msg in messages:
                msg_text = msg.text or msg.message or ""
                if msg_text and not text:
                    text = msg_text

            if not text and not any(m.media for m in messages):
                return

            # Get channel/chat info
            chat = await event.get_chat()
            channel_name = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat.id)

            # Check for duplicates
            if await is_duplicate("telegram", source_id):
                logger.debug(f"⏭️  Duplicate album skipped: {source_id}")
                return

            # Apply content filter
            settings = config.load_settings()
            if not should_forward(text, settings):
                logger.debug(f"🚫 Filtered out album: {text[:50]}...")
                return

            logger.info(f"📸 Album from [{channel_name}] ({len(messages)} items): {text[:80]}...")

            # Download all media from the album
            media_paths = []
            first_media_path = None
            first_media_type = None

            for msg in messages:
                if msg.media:
                    path, mtype = await download_telegram_media(self.client, msg)
                    if path:
                        media_paths.append({"path": path, "type": mtype})
                        if not first_media_path:
                            first_media_path = path
                            first_media_type = mtype

            # Prepare post data
            post_data = {
                "source": "telegram",
                "source_id": source_id,
                "channel_name": channel_name,
                "text": text,
                "media_path": first_media_path,  # First image for Facebook
                "media_type": first_media_type,
                "media_paths": media_paths,  # All images for Telegram album
                "original_link": None,
            }

            # Send to Telegram channel (as album)
            tg_sent = await send_to_channel(post_data)

            # Send to Facebook page (uses first image)
            fb_sent = False
            if settings.get("facebook_posting_enabled", False):
                fb_sent = await send_to_facebook(post_data)

            # Send to Instagram (uses first image)
            ig_sent = False
            if settings.get("instagram_posting_enabled", False):
                ig_sent = await send_to_instagram(post_data)

            # Cleanup ALL media files
            for mp in media_paths:
                path = mp.get("path", "") if isinstance(mp, dict) else mp
                if path:
                    cleanup_media(path)

            # Mark as sent
            await mark_sent(
                "telegram", source_id, text,
                title=text[:100] if text else channel_name,
                telegram=tg_sent, facebook=fb_sent, instagram=ig_sent
            )

            await log_activity(
                "info",
                f"Forwarded album ({len(media_paths)} media) from [{channel_name}] → TG:{'✅' if tg_sent else '❌'} FB:{'✅' if fb_sent else '⏭️'} IG:{'✅' if ig_sent else '⏭️'}",
                "telegram"
            )

        except Exception as e:
            logger.error(f"❌ Error processing album: {e}", exc_info=True)
            await log_activity("error", f"Album error: {str(e)}", "telegram")

    async def stop(self):
        """Stop the Telegram scraper."""
        self.running = False
        if self.client:
            await self.client.disconnect()
            logger.info("🛑 Telegram client disconnected")

    async def reload_channels(self):
        """Reload monitored channels (called when settings change)."""
        logger.info("🔄 Channel list changed - restart required for changes to take effect")
        await log_activity("info", "Channel list updated - restart scraper to apply", "telegram")
