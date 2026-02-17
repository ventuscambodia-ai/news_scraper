"""
Auto News Scraper - Telegram Channel Sender
Sends formatted posts to the target Telegram channel via Bot API.
"""

import asyncio
import logging
from pathlib import Path

from telegram import Bot, InputMediaPhoto, InputMediaVideo
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
    Supports single media, multi-image albums, and text-only posts.

    Args:
        post_data: Dict with keys: source, source_id, channel_name, text,
                   media_path, media_type, media_paths, original_link

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
        media_paths = post_data.get("media_paths", [])  # For albums

        sent = False
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # --- ALBUM (multiple images) ---
                if media_paths and len(media_paths) > 1:
                    sent = await _send_album(bot, channel_id, message_text, media_paths)
                    break

                # --- SINGLE MEDIA ---
                elif media_path and Path(media_path).exists():
                    # Check file size - Telegram Bot API limit is 50MB
                    file_size_mb = Path(media_path).stat().st_size / (1024 * 1024)
                    logger.info(f"📎 Media: {media_type}, size: {file_size_mb:.1f}MB")

                    if file_size_mb > 50:
                        logger.warning(f"⚠️  File too large ({file_size_mb:.1f}MB > 50MB), sending text only")
                        await bot.send_message(
                            chat_id=channel_id,
                            text=message_text,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=False,
                        )
                        sent = True
                        break

                    # Telegram caption limit: 1024 chars for media
                    caption = message_text
                    if len(message_text) > 1024:
                        caption = message_text[:1020] + "..."

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

                # --- TEXT ONLY ---
                else:
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


async def _send_album(bot: Bot, channel_id: str, message_text: str, media_paths: list) -> bool:
    """Send multiple photos as an album (media group) to Telegram."""
    try:
        media_group = []
        caption = message_text
        if len(message_text) > 1024:
            caption = message_text[:1020] + "..."

        for i, mp in enumerate(media_paths):
            path = mp.get("path", "") if isinstance(mp, dict) else mp
            mtype = mp.get("type", "photo") if isinstance(mp, dict) else "photo"

            if not path or not Path(path).exists():
                continue

            # Only the first item gets the caption
            item_caption = caption if i == 0 else None

            if mtype == "video":
                with open(path, "rb") as f:
                    media_group.append(InputMediaVideo(
                        media=f.read(),
                        caption=item_caption,
                        parse_mode=ParseMode.HTML if item_caption else None,
                        supports_streaming=True,
                    ))
            else:
                with open(path, "rb") as f:
                    media_group.append(InputMediaPhoto(
                        media=f.read(),
                        caption=item_caption,
                        parse_mode=ParseMode.HTML if item_caption else None,
                    ))

        if not media_group:
            logger.warning("⚠️  No valid media in album, skipping")
            return False

        await bot.send_media_group(chat_id=channel_id, media=media_group)
        logger.info(f"📸 Sent album with {len(media_group)} items")
        return True

    except Exception as e:
        logger.error(f"❌ Album send error: {e}", exc_info=True)
        return False
