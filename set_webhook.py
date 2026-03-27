"""
Run this script ONCE after deploying to Render to register
your Telegram webhook URL.

Usage:
    python set_webhook.py https://your-app.onrender.com
"""
import sys
import requests
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN not set in .env")
    sys.exit(1)

if len(sys.argv) < 2:
    print("Usage: python set_webhook.py https://your-app.onrender.com")
    sys.exit(1)

base_url = sys.argv[1].rstrip("/")
webhook_url = f"{base_url}/webhook"

resp = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
    json={"url": webhook_url}
)
data = resp.json()

if data.get("ok"):
    print(f"✅ Webhook set successfully: {webhook_url}")
else:
    print(f"❌ Failed: {data}")
