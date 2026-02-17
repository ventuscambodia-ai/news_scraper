"""
Auto News Scraper - Content Filter
Keyword-based filtering with include/exclude modes.
"""

import logging
import re

logger = logging.getLogger("filter")


def should_forward(text: str, settings: dict) -> bool:
    """
    Determine if a post should be forwarded based on filter settings.

    Modes:
        - "all": Forward everything, except posts matching exclude keywords
        - "include": Only forward posts matching at least one include keyword

    Args:
        text: The post text content
        settings: Current settings dict with filter config

    Returns:
        True if the post should be forwarded, False otherwise
    """
    if not text:
        # Forward media-only posts (no text to filter)
        return True

    text_lower = text.lower()
    filter_mode = settings.get("filter_mode", "all")
    exclude_keywords = settings.get("filter_exclude_keywords", [])
    include_keywords = settings.get("filter_include_keywords", [])

    # Always check exclude list first
    for keyword in exclude_keywords:
        if keyword.lower() in text_lower:
            logger.debug(f"🚫 Excluded by keyword: '{keyword}'")
            return False

    # In "all" mode, forward everything that wasn't excluded
    if filter_mode == "all":
        return True

    # In "include" mode, must match at least one include keyword
    if filter_mode == "include":
        if not include_keywords:
            # No include keywords set = forward nothing in include mode
            logger.debug("🚫 Include mode active but no keywords set")
            return False

        for keyword in include_keywords:
            if keyword.lower() in text_lower:
                logger.debug(f"✅ Included by keyword: '{keyword}'")
                return True

        logger.debug(f"🚫 No include keywords matched")
        return False

    # Default: forward
    return True


def highlight_keywords(text: str, settings: dict) -> str:
    """
    Optionally highlight matched keywords in the text (for display purposes).
    Uses **bold** markdown formatting.
    """
    include_keywords = settings.get("filter_include_keywords", [])
    if not include_keywords:
        return text

    for keyword in include_keywords:
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        text = pattern.sub(f"**{keyword}**", text)

    return text
