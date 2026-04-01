import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from config import SHEET_ID

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

_creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")

if _creds_json:
    # Running on Render — credentials stored as env var
    creds_dict = json.loads(_creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
else:
    # Running locally — credentials.json file in project root
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)

client = gspread.authorize(creds)
wb = client.open_by_key(SHEET_ID)

inv_sheet = wb.worksheet("Sheet1")
log_sheet = wb.worksheet("Sheet2")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _find_item_row(item: str):
    """Returns 1-based row index of item in Inventory sheet, or None."""
    items = inv_sheet.col_values(1)
    for i, val in enumerate(items):
        if val.strip().lower() == item.strip().lower():
            return i + 1
    return None


def get_balance(item: str):
    row = _find_item_row(item)
    if row is None:
        return None
    val = inv_sheet.cell(row, 3).value
    return int(val) if val else 0


def get_unit(item: str) -> str:
    row = _find_item_row(item)
    if row is None:
        return "pcs"
    val = inv_sheet.cell(row, 2).value
    return val if val else "pcs"


def update_inventory(item: str, delta: int, unit: str = "pcs"):
    row = _find_item_row(item)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if row is None:
        inv_sheet.append_row([item.lower(), unit, delta, ts])
    else:
        current = int(inv_sheet.cell(row, 3).value or 0)
        inv_sheet.update_cell(row, 3, current + delta)
        inv_sheet.update_cell(row, 4, ts)


def log_transaction(user_id: int, role: str, action: str,
                    item: str, qty: int, balance_after: int, note: str = ""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_sheet.append_row([ts, str(user_id), role, action, item.lower(), qty, balance_after, note])

    # Color the row: green for ADD, red for TAKE
    row_index = len(log_sheet.col_values(1))  # last filled row
    if action.upper() == "ADD":
        bg_color = {"red": 0.714, "green": 0.843, "blue": 0.659}   # soft green
    else:
        bg_color = {"red": 0.918, "green": 0.6,   "blue": 0.6}     # soft red

    num_cols = 8
    requests_body = [
        {
            "repeatCell": {
                "range": {
                    "sheetId": log_sheet.id,
                    "startRowIndex": row_index - 1,
                    "endRowIndex": row_index,
                    "startColumnIndex": 0,
                    "endColumnIndex": num_cols
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": bg_color
                    }
                },
                "fields": "userEnteredFormat.backgroundColor"
            }
        }
    ]
    wb.batch_update({"requests": requests_body})


def get_status(item: str = "all") -> str:
    if item and item.lower() != "all":
        balance = get_balance(item)
        unit = get_unit(item)
        if balance is None:
            return f"❌ Item *{item}* not found in inventory."
        return f"📦 *{item.capitalize()}*: {balance} {unit}"
    else:
        rows = inv_sheet.get_all_values()[1:]  # skip header
        if not rows:
            return "📦 Inventory is empty."
        lines = ["📦 *Inventory Status:*"]
        for r in rows:
            if r[0]:
                lines.append(f"  • {r[0].capitalize()}: {r[2]} {r[1]}")
        return "\n".join(lines)
