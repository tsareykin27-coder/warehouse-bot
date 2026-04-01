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
    creds_dict = json.loads(_creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
else:
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)

client = gspread.authorize(creds)
wb = client.open_by_key(SHEET_ID)

inv_sheet = wb.worksheet("Sheet1")
log_sheet = wb.worksheet("Sheet2")

# Colors
GREEN  = {"red": 0.714, "green": 0.843, "blue": 0.659}
RED    = {"red": 0.918, "green": 0.6,   "blue": 0.6}
GREY   = {"red": 0.85,  "green": 0.85,  "blue": 0.85}
WHITE  = {"red": 1.0,   "green": 1.0,   "blue": 1.0}

NUM_LOG_COLS = 9   # A=Log#  B=Timestamp  C=UserID  D=Role  E=Action  F=Item  G=Qty  H=Balance  I=Note


# ─── Color helper ─────────────────────────────────────────────────────────────

def _color_row(sheet, row_index: int, color: dict, num_cols: int = NUM_LOG_COLS):
    wb.batch_update({"requests": [{
        "repeatCell": {
            "range": {
                "sheetId": sheet.id,
                "startRowIndex": row_index - 1,
                "endRowIndex": row_index,
                "startColumnIndex": 0,
                "endColumnIndex": num_cols
            },
            "cell": {"userEnteredFormat": {"backgroundColor": color}},
            "fields": "userEnteredFormat.backgroundColor"
        }
    }]})


# ─── Inventory helpers ────────────────────────────────────────────────────────

def _find_item_row(item: str):
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


# ─── Log helpers ──────────────────────────────────────────────────────────────

def _next_log_number() -> int:
    """Returns the next log number (max existing + 1)."""
    nums = log_sheet.col_values(1)[1:]  # skip header row
    existing = []
    for n in nums:
        try:
            existing.append(int(n))
        except (ValueError, TypeError):
            pass
    return max(existing, default=0) + 1


def log_transaction(user_id: int, role: str, action: str,
                    item: str, qty, balance_after, note: str = ""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_num = _next_log_number()
    log_sheet.append_row([log_num, ts, str(user_id), role, action, item.lower(), qty, balance_after, note])

    row_index = len(log_sheet.col_values(1))
    if action.upper() == "ADD":
        _color_row(log_sheet, row_index, GREEN)
    elif action.upper() == "DELETE":
        _color_row(log_sheet, row_index, GREY)
    else:
        _color_row(log_sheet, row_index, RED)


def get_log_row_by_number(log_num: int):
    """
    Finds the Sheet2 row index (1-based) for a given log number.
    Returns (row_index, row_data) or (None, None).
    """
    all_rows = log_sheet.get_all_values()
    for i, row in enumerate(all_rows):
        if i == 0:
            continue  # skip header
        try:
            if int(row[0]) == log_num:
                return i + 1, row  # i+1 because gspread is 1-based
        except (ValueError, IndexError):
            pass
    return None, None


def delete_log_entry(log_num: int, deleted_by_user_id: int):
    """
    Deletes a single log entry by log number:
    - Reverses its effect on Sheet1 inventory
    - Strikes through / greys out the row in Sheet2
    - Appends a DELETE audit row in Sheet2
    Returns a result message string.
    """
    row_index, row = get_log_row_by_number(log_num)
    if row_index is None:
        return f"❌ Log #{log_num} not found."

    # Parse the row: [log#, timestamp, user_id, role, action, item, qty, balance_after, note]
    try:
        action       = row[4].upper()
        item         = row[5]
        qty          = int(row[6])
        original_note = row[8] if len(row) > 8 else ""
    except (IndexError, ValueError):
        return f"❌ Could not read log #{log_num} — row may be malformed."

    if action == "DELETE":
        return f"❌ Log #{log_num} is already a DELETE entry and cannot be deleted."

    # Reverse inventory effect
    if action == "ADD":
        # Undo an ADD → subtract from inventory
        current = get_balance(item)
        if current is not None:
            update_inventory(item, -qty)
    elif action == "TAKE":
        # Undo a TAKE → add back to inventory
        update_inventory(item, qty)

    # Grey out the deleted row in Sheet2
    _color_row(log_sheet, row_index, GREY)

    # Strike through text by clearing and rewriting with strikethrough format
    wb.batch_update({"requests": [{
        "repeatCell": {
            "range": {
                "sheetId": log_sheet.id,
                "startRowIndex": row_index - 1,
                "endRowIndex": row_index,
                "startColumnIndex": 0,
                "endColumnIndex": NUM_LOG_COLS
            },
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {"strikethrough": True},
                    "backgroundColor": GREY
                }
            },
            "fields": "userEnteredFormat.textFormat.strikethrough,userEnteredFormat.backgroundColor"
        }
    }]})

    # Append a DELETE audit log row
    new_balance = get_balance(item)
    audit_note = f"DELETED log #{log_num} | was: {action} {qty} {item} | orig note: {original_note}"
    log_transaction(deleted_by_user_id, "manager", "DELETE", item, qty, new_balance, audit_note)

    return (
        f"🗑 Log #{log_num} deleted.\n"
        f"  Was: *{action} {qty} × {item}*\n"
        f"  Inventory adjusted accordingly.\n"
        f"  Deletion logged as entry #{_next_log_number() - 1}."
    )


def delete_all_logs(deleted_by_user_id: int):
    """
    Clears all rows in Sheet2 (except header) and resets Sheet1 quantities to 0.
    Appends one DELETE audit entry.
    Returns a result message.
    """
    # Count rows before clearing
    all_rows = log_sheet.get_all_values()
    data_rows = [r for r in all_rows[1:] if any(r)]
    count = len(data_rows)

    if count == 0:
        return "📋 Log is already empty."

    # Reset all inventory quantities to 0 in Sheet1
    inv_rows = inv_sheet.get_all_values()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for i, row in enumerate(inv_rows):
        if i == 0:
            continue
        if row[0]:
            inv_sheet.update_cell(i + 1, 3, 0)
            inv_sheet.update_cell(i + 1, 4, ts)

    # Clear all data rows in Sheet2 (keep header row 1)
    last_row = len(all_rows)
    if last_row > 1:
        wb.batch_update({"requests": [{
            "deleteDimension": {
                "range": {
                    "sheetId": log_sheet.id,
                    "dimension": "ROWS",
                    "startIndex": 1,       # 0-based, so row index 1 = row 2
                    "endIndex": last_row
                }
            }
        }]})

    # Append one audit row
    audit_note = f"ALL LOGS CLEARED ({count} entries deleted) by user {deleted_by_user_id}"
    ts2 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_sheet.append_row([1, ts2, str(deleted_by_user_id), "manager", "DELETE", "ALL", count, 0, audit_note])
    _color_row(log_sheet, 2, GREY)

    return (
        f"🗑 All {count} log entries deleted.\n"
        f"  Sheet1 inventory quantities reset to 0.\n"
        f"  Deletion logged as entry #1."
    )


def get_status(item: str = "all") -> str:
    if item and item.lower() != "all":
        balance = get_balance(item)
        unit = get_unit(item)
        if balance is None:
            return f"❌ Item *{item}* not found in inventory."
        return f"📦 *{item.capitalize()}*: {balance} {unit}"
    else:
        rows = inv_sheet.get_all_values()[1:]
        if not rows:
            return "📦 Inventory is empty."
        lines = ["📦 *Inventory Status:*"]
        for r in rows:
            if r[0]:
                lines.append(f"  • {r[0].capitalize()}: {r[2]} {r[1]}")
        return "\n".join(lines)
