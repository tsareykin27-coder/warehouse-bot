import os
import re
import requests
from flask import Flask, request, jsonify
from config import BOT_TOKEN, get_role, USE_AI
from sheets import update_inventory, get_balance, get_unit, log_transaction, get_status, delete_log_entry, delete_all_logs
from ai_parser import parse_with_ai

DELETE_PIN = "482258"

app = Flask(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# --- Telegram sender ---------------------------------------------------------

def send_message(chat_id: int, text: str):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    resp = requests.post(url, json=payload)
    print(f"[TG] -> {chat_id}: {text[:60]} | status={resp.status_code}")


# --- Unit extractor ----------------------------------------------------------

UNIT_KEYWORDS = [
    "boxes", "box", "kits", "kit", "packs", "pack", "package", "packages",
    "bags", "bag", "bottles", "bottle", "rolls", "roll", "pairs", "pair",
    "sets", "set", "units", "unit", "pcs", "pc", "pieces", "piece",
    "vials", "vial", "ampules", "ampule", "tubes", "tube", "cans", "can",
    "sheets", "sheet", "doses", "dose",
]

def extract_unit(raw_item: str):
    words = raw_item.strip().lower().split()
    if len(words) >= 2 and words[-1] in UNIT_KEYWORDS:
        return " ".join(words[:-1]), words[-1]
    return raw_item.strip().lower(), "pcs"


# --- Rule-based parsers ------------------------------------------------------

def parse_bulk_items(body: str):
    parts = re.split(r'[\n,\.]+', body)
    results = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if len(tokens) < 2:
            raise ValueError(f"bad_line:{part}")
        try:
            qty = int(tokens[0].replace(",", ""))
            if qty <= 0:
                raise ValueError(f"bad_qty:{part}")
        except ValueError:
            raise ValueError(f"bad_line:{part}")
        raw_item = " ".join(tokens[1:]).lower().strip()
        item, unit = extract_unit(raw_item)
        results.append((qty, item, unit))
    if not results:
        raise ValueError("empty")
    return results


def parse_command(body: str):
    body = body.strip()
    if body.startswith("/"):
        body = body[1:]
    tokens = body.split()
    if not tokens:
        raise ValueError("empty")
    command = tokens[0].upper()
    if command == "STATUS":
        item = tokens[1].lower() if len(tokens) > 1 else "all"
        return command, None, item, "", "pcs"
    if command in ("ADD", "TAKE"):
        if len(tokens) < 3:
            raise ValueError("missing_args")
        try:
            qty = int(tokens[1].replace(",", ""))
            if qty <= 0:
                raise ValueError("bad_qty")
        except (ValueError, AttributeError):
            raise ValueError("bad_qty")
        rest = body[len(tokens[0]):].strip()
        rest = rest[len(tokens[1]):].strip()
        quoted = re.match(r'^"([^"]+)"(.*)', rest)
        if quoted:
            raw_item = quoted.group(1).lower().strip()
            note = quoted.group(2).strip()
        else:
            item_tokens = rest.split()
            raw_item = " ".join(item_tokens).lower()
            note = ""
        item, unit = extract_unit(raw_item)
        return command, qty, item, note, unit
    raise ValueError("unknown_command")


def is_bulk(body: str) -> bool:
    return bool(re.match(r'^(ADD|TAKE)\s*:\s*', body.strip(), re.IGNORECASE))


# --- AI execution ------------------------------------------------------------

def execute_ai_result(parsed: dict, user_id: int, role: str) -> str:
    """Executes a Gemini-parsed command dict using the same logic as rule-based path."""
    action = parsed.get("action", "UNKNOWN").upper()

    if action == "UNKNOWN":
        return "I didn't understand that. Use ADD, TAKE, or STATUS."

    if action == "DELETE":
        target = str(parsed.get("target", "")).upper()
        pin = str(parsed.get("pin", ""))
        if role != "manager":
            return "Only the manager can delete logs."
        if pin != DELETE_PIN:
            return "Wrong PIN. Deletion cancelled."
        if target == "ALL":
            return delete_all_logs(user_id)
        try:
            return delete_log_entry(int(target), user_id)
        except ValueError:
            return f"Invalid log number: {target}"

    if action == "STATUS":
        return get_status(parsed.get("item", "all"))

    if action in ("ADD", "BULK_ADD", "TAKE", "BULK_TAKE"):
        is_add = action in ("ADD", "BULK_ADD")
        is_bulk_ai = action in ("BULK_ADD", "BULK_TAKE")
        cmd = "ADD" if is_add else "TAKE"

        if is_add and role != "manager":
            return "Only the manager can add stock."

        if is_bulk_ai:
            items = parsed.get("items", [])
            if not items:
                return "No items found in message."
            lines = []
            for entry in items:
                qty = int(entry.get("qty", 0))
                item = entry.get("item", "").lower().strip()
                unit = entry.get("unit", "pcs")
                if not item or qty <= 0:
                    continue
                if is_add:
                    update_inventory(item, qty, unit)
                    balance = get_balance(item)
                    log_transaction(user_id, role, "ADD", item, qty, balance, "")
                    lines.append(f"  + *{item}* +{qty} {unit} -> stock: {balance} {unit}")
                else:
                    balance = get_balance(item)
                    if balance is None:
                        lines.append(f"  x *{item}* - not found")
                        continue
                    stored_unit = get_unit(item)
                    if balance < qty:
                        lines.append(f"  x *{item}* - only {balance} {stored_unit} available")
                        continue
                    update_inventory(item, -qty)
                    new_bal = get_balance(item)
                    log_transaction(user_id, role, "TAKE", item, qty, new_bal, "")
                    lines.append(f"  - *{item}* -{qty} {stored_unit} -> remaining: {new_bal} {stored_unit}")
            return f"*Bulk {cmd} complete:*\n" + "\n".join(lines)

        else:
            qty = int(parsed.get("qty", 0))
            item = parsed.get("item", "").lower().strip()
            unit = parsed.get("unit", "pcs")
            note = parsed.get("note", "")
            if not item or qty <= 0:
                return "Could not extract item or quantity."
            if is_add:
                update_inventory(item, qty, unit)
                balance = get_balance(item)
                log_transaction(user_id, role, "ADD", item, qty, balance, note)
                return f"Added *{qty} {unit} x {item}*.\nNew stock: *{balance} {unit}*."
            else:
                balance = get_balance(item)
                if balance is None:
                    return f"Item *{item}* not found. Contact manager."
                stored_unit = get_unit(item)
                if balance < qty:
                    return (f"Not enough stock.\nCurrent: *{balance} {stored_unit}*\n"
                            f"Requested: *{qty}*\nShortage: *{qty - balance}*")
                update_inventory(item, -qty)
                new_bal = get_balance(item)
                log_transaction(user_id, role, "TAKE", item, qty, new_bal, note)
                return f"TAKE *{qty} x {item}*.\nRemaining: *{new_bal} {stored_unit}*."

    return "I didn't understand that. Use ADD, TAKE, or STATUS."


# --- Business logic (rule-based) ---------------------------------------------

def handle_bulk(user_id: int, role: str, command: str, items_body: str) -> str:
    try:
        items = parse_bulk_items(items_body)
    except ValueError as e:
        err = str(e)
        if err.startswith("bad_line:"):
            line = err.split(":", 1)[1]
            return f"Could not read this line: `{line}`\nFormat: `50 gloves`"
        if err.startswith("bad_qty:"):
            line = err.split(":", 1)[1]
            return f"Invalid quantity in: `{line}`"
        return "Could not parse items. Use:\n`ADD:\n50 gloves\n13 tubes\n40 masks`"

    if command == "ADD" and role != "manager":
        return "Only the manager can add stock."

    lines = []
    for qty, item, unit in items:
        if command == "ADD":
            update_inventory(item, qty, unit)
            balance = get_balance(item)
            log_transaction(user_id, role, "ADD", item, qty, balance, "")
            lines.append(f"  + *{item}* +{qty} {unit} -> stock: {balance} {unit}")
        elif command == "TAKE":
            balance = get_balance(item)
            if balance is None:
                lines.append(f"  x *{item}* - not found in inventory")
                continue
            stored_unit = get_unit(item)
            if balance < qty:
                lines.append(f"  x *{item}* - only {balance} {stored_unit} available, requested {qty}")
                continue
            update_inventory(item, -qty)
            new_balance = get_balance(item)
            log_transaction(user_id, role, "TAKE", item, qty, new_balance, "")
            lines.append(f"  - *{item}* -{qty} {stored_unit} -> remaining: {new_balance} {stored_unit}")

    header = f"*Bulk {command} complete:*"
    return header + "\n" + "\n".join(lines)


def handle_message(user_id: int, text: str) -> str:
    role = get_role(user_id)
    if not role:
        return (
            "You are not authorized to use this system.\n\n"
            f"Your Telegram ID is: `{user_id}`\n"
            "Send this ID to your manager to get access."
        )

    # --- AI path (when USE_AI=true) ---
    if USE_AI:
        parsed = parse_with_ai(text)
        if parsed is not None:
            return execute_ai_result(parsed, user_id, role)
        # If AI fails, fall through to rule-based parser below
        print("[AI] fallback to rule-based parser")

    # --- DELETE command ---
    delete_match = re.match(
        r'^DELETE\s+(?:LOG\s+)?(?:NUMBER\s+)?(\d+|ALL)\s+(\d+)$',
        text.strip(), re.IGNORECASE
    )
    if delete_match:
        if role != "manager":
            return "Only the manager can delete logs."
        target = delete_match.group(1).upper()
        pin = delete_match.group(2)
        if pin != DELETE_PIN:
            return "Wrong PIN. Deletion cancelled."
        if target == "ALL":
            return delete_all_logs(user_id)
        else:
            return delete_log_entry(int(target), user_id)

    # --- Bulk mode ---
    if is_bulk(text):
        match = re.match(r'^(ADD|TAKE)\s*:\s*(.+)', text.strip(), re.IGNORECASE | re.DOTALL)
        if match:
            command = match.group(1).upper()
            items_body = match.group(2)
            return handle_bulk(user_id, role, command, items_body)

    # --- Single command mode ---
    try:
        command, qty, item, note, unit = parse_command(text)
    except ValueError as e:
        hints = {
            "unknown_command": (
                "Unknown command. Use:\n"
                "  - `ADD [qty] [item]`\n"
                "  - `TAKE [qty] [item]`\n"
                "  - `STATUS [item]` or `STATUS ALL`\n"
                "  - `DELETE LOG 12 [pin]`\n"
                "  - `DELETE ALL [pin]`\n\n"
                "Bulk format:\n"
                "  `ADD:\n  50 gloves\n  13 tubes`"
            ),
            "missing_args": "Usage: `ADD [qty] [item]` or `TAKE [qty] [item]`\nExample: `ADD 50 gloves`",
            "bad_qty":      "Quantity must be a positive number.\nExample: `TAKE 5 gloves`",
            "empty":        "Please send a command: `ADD`, `TAKE`, or `STATUS`.",
        }
        return hints.get(str(e), "Could not parse message. Use ADD, TAKE, or STATUS.")

    if command == "STATUS":
        return get_status(item)

    if command == "ADD":
        if role != "manager":
            return "Only the manager can add stock.\nUse `TAKE` to log what you take."
        update_inventory(item, qty, unit)
        balance = get_balance(item)
        log_transaction(user_id, role, "ADD", item, qty, balance, note)
        return f"Added *{qty} {unit} x {item}*.\nNew stock: *{balance} {unit}*."

    if command == "TAKE":
        balance = get_balance(item)
        if balance is None:
            return f"Item *{item}* not found.\nContact your manager to add it first."
        unit = get_unit(item)
        if balance < qty:
            return (
                f"Not enough stock.\n"
                f"Current: *{balance} {unit}*\n"
                f"Requested: *{qty}*\n"
                f"Shortage: *{qty - balance}*"
            )
        update_inventory(item, -qty)
        new_balance = get_balance(item)
        log_transaction(user_id, role, "TAKE", item, qty, new_balance, note)
        return f"TAKE *{qty} x {item}*.\nRemaining: *{new_balance} {unit}*."


# --- Webhook -----------------------------------------------------------------

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    try:
        message = data.get("message") or data.get("edited_message")
        if message:
            user_id = message["from"]["id"]
            text = message.get("text", "").strip()
            if text:
                print(f"[IN] {user_id}: {text}")
                reply = handle_message(user_id, text)
                send_message(message["chat"]["id"], reply)
    except Exception as e:
        print(f"[ERROR] {e}")
    return __import__('flask').jsonify({"ok": True}), 200


@app.route("/", methods=["GET"])
def health():
    return "Warehouse Bot (Telegram) is running", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
