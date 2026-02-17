"""
Auto News Scraper - Configuration Module
Loads settings from .env and provides centralized config access.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
MEDIA_TMP_DIR = BASE_DIR / "media" / "tmp"
LOGS_DIR = BASE_DIR / "logs"
SETTINGS_FILE = DATA_DIR / "settings.json"

# Create directories
DATA_DIR.mkdir(exist_ok=True)
MEDIA_TMP_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# --- Telegram User Client (Scraping) ---
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE", "")
TELEGRAM_SESSION_NAME = "news_scraper_session"

# --- Telegram Bot (Sending) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")

# --- X (Twitter) ---
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")
X_POLL_INTERVAL = int(os.getenv("X_POLL_INTERVAL", "60"))  # seconds

# --- Facebook ---
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")
FACEBOOK_POSTING_ENABLED = os.getenv("FACEBOOK_POSTING_ENABLED", "true").lower() == "true"
FACEBOOK_API_VERSION = "v21.0"

# --- Dashboard ---
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))
DASHBOARD_SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "auto-news-scraper-secret")


# --- Dynamic Settings (persisted to JSON) ---
DEFAULT_SETTINGS = {
    "telegram_sources": [],       # List of Telegram channel usernames/IDs to monitor
    "x_accounts": [],             # List of X usernames to monitor (without @)
    "x_hashtags": [],             # List of hashtags to monitor (without #)
    "filter_mode": "all",         # "all" = forward everything (except excludes), "include" = only matching keywords
    "filter_include_keywords": [],  # Keywords to include (used in "include" mode)
    "filter_exclude_keywords": [],  # Keywords to exclude (always active)
    "facebook_posting_enabled": FACEBOOK_POSTING_ENABLED,
}


def load_settings() -> dict:
    """Load settings from the JSON file, or return defaults."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                saved = json.load(f)
                # Merge with defaults to ensure new keys are always present
                merged = {**DEFAULT_SETTINGS, **saved}
                return merged
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict):
    """Save settings to the JSON file."""
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


def get_settings() -> dict:
    """Get current settings (convenience alias)."""
    return load_settings()


def update_settings(updates: dict) -> dict:
    """Update specific settings and save to disk."""
    settings = load_settings()
    settings.update(updates)
    save_settings(settings)
    return settings


def is_configured() -> dict:
    """Check which API credentials are configured."""
    return {
        "telegram_user": bool(TELEGRAM_API_ID and TELEGRAM_API_HASH),
        "telegram_bot": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID),
        "x_api": bool(X_BEARER_TOKEN),
        "facebook": bool(FACEBOOK_PAGE_ACCESS_TOKEN and FACEBOOK_PAGE_ID),
    }
