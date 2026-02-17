"""
Auto News Scraper - Main Entry Point
Starts all scrapers concurrently and manages the application lifecycle.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime

import config
from database import init_db, log_activity
from scrapers.telegram_scraper import TelegramScraper
from scrapers.x_scraper import XScraper
from media.media_handler import cleanup_all_temp


# ─── Logging Setup ───────────────────────────────────────────────────────────

def setup_logging():
    """Configure console + file logging."""
    log_format = "%(asctime)s │ %(name)-20s │ %(levelname)-7s │ %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    # File handler
    log_file = config.LOGS_DIR / f"scraper_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("tweepy").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    return logging.getLogger("main")


# ─── Main Application ────────────────────────────────────────────────────────

async def main():
    """Main application entry point."""
    logger = setup_logging()

    # Banner
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║         📰 AUTO NEWS SCRAPER v1.0               ║")
    print("║    Telegram + X → Telegram Channel + Facebook   ║")
    print("╚══════════════════════════════════════════════════╝")
    print()

    # Initialize database
    logger.info("🗄️  Initializing database...")
    await init_db()

    # Clean up old temp files
    cleanup_all_temp()

    # Check API configuration status
    api_status = config.is_configured()
    logger.info("📋 API Configuration Status:")
    for name, configured in api_status.items():
        status = "✅ Ready" if configured else "❌ Not configured"
        logger.info(f"   {name}: {status}")

    # Load settings
    settings = config.load_settings()
    logger.info(f"📋 Sources configured:")
    logger.info(f"   Telegram channels: {len(settings.get('telegram_sources', []))}")
    logger.info(f"   X accounts: {len(settings.get('x_accounts', []))}")
    logger.info(f"   X hashtags: {len(settings.get('x_hashtags', []))}")
    logger.info(f"   Filter mode: {settings.get('filter_mode', 'all')}")
    logger.info(f"   Facebook posting: {'enabled' if settings.get('facebook_posting_enabled') else 'disabled'}")

    await log_activity("info", "Auto News Scraper started", "system")

    # Create scraper instances
    telegram_scraper = TelegramScraper()
    x_scraper = XScraper()

    # Start dashboard in a separate thread (always runs)
    dashboard_task = None
    try:
        from dashboard.app import start_dashboard_async
        dashboard_task = asyncio.create_task(start_dashboard_async())
        logger.info(f"🌐 Dashboard running at http://localhost:{config.DASHBOARD_PORT}")
    except Exception as e:
        logger.warning(f"⚠️  Dashboard failed to start: {e}")

    # Create tasks list — dashboard is always included
    tasks = []
    if dashboard_task:
        tasks.append(dashboard_task)

    # Helper to wrap scrapers so failures don't crash the app
    async def safe_scraper(name, coro):
        try:
            await coro
        except asyncio.CancelledError:
            logger.info(f"🛑 {name} scraper stopped")
        except Exception as e:
            logger.error(f"❌ {name} scraper failed: {e}")
            await log_activity("error", f"{name} scraper failed: {e}", name.lower())

    if api_status["telegram_user"]:
        tasks.append(asyncio.create_task(safe_scraper("Telegram", telegram_scraper.start())))
        logger.info("🚀 Telegram scraper starting...")
    else:
        logger.warning("⏭️  Skipping Telegram scraper (not configured)")

    if api_status["x_api"]:
        tasks.append(asyncio.create_task(safe_scraper("X", x_scraper.start())))
        logger.info("🚀 X scraper starting...")
    else:
        logger.warning("⏭️  Skipping X scraper (not configured)")

    if len(tasks) <= 1:
        logger.warning("⚠️  No scrapers configured! Use the dashboard to set up API keys.")
        logger.info(f"🌐 Open http://localhost:{config.DASHBOARD_PORT} → Settings → API Configuration")

    if not tasks:
        logger.error("❌ Nothing to run. Dashboard and scrapers both failed to start.")
        return

    # Graceful shutdown handling
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info("🛑 Shutdown signal received...")
        shutdown_event.set()
        for task in tasks:
            task.cancel()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("━" * 50)
    logger.info("✅ Auto News Scraper is running! Press Ctrl+C to stop.")
    logger.info("━" * 50)

    # Wait for all tasks
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("🧹 Cleaning up...")
        cleanup_all_temp()
        await log_activity("info", "Auto News Scraper stopped", "system")
        logger.info("👋 Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
