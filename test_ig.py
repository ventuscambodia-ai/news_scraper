
import os
import sys
import logging
import requests
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_ig")

# Load environment variables
load_dotenv()

ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
API_VER = "v21.0"
BASE_URL = f"https://graph.facebook.com/{API_VER}"

def test_config():
    if not ACCOUNT_ID or not ACCESS_TOKEN:
        logger.error("❌ Missing INSTAGRAM_ACCOUNT_ID or INSTAGRAM_ACCESS_TOKEN in .env")
        return False
    logger.info(f"✅ Config found: Account ID {ACCOUNT_ID}")
    return True

def test_connection():
    """Check if we can access the account details."""
    url = f"{BASE_URL}/{ACCOUNT_ID}"
    params = {
        "fields": "username,name",
        "access_token": ACCESS_TOKEN
    }
    resp = requests.get(url, params=params)
    if resp.status_code == 200:
        data = resp.json()
        logger.info(f"✅ Connection successful: Connected to @{data.get('username')} ({data.get('name')})")
        return True
    else:
        logger.error(f"❌ Connection failed: {resp.status_code} - {resp.text}")
        return False

def test_post_photo():
    """Try to post a sample photo."""
    image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Cat03.jpg/800px-Cat03.jpg"
    caption = "Test post from Auto News Scraper v2.0 - Debug Mode 🤖📸"

    logger.info("🚀 Attempting to post a sample photo...")

    # Step 1: Create Container
    container_url = f"{BASE_URL}/{ACCOUNT_ID}/media"
    data = {
        "image_url": image_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN
    }
    
    logger.info("   Creating media container...")
    resp = requests.post(container_url, data=data)
    
    if resp.status_code != 200:
        logger.error(f"❌ Container creation failed: {resp.status_code} - {resp.text}")
        return False
    
    container_id = resp.json().get("id")
    logger.info(f"   Container created: {container_id}")

    # Step 2: Publish
    publish_url = f"{BASE_URL}/{ACCOUNT_ID}/media_publish"
    pub_data = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }

    logger.info("   Publishing container...")
    resp = requests.post(publish_url, data=pub_data)

    if resp.status_code == 200:
        post_id = resp.json().get("id")
        logger.info(f"✅ Post successful! ID: {post_id}")
        return True
    else:
        logger.error(f"❌ Publish failed: {resp.status_code} - {resp.text}")
        return False

if __name__ == "__main__":
    if test_config():
        if test_connection():
            test_post_photo()
