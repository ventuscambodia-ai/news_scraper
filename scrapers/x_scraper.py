"""
Auto News Scraper - X (Twitter) Scraper
Uses Tweepy to poll recent tweets from specific accounts and hashtags.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import tweepy

import config
from database import is_duplicate, mark_sent, log_activity
from filters.content_filter import should_forward
from media.media_handler import download_x_media
from sender.telegram_sender import send_to_channel
from sender.facebook_sender import send_to_facebook
from sender.instagram_sender import send_to_instagram

logger = logging.getLogger("scraper.x")


class XScraper:
    """Polls X (Twitter) for new tweets from monitored accounts and hashtags."""

    def __init__(self):
        self.client = None
        self.running = False
        self._last_tweet_ids = {}  # Track last seen tweet per account/hashtag

    async def start(self):
        """Initialize and start the X scraper polling loop."""
        bearer_token = config.X_BEARER_TOKEN

        if not bearer_token:
            logger.warning("⚠️  X API credentials not configured. Skipping X scraper.")
            await log_activity("warning", "X API credentials not configured", "x")
            return

        self.client = tweepy.Client(
            bearer_token=bearer_token,
            wait_on_rate_limit=True,
        )

        self.running = True
        logger.info("✅ X (Twitter) client initialized")
        await log_activity("info", "X scraper started", "x")

        # Polling loop
        while self.running:
            try:
                settings = config.load_settings()
                accounts = settings.get("x_accounts", [])
                hashtags = settings.get("x_hashtags", [])

                if not accounts and not hashtags:
                    logger.debug("⚠️  No X accounts or hashtags configured")
                    await asyncio.sleep(config.X_POLL_INTERVAL)
                    continue

                # Poll each account
                for account in accounts:
                    if not self.running:
                        break
                    await self._poll_account(account, settings)
                    await asyncio.sleep(2)  # Small delay between API calls

                # Poll each hashtag
                for hashtag in hashtags:
                    if not self.running:
                        break
                    await self._poll_hashtag(hashtag, settings)
                    await asyncio.sleep(2)

                # Wait before next poll cycle
                await asyncio.sleep(config.X_POLL_INTERVAL)

            except tweepy.TooManyRequests:
                logger.warning("⏳ X API rate limit hit. Waiting 60s...")
                await log_activity("warning", "Rate limit hit, waiting 60s", "x")
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                logger.info("🛑 X scraper stopped")
                break
            except Exception as e:
                logger.error(f"❌ X polling error: {e}", exc_info=True)
                await log_activity("error", f"Polling error: {str(e)}", "x")
                await asyncio.sleep(30)

    async def _poll_account(self, username: str, settings: dict):
        """Poll recent tweets from a specific X account."""
        try:
            # Get user ID from username
            user = self.client.get_user(username=username)
            if not user.data:
                logger.warning(f"⚠️  X user not found: @{username}")
                return

            user_id = user.data.id
            since_id = self._last_tweet_ids.get(f"user_{username}")

            # Get recent tweets
            tweets_response = self.client.get_users_tweets(
                id=user_id,
                max_results=10,
                since_id=since_id,
                tweet_fields=["created_at", "attachments", "entities", "text"],
                expansions=["attachments.media_keys"],
                media_fields=["url", "preview_image_url", "type", "variants"],
                exclude=["retweets", "replies"],
            )

            if not tweets_response.data:
                return

            # Process from oldest to newest
            media_map = {}
            if tweets_response.includes and "media" in tweets_response.includes:
                for media in tweets_response.includes["media"]:
                    media_map[media.media_key] = media

            for tweet in reversed(tweets_response.data):
                await self._process_tweet(tweet, username, media_map, settings)

            # Update since_id to latest
            self._last_tweet_ids[f"user_{username}"] = tweets_response.data[0].id

        except tweepy.TooManyRequests:
            raise  # Let the parent handle rate limits
        except Exception as e:
            logger.error(f"❌ Error polling @{username}: {e}", exc_info=True)

    async def _poll_hashtag(self, hashtag: str, settings: dict):
        """Poll recent tweets with a specific hashtag."""
        try:
            query = f"#{hashtag} -is:retweet -is:reply"
            since_id = self._last_tweet_ids.get(f"tag_{hashtag}")

            tweets_response = self.client.search_recent_tweets(
                query=query,
                max_results=10,
                since_id=since_id,
                tweet_fields=["created_at", "attachments", "entities", "text", "author_id"],
                expansions=["attachments.media_keys", "author_id"],
                media_fields=["url", "preview_image_url", "type", "variants"],
                user_fields=["username"],
            )

            if not tweets_response.data:
                return

            # Build media and user maps
            media_map = {}
            user_map = {}
            if tweets_response.includes:
                if "media" in tweets_response.includes:
                    for media in tweets_response.includes["media"]:
                        media_map[media.media_key] = media
                if "users" in tweets_response.includes:
                    for user in tweets_response.includes["users"]:
                        user_map[user.id] = user.username

            for tweet in reversed(tweets_response.data):
                author = user_map.get(tweet.author_id, "unknown")
                await self._process_tweet(tweet, author, media_map, settings, hashtag=hashtag)

            self._last_tweet_ids[f"tag_{hashtag}"] = tweets_response.data[0].id

        except tweepy.TooManyRequests:
            raise
        except Exception as e:
            logger.error(f"❌ Error polling #{hashtag}: {e}", exc_info=True)

    async def _process_tweet(self, tweet, author: str, media_map: dict,
                             settings: dict, hashtag: str = None):
        """Process a single tweet and forward it."""
        source_id = f"x_{tweet.id}"

        # Check for duplicates
        if await is_duplicate("x", source_id):
            return

        text = tweet.text or ""

        # Apply content filter
        if not should_forward(text, settings):
            logger.debug(f"🚫 Filtered out tweet from @{author}")
            return

        # Build tweet URL
        tweet_url = f"https://x.com/{author}/status/{tweet.id}"

        logger.info(f"🐦 New tweet from @{author}: {text[:80]}...")

        # Download media if present
        media_path = None
        media_type = None

        if hasattr(tweet, "attachments") and tweet.attachments:
            media_keys = tweet.attachments.get("media_keys", [])
            if media_keys and media_keys[0] in media_map:
                media_obj = media_map[media_keys[0]]
                media_path, media_type = await download_x_media(media_obj)

        # Build source label
        source_label = f"@{author}"
        if hashtag:
            source_label = f"@{author} (#{hashtag})"

        # Prepare post data
        post_data = {
            "source": "x",
            "source_id": source_id,
            "channel_name": source_label,
            "text": text,
            "media_path": media_path,
            "media_type": media_type,
            "original_link": tweet_url,
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

        # Mark as sent
        await mark_sent(
            "x", source_id, text,
            title=text[:100],
            telegram=tg_sent, facebook=fb_sent, instagram=ig_sent
        )

        await log_activity(
            "info",
            f"Forwarded from {source_label} → TG:{'✅' if tg_sent else '❌'} FB:{'✅' if fb_sent else '⏭️'} IG:{'✅' if ig_sent else '⏭️'}",
            "x"
        )

    async def stop(self):
        """Stop the X scraper."""
        self.running = False
        logger.info("🛑 X scraper stopped")
