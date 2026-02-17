"""
Auto News Scraper - Database Module
SQLite-based deduplication and history tracking.
"""

import aiosqlite
import hashlib
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "news_scraper.db"


async def init_db():
    """Initialize the database and create tables."""
    DB_PATH.parent.mkdir(exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sent_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                title TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_to_telegram BOOLEAN DEFAULT 0,
                sent_to_facebook BOOLEAN DEFAULT 0,
                UNIQUE(source, source_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                level TEXT NOT NULL,
                source TEXT,
                message TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_sent_posts_source 
            ON sent_posts(source, source_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_log_timestamp 
            ON activity_log(timestamp DESC)
        """)
        await db.commit()


def _content_hash(text: str) -> str:
    """Generate a hash for content deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


async def is_duplicate(source: str, source_id: str) -> bool:
    """Check if a post has already been sent."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            "SELECT 1 FROM sent_posts WHERE source = ? AND source_id = ?",
            (source, source_id)
        )
        row = await cursor.fetchone()
        return row is not None


async def mark_sent(source: str, source_id: str, content: str,
                    title: str = None, telegram: bool = False, facebook: bool = False):
    """Record a post as sent."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """INSERT OR REPLACE INTO sent_posts 
               (source, source_id, content_hash, title, sent_to_telegram, sent_to_facebook)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (source, source_id, _content_hash(content), title, telegram, facebook)
        )
        await db.commit()


async def log_activity(level: str, message: str, source: str = None):
    """Log an activity to the database for dashboard display."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO activity_log (level, source, message) VALUES (?, ?, ?)",
            (level, source, message)
        )
        await db.commit()


async def get_recent_posts(limit: int = 50) -> list:
    """Get recently sent posts for dashboard display."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM sent_posts ORDER BY sent_at DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_activity_log(limit: int = 100) -> list:
    """Get recent activity log entries."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_stats() -> dict:
    """Get statistics for the dashboard."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        # Total posts
        cursor = await db.execute("SELECT COUNT(*) FROM sent_posts")
        total = (await cursor.fetchone())[0]

        # Posts today
        cursor = await db.execute(
            "SELECT COUNT(*) FROM sent_posts WHERE DATE(sent_at) = DATE('now')"
        )
        today = (await cursor.fetchone())[0]

        # By source
        cursor = await db.execute(
            "SELECT source, COUNT(*) as count FROM sent_posts GROUP BY source"
        )
        by_source = {row[0]: row[1] for row in await cursor.fetchall()}

        return {
            "total_posts": total,
            "posts_today": today,
            "by_source": by_source,
        }
