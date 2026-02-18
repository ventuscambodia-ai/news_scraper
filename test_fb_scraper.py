
import os
import sys
import logging
import requests
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_fb")

# Load environment variables
load_dotenv()

PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
API_VER = "v21.0"

def test_fb_scrape():
    if not PAGE_ACCESS_TOKEN:
        logger.error("❌ Missing FACEBOOK_PAGE_ACCESS_TOKEN in .env")
        return

    # If PAGE_ID is missing, try to fetch it or just ask
    if len(sys.argv) > 1:
        target_page_id = sys.argv[1]
    else:
        target_page_id = PAGE_ID or input("Enter Facebook Page ID to scrape: ")

    logger.info(f"🚀 Testing Facebook Scraper for Page ID: {target_page_id}")

    url = f"https://graph.facebook.com/{API_VER}/{target_page_id}/feed"
    params = {
        "access_token": PAGE_ACCESS_TOKEN,
        "fields": "id,message,created_time,full_picture,attachments{media_type,media,url}",
        "limit": 5,
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        
        if resp.status_code == 200:
            data = resp.json()
            posts = data.get("data", [])
            logger.info(f"✅ Success! Found {len(posts)} posts.")
            
            for post in posts:
                logger.info(f"   - [{post.get('id')}] {post.get('created_time')}: {post.get('message', '')[:50]}...")
                if "attachments" in post:
                    logger.info("     (Has attachments)")
                if "full_picture" in post:
                     logger.info("     (Has full_picture)")
            
            if not posts:
                logger.warning("⚠️  Connection successful but NO posts found. Check if page has public posts or if token has permission.")
                
        else:
            logger.error(f"❌ API Request Failed: {resp.status_code} - {resp.text}")
            logger.error("Make sure your Token has 'pages_read_engagement' or 'pages_read_user_content' permission.")

    except Exception as e:
        logger.error(f"❌ Connection error: {e}")

if __name__ == "__main__":
    test_fb_scrape()
