"""
Auto News Scraper - Telegram Channel Sender
Sends formatted posts to the target Telegram channel via Bot API.
"""

import asyncio
import logging
from pathlib import Path

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError, RetryAfter

import config

logger = logging.getLogger("sender.telegram")

# Reusable bot instance
_bot = None


def _get_bot() -> Bot:
    """Get or create the Telegram Bot instance."""
    global _bot
    if _bot is None:
        token = config.TELEGRAM_BOT_TOKEN
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN not configured")
        _bot = Bot(token=token)
    return _bot


def _format_message(post_data: dict) -> str:
    """
    Format a post into a nice Telegram message.

    Format:
        📰 Source: [Channel/Account Name]

        Post text content here...

        🔗 Original: https://x.com/...
    """
    parts = []

    # Source header
    source = post_data.get("source", "unknown")
    channel_name = post_data.get("channel_name", "Unknown")

    if source == "telegram":
        parts.append(f"📡 <b>Telegram</b> • {_escape_html(channel_name)}")
    elif source == "x":
        parts.append(f"🐦 <b>X (Twitter)</b> • {_escape_html(channel_name)}")
    else:
        parts.append(f"📰 <b>{_escape_html(source)}</b> • {_escape_html(channel_name)}")

    parts.append("")  # Blank line

    # Post text
    text = post_data.get("text", "")
    if text:
        # Truncate very long posts (Telegram limit is 4096 chars)
        if len(text) > 3500:
            text = text[:3500] + "..."
        parts.append(_escape_html(text))

    # Original link (only for X)
    original_link = post_data.get("original_link")
    if original_link:
        parts.append("")
        parts.append(f'🔗 <a href="{original_link}">View Original</a>')

    return "\n".join(parts)


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


async def send_to_channel(post_data: dict) -> bool:
    """
    Send a post to the Telegram channel.

    Args:
        post_data: Dict with keys: source, source_id, channel_name, text,
                   media_path, media_type, original_link

    Returns:
        True if sent successfully, False otherwise
    """
    token = config.TELEGRAM_BOT_TOKEN
    channel_id = config.TELEGRAM_CHANNEL_ID

    if not token or not channel_id:
        logger.warning("⚠️  Telegram Bot not configured, skipping send")
        return False

    try:
        bot = _get_bot()
        message_text = _format_message(post_data)
        media_path = post_data.get("media_path")
        media_type = post_data.get("media_type")

        sent = False
        max_retries = 3

        for attempt in range(max_retries):
            try:
                if media_path and Path(media_path).exists():
                    # Telegram caption limit: 1024 chars for media
                    caption = message_text
                    send_followup = False

                    if len(message_text) > 1024:
                        # Truncate caption and send full text as follow-up
                        caption = message_text[:1020] + "..."
                        send_followup = True

                    if media_type == "photo":
                        with open(media_path, "rb") as photo:
                            await bot.send_photo(
                                chat_id=channel_id,
                                photo=photo,
                                caption=caption,
                                parse_mode=ParseMode.HTML,
                            )
                        sent = True
                    elif media_type == "video":
                        with open(media_path, "rb") as video:
                            await bot.send_video(
                                chat_id=channel_id,
                                video=video,
                                caption=caption,
                                parse_mode=ParseMode.HTML,
                                supports_streaming=True,
                            )
                        sent = True
                    else:
                        # Fallback: send as document
                        with open(media_path, "rb") as doc:
                            await bot.send_document(
                                chat_id=channel_id,
                                document=doc,
                                caption=caption,
                                parse_mode=ParseMode.HTML,
                            )
                        sent = True

                    # Send full text as follow-up if caption was truncated
                    if sent and send_followup:
                        await bot.send_message(
                            chat_id=channel_id,
                            text=message_text,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                        )
                else:
                    # Text-only message (4096 char limit)
                    await bot.send_message(
                        chat_id=channel_id,
                        text=message_text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=False,
                    )
                    sent = True

                break  # Success

            except RetryAfter as e:
                wait_time = e.retry_after
                logger.warning(f"⏳ Telegram rate limit, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
            except TelegramError as e:
                logger.error(f"❌ Telegram send error (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)

        # Note: media cleanup is handled by the scraper after all senders finish

        if sent:
            logger.info(f"✅ Sent to Telegram channel: {post_data.get('channel_name', '')}")
        else:
            logger.error(f"❌ Failed to send to Telegram after {max_retries} attempts")

        return sent

    except Exception as e:
        logger.error(f"❌ Telegram sender error: {e}", exc_info=True)
        return False
