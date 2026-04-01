import os
from dotenv import load_dotenv

load_dotenv()

# --- Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Google Sheets ---
SHEET_ID = os.getenv("SHEET_ID")

# --- Email (for EXPORT command) ---
GMAIL_SENDER      = os.getenv("GMAIL_SENDER", "")   # shown as sender address
SENDGRID_API_KEY  = os.getenv("SENDGRID_API_KEY", "")  # sendgrid.com free tier

# --- Authorized Telegram user IDs (numeric) ---
# How to find a user's ID: message the bot — if unauthorized,
# the bot replies with that user's Telegram ID. Add it here.
#
# Example:
#   MANAGER_IDS=123456789
#   EMPLOYEE_IDS=987654321,111222333,444555666

MANAGER_IDS  = set(int(x) for x in os.getenv("MANAGER_IDS",  "").split(",") if x.strip())
EMPLOYEE_IDS = set(int(x) for x in os.getenv("EMPLOYEE_IDS", "").split(",") if x.strip())


def get_role(user_id: int):
    """Returns 'manager', 'employee', or None for unauthorized users."""
    if user_id in MANAGER_IDS:
        return "manager"
    if user_id in EMPLOYEE_IDS:
        return "employee"
    return None
