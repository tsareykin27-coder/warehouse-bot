"""
Run this ONCE to color all existing rows in Sheet2 (Log).
Green = ADD, Red = TAKE.

Usage:
    python color_existing_rows.py
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
log_sheet = wb.worksheet("Sheet2")

GREEN = {"red": 0.714, "green": 0.843, "blue": 0.659}
RED   = {"red": 0.918, "green": 0.6,   "blue": 0.6}

rows = log_sheet.get_all_values()

requests_body = []
for i, row in enumerate(rows):
    if i == 0:
        continue  # skip header row
    if len(row) < 4:
        continue  # skip empty/incomplete rows

    action = row[3].strip().upper()  # column D = Action
    if action == "ADD":
        bg_color = GREEN
    elif action == "TAKE":
        bg_color = RED
    else:
        continue  # skip rows with unknown action

    requests_body.append({
        "repeatCell": {
            "range": {
                "sheetId": log_sheet.id,
                "startRowIndex": i,
                "endRowIndex": i + 1,
                "startColumnIndex": 0,
                "endColumnIndex": 8
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": bg_color
                }
            },
            "fields": "userEnteredFormat.backgroundColor"
        }
    })

if not requests_body:
    print("No rows to color.")
else:
    wb.batch_update({"requests": requests_body})
    print(f"✅ Colored {len(requests_body)} rows.")
