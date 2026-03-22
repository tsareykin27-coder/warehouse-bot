import os
from dotenv import load_dotenv

load_dotenv()

# ─── WhatsApp ────────────────────────────────────────────────────────────────
WHATSAPP_TOKEN   = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID  = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN     = os.getenv("VERIFY_TOKEN")

# ─── Google Sheets ───────────────────────────────────────────────────────────
SHEET_ID         = os.getenv("SHEET_ID")

# ─── Authorized numbers (E.164 without the +) ───────────────────────────────
# Example: MANAGER_NUMBERS=972501234567
# Multiple employees: EMPLOYEE_NUMBERS=972501234568,972501234569
MANAGER_NUMBERS  = set(filter(None, os.getenv("MANAGER_NUMBERS", "").split(",")))
EMPLOYEE_NUMBERS = set(filter(None, os.getenv("EMPLOYEE_NUMBERS", "").split(",")))


def get_role(phone: str):
    """Returns 'manager', 'employee', or None for unauthorized numbers."""
    if phone in MANAGER_NUMBERS:
        return "manager"
    if phone in EMPLOYEE_NUMBERS:
        return "employee"
    return None
