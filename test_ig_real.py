
import os
import sys
import logging
import requests
import json
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

def test_ig_debug():
    if not ACCOUNT_ID or not ACCESS_TOKEN:
        logger.error("❌ Missing INSTAGRAM_ACCOUNT_ID or INSTAGRAM_ACCESS_TOKEN in .env")
        return

    logger.info(f"🚀 Testing Instagram Connection for Account ID: {ACCOUNT_ID}")

    # 1. Test Limit/Connection
    url = f"{BASE_URL}/{ACCOUNT_ID}"
    params = {
        "fields": "username,name,biography",
        "access_token": ACCESS_TOKEN
    }
    
    try:
        resp = requests.get(url, params=params)
        if resp.status_code == 200:
            data = resp.json()
            logger.info(f"✅ Connected to Instagram: @{data.get('username')} ({data.get('name')})")
        else:
            logger.error(f"❌ Connection Failed: {resp.status_code} - {resp.text}")
            logger.error("Possible causes: Invalid Token, Wrong Account ID, or User Token instead of Page Token.")
            return

    except Exception as e:
        logger.error(f"❌ Network Error: {e}")
        return

    # 2. Test Media Upload (Photo)
    logger.info("📸 Attempting to post a test photo...")
    
    # Use a Wikimedia image (publicly accessible)
    image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b6/Image_created_with_a_mobile_phone.png/640px-Image_created_with_a_mobile_phone.png"
    caption = "Test post from Debug Script 🤖"

    # Step A: Create Container
    container_url = f"{BASE_URL}/{ACCOUNT_ID}/media"
    payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN
    }
    
    resp = requests.post(container_url, data=payload)
    
    if resp.status_code != 200:
        logger.error(f"❌ Container Creation Failed: {resp.status_code} - {resp.text}")
        if "Application does not have permission" in resp.text:
            logger.error("👉 Check if your Token has 'instagram_content_publish' permission.")
        if "The user must be an administrator" in resp.text:
            logger.error("👉 User Token used? You might need a Page Token linked to this IG account.")
        return

    creation_id = resp.json().get("id")
    logger.info(f"✅ Container created: {creation_id}")

    # Step B: Publish
    publish_url = f"{BASE_URL}/{ACCOUNT_ID}/media_publish"
    pub_payload = {
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN
    }
    
    resp = requests.post(publish_url, data=pub_payload)
    
    if resp.status_code == 200:
        logger.info(f"✅ SUCCESS! Post ID: {resp.json().get('id')}")
    else:
        logger.error(f"❌ Publish Failed: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    if not ACCOUNT_ID:
        # allow manual input if env is empty
        ACCOUNT_ID = input("Enter Instagram Account ID: ")
        ACCESS_TOKEN = input("Enter Access Token: ")
    test_ig_debug()
