"""
Run this ONCE to fully reset both sheets:
- Clears all data rows from Sheet1 and Sheet2
- Writes correct headers to both sheets

Usage:
    python reset_sheets.py
"""
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

load_dotenv()

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

SHEET_ID = os.getenv("SHEET_ID")

_creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
if _creds_json:
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(_creds_json), SCOPE)
else:
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)

client = gspread.authorize(creds)
wb = client.open_by_key(SHEET_ID)

inv_sheet = wb.worksheet("Sheet1")
log_sheet = wb.worksheet("Sheet2")

# ── Clear Sheet1 completely and write header ──────────────────────────────────
inv_sheet.clear()
inv_sheet.append_row(["Item", "Unit", "Quantity", "Last Updated"])
print("✅ Sheet1 cleared and header written: Item | Unit | Quantity | Last Updated")

# ── Clear Sheet2 completely and write header ──────────────────────────────────
log_sheet.clear()
log_sheet.append_row(["#", "Timestamp", "User ID", "Role", "Action", "Item", "Qty", "Balance After", "Note"])
print("✅ Sheet2 cleared and header written: # | Timestamp | User ID | Role | Action | Item | Qty | Balance After | Note")

print("\n🎉 Both sheets reset. You can now start fresh.")
