"""
Auto News Scraper - Media Handler
Downloads and manages media files (images, videos) from scraped posts.
"""

import asyncio
import logging
import os
import uuid
from pathlib import Path

import aiohttp

import config

logger = logging.getLogger("media")


async def download_telegram_media(client, message) -> tuple:
    """
    Download media from a Telegram message.

    Args:
        client: Telethon client
        message: Telegram message object

    Returns:
        Tuple of (file_path, media_type) or (None, None)
    """
    try:
        if not message.media:
            return None, None

        # Determine media type
        from telethon.tl.types import (
            MessageMediaPhoto,
            MessageMediaDocument,
            DocumentAttributeVideo,
        )

        media_type = None
        extension = ".tmp"

        if isinstance(message.media, MessageMediaPhoto):
            media_type = "photo"
            extension = ".jpg"
        elif isinstance(message.media, MessageMediaDocument):
            doc = message.media.document
            mime = doc.mime_type or ""

            if mime.startswith("video/"):
                media_type = "video"
                extension = ".mp4"
            elif mime.startswith("image/"):
                media_type = "photo"
                extension = ".jpg" if "jpeg" in mime or "jpg" in mime else ".png"
            elif any(isinstance(attr, DocumentAttributeVideo) for attr in (doc.attributes or [])):
                media_type = "video"
                extension = ".mp4"
            else:
                # Unsupported media type (stickers, files, etc.)
                logger.debug(f"⏭️  Unsupported media type: {mime}")
                return None, None

        if not media_type:
            return None, None

        # Generate unique filename
        filename = f"{uuid.uuid4().hex[:12]}{extension}"
        file_path = config.MEDIA_TMP_DIR / filename

        # Download the media
        logger.debug(f"⬇️  Downloading {media_type}: {filename}")
        await client.download_media(message, file=str(file_path))

        if file_path.exists():
            size_mb = file_path.stat().st_size / (1024 * 1024)
            logger.info(f"✅ Downloaded {media_type}: {filename} ({size_mb:.1f}MB)")
            return str(file_path), media_type
        else:
            logger.warning(f"⚠️  Download failed: file not created")
            return None, None

    except Exception as e:
        logger.error(f"❌ Media download error: {e}", exc_info=True)
        return None, None


async def download_x_media(media_obj) -> tuple:
    """
    Download media from an X (Twitter) tweet.

    Args:
        media_obj: Tweepy media object

    Returns:
        Tuple of (file_path, media_type) or (None, None)
    """
    try:
        media_type_str = getattr(media_obj, "type", None)
        url = None

        if media_type_str == "photo":
            url = media_obj.url
            extension = ".jpg"
            media_type = "photo"
        elif media_type_str in ("video", "animated_gif"):
            # Get the best quality video variant
            variants = getattr(media_obj, "variants", None)
            if variants:
                # Filter for mp4 and sort by bitrate
                mp4_variants = [v for v in variants if v.get("content_type") == "video/mp4"]
                if mp4_variants:
                    mp4_variants.sort(key=lambda v: v.get("bit_rate", 0), reverse=True)
                    url = mp4_variants[0]["url"]
                elif variants:
                    url = variants[0].get("url")
            extension = ".mp4"
            media_type = "video"
        else:
            logger.debug(f"⏭️  Unsupported X media type: {media_type_str}")
            return None, None

        if not url:
            logger.warning("⚠️  No media URL found")
            return None, None

        # Download the file
        filename = f"{uuid.uuid4().hex[:12]}{extension}"
        file_path = config.MEDIA_TMP_DIR / filename

        logger.debug(f"⬇️  Downloading X {media_type}: {url[:80]}...")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    with open(file_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)

                    size_mb = file_path.stat().st_size / (1024 * 1024)
                    logger.info(f"✅ Downloaded X {media_type}: {filename} ({size_mb:.1f}MB)")
                    return str(file_path), media_type
                else:
                    logger.warning(f"⚠️  X media download failed: HTTP {resp.status}")
                    return None, None

    except Exception as e:
        logger.error(f"❌ X media download error: {e}", exc_info=True)
        return None, None


def cleanup_media(file_path: str):
    """Delete a temporary media file after it's been sent."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.debug(f"🗑️  Cleaned up: {os.path.basename(file_path)}")
    except Exception as e:
        logger.warning(f"⚠️  Cleanup failed: {e}")


def cleanup_all_temp():
    """Clean up all temporary media files."""
    tmp_dir = config.MEDIA_TMP_DIR
    if tmp_dir.exists():
        count = 0
        for f in tmp_dir.iterdir():
            if f.is_file():
                f.unlink()
                count += 1
        if count:
            logger.info(f"🗑️  Cleaned up {count} temp files")
