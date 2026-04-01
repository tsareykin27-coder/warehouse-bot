import os
import re
import requests
from flask import Flask, request, jsonify
from config import BOT_TOKEN, get_role
from sheets import update_inventory, get_balance, get_unit, log_transaction, get_status

app = Flask(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ─── Telegram sender ──────────────────────────────────────────────────────────

def send_message(chat_id: int, text: str):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    resp = requests.post(url, json=payload)
    print(f"[TG] → {chat_id}: {text[:60]} | status={resp.status_code}")


# ─── Unit extractor ─────────────────────────────────────────────────────────

# Known unit keywords (singular and plural)
UNIT_KEYWORDS = [
    "boxes", "box",
    "kits", "kit",
    "packs", "pack", "package", "packages",
    "bags", "bag",
    "bottles", "bottle",
    "rolls", "roll",
    "pairs", "pair",
    "sets", "set",
    "units", "unit",
    "pcs", "pc",
    "pieces", "piece",
    "vials", "vial",
    "ampules", "ampule",
    "tubes", "tube",
    "cans", "can",
    "sheets", "sheet",
    "doses", "dose",
]

def extract_unit(raw_item: str):
    """
    Given a raw item string like 'glove boxes' or 'chest tube kits',
    returns (item, unit).
    If the last word is a known unit keyword, splits it off.
    Otherwise returns (raw_item, 'pcs').

    Examples:
      'glove boxes'     → ('gloves', 'boxes')
      'chest tube kits' → ('chest tube', 'kits')
      'gloves'          → ('gloves', 'pcs')
    """
    words = raw_item.strip().lower().split()
    if len(words) >= 2 and words[-1] in UNIT_KEYWORDS:
        unit = words[-1]
        item = " ".join(words[:-1])
        return item, unit
    return raw_item.strip().lower(), "pcs"


# ─── Parsers ──────────────────────────────────────────────────────────────────

def parse_bulk_items(body: str):
    """
    Parses bulk format after the command keyword.
    Supports:
      - Newline separated:  "50 gloves\n13 tubes\n40 masks"
      - Comma separated:    "50 gloves, 13 tubes, 40 masks"
      - Mixed punctuation:  "50 gloves, 13 tubes. 40 masks"

    Returns list of (qty, item) tuples.
    Raises ValueError if any line is unparseable.
    """
    # Split on newlines or commas or periods
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
    """
    Returns (command, qty, item, note) for single-item commands.
    Raises ValueError with a code on bad input.
    Supports quoted item names: TAKE 5 "first aid kit"
    """
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

    raise ValueError("unknown_command")  # parse_command ends here


def is_bulk(body: str) -> bool:
    """
    Detects bulk format:
      ADD:          (followed by newline or comma-separated items)
      TAKE:
    """
    return bool(re.match(r'^(ADD|TAKE)\s*:\s*', body.strip(), re.IGNORECASE))


# ─── Business logic ───────────────────────────────────────────────────────────

def handle_bulk(user_id: int, role: str, command: str, items_body: str) -> str:
    """Processes a bulk ADD or TAKE and returns a summary reply."""
    try:
        items = parse_bulk_items(items_body)
    except ValueError as e:
        err = str(e)
        if err.startswith("bad_line:"):
            line = err.split(":", 1)[1]
            return f"❓ Could not read this line: `{line}`\nFormat: `50 gloves` (number then item name)"
        if err.startswith("bad_qty:"):
            line = err.split(":", 1)[1]
            return f"❓ Invalid quantity in: `{line}`"
        return "❓ Could not parse items. Use:\n`ADD:\n50 gloves\n13 tubes\n40 masks`"

    if command == "ADD" and role != "manager":
        return "⛔ Only the manager can add stock."

    lines = []
    for qty, item, unit in items:
        if command == "ADD":
            update_inventory(item, qty, unit)
            balance = get_balance(item)
            log_transaction(user_id, role, "ADD", item, qty, balance, "")
            lines.append(f"  ✅ *{item}* +{qty} {unit} → stock: {balance} {unit}")

        elif command == "TAKE":
            balance = get_balance(item)
            if balance is None:
                lines.append(f"  ❌ *{item}* — not found in inventory")
                continue
            stored_unit = get_unit(item)
            if balance < qty:
                lines.append(f"  ❌ *{item}* — only {balance} {stored_unit} available, requested {qty}")
                continue
            update_inventory(item, -qty)
            new_balance = get_balance(item)
            log_transaction(user_id, role, "TAKE", item, qty, new_balance, "")
            lines.append(f"  ✅ *{item}* -{qty} {stored_unit} → remaining: {new_balance} {stored_unit}")

    header = "📦 *Bulk ADD complete:*" if command == "ADD" else "📦 *Bulk TAKE complete:*"
    return header + "\n" + "\n".join(lines)


def handle_message(user_id: int, text: str) -> str:
    role = get_role(user_id)
    if not role:
        return (
            "⛔ You are not authorized to use this system.\n\n"
            f"Your Telegram ID is: `{user_id}`\n"
            "Send this ID to your manager to get access."
        )

    # ── Bulk mode: ADD: or TAKE: followed by items ──
    if is_bulk(text):
        match = re.match(r'^(ADD|TAKE)\s*:\s*(.+)', text.strip(), re.IGNORECASE | re.DOTALL)
        if match:
            command = match.group(1).upper()
            items_body = match.group(2)
            return handle_bulk(user_id, role, command, items_body)

    # ── Single command mode ──
    try:
        command, qty, item, note, unit = parse_command(text)
    except ValueError as e:
        hints = {
            "unknown_command": (
                "❓ Unknown command. Use:\n"
                "  • `ADD [qty] [item]`\n"
                "  • `TAKE [qty] [item]`\n"
                "  • `STATUS [item]`  or  `STATUS ALL`\n\n"
                "Bulk format:\n"
                "  `ADD:\n  50 gloves\n  13 tubes\n  40 masks`"
            ),
            "missing_args": "❓ Usage: `ADD [qty] [item]`  or  `TAKE [qty] [item]`\nExample: `ADD 50 gloves`",
            "bad_qty":      "❓ Quantity must be a positive number.\nExample: `TAKE 5 gloves`",
            "empty":        "❓ Please send a command: `ADD`, `TAKE`, or `STATUS`.",
        }
        return hints.get(str(e), "❓ Could not parse message. Use ADD, TAKE, or STATUS.")

    # ── STATUS ──
    if command == "STATUS":
        return get_status(item)

    # ── ADD ──
    if command == "ADD":
        if role != "manager":
            return "⛔ Only the manager can add stock.\nUse `TAKE` to log what you take from the warehouse."
        update_inventory(item, qty, unit)
        balance = get_balance(item)
        log_transaction(user_id, role, "ADD", item, qty, balance, note)
        return f"✅ Added *{qty} {unit} × {item}*.\nNew stock: *{balance} {unit}*."

    # ── TAKE ──
    if command == "TAKE":
        balance = get_balance(item)
        if balance is None:
            return f"❌ Item *{item}* not found in inventory.\nContact your manager to add it first."
        unit = get_unit(item)
        if balance < qty:
            return (
                f"❌ Not enough stock.\n"
                f"Current: *{balance} {unit}*\n"
                f"Requested: *{qty}*\n"
                f"Shortage: *{qty - balance}*"
            )
        update_inventory(item, -qty)
        new_balance = get_balance(item)
        log_transaction(user_id, role, "TAKE", item, qty, new_balance, note)
        return f"✅ Logged: TAKE *{qty} × {item}*.\nRemaining stock: *{new_balance} {unit}*."


# ─── Webhook ──────────────────────────────────────────────────────────────────

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
    return jsonify({"ok": True}), 200


@app.route("/", methods=["GET"])
def health():
    return "Warehouse Bot (Telegram) is running ✅", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
