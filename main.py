from flask import Flask, request, jsonify
import requests
from config import WHATSAPP_TOKEN, PHONE_NUMBER_ID, VERIFY_TOKEN, get_role
from sheets import update_inventory, get_balance, get_unit, log_transaction, get_status

app = Flask(__name__)


# ─── WhatsApp sender ────────────────────────────────────────────────────────

def send_whatsapp(to: str, message: str):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    resp = requests.post(url, headers=headers, json=payload)
    print(f"[WA] → {to}: {message[:60]}... | status={resp.status_code}")


# ─── Message parser ──────────────────────────────────────────────────────────

def parse_command(body: str):
    """
    Returns (command, qty, item, note)
    Raises ValueError with a descriptive code on bad input.
    Supports quoted item names: TAKE 5 "first aid kit"
    """
    import re
    body = body.strip()
    tokens = body.split()
    if not tokens:
        raise ValueError("empty")

    command = tokens[0].upper()

    if command == "STATUS":
        item = tokens[1].lower() if len(tokens) > 1 else "all"
        return command, None, item, ""

    if command in ("ADD", "TAKE"):
        if len(tokens) < 3:
            raise ValueError("missing_args")

        try:
            qty = int(tokens[1].replace(",", ""))
            if qty <= 0:
                raise ValueError("bad_qty")
        except (ValueError, AttributeError):
            raise ValueError("bad_qty")

        # Support quoted item names: ADD 10 "oxygen mask"
        rest = body[len(tokens[0]):].strip()          # everything after ADD/TAKE
        rest = rest[len(tokens[1]):].strip()           # everything after qty

        quoted = re.match(r'^"([^"]+)"(.*)', rest)
        if quoted:
            item = quoted.group(1).lower().strip()
            note = quoted.group(2).strip()
        else:
            item_tokens = rest.split()
            item = item_tokens[0].lower()
            note = " ".join(item_tokens[1:])

        return command, qty, item, note

    raise ValueError("unknown_command")


# ─── Business logic ──────────────────────────────────────────────────────────

def handle_message(from_number: str, body: str) -> str:
    role = get_role(from_number)
    if not role:
        return "⛔ You are not authorized to use this system."

    try:
        command, qty, item, note = parse_command(body)
    except ValueError as e:
        err = str(e)
        hints = {
            "unknown_command": (
                "❓ Unknown command. Use:\n"
                "  • ADD [qty] [item]\n"
                "  • TAKE [qty] [item]\n"
                "  • STATUS [item]  or  STATUS ALL"
            ),
            "missing_args": "❓ Usage: ADD [qty] [item]  or  TAKE [qty] [item]\nExample: ADD 50 gloves",
            "bad_qty": "❓ Quantity must be a positive number.\nExample: TAKE 5 gloves",
            "empty": "❓ Please send a command. Use ADD, TAKE, or STATUS.",
        }
        return hints.get(err, "❓ Could not parse message. Use ADD, TAKE, or STATUS.")

    # ── STATUS ──
    if command == "STATUS":
        return get_status(item)

    # ── ADD ──
    if command == "ADD":
        if role != "manager":
            return "⛔ Only the manager can add stock.\nUse TAKE to log what you take from the warehouse."
        update_inventory(item, qty)
        balance = get_balance(item)
        unit = get_unit(item)
        log_transaction(from_number, role, "ADD", item, qty, balance, note)
        return f"✅ Added {qty} × {item}.\nNew stock: {balance} {unit}."

    # ── TAKE ──
    if command == "TAKE":
        balance = get_balance(item)
        if balance is None:
            return f"❌ Item '{item}' not found in inventory.\nContact your manager to add it first."
        unit = get_unit(item)
        if balance < qty:
            return (
                f"❌ Not enough stock.\n"
                f"Current: {balance} {unit}\n"
                f"Requested: {qty}\n"
                f"Shortage: {qty - balance}"
            )
        update_inventory(item, -qty)
        new_balance = get_balance(item)
        log_transaction(from_number, role, "TAKE", item, qty, new_balance, note)
        return f"✅ Logged: TAKE {qty} × {item}.\nRemaining stock: {new_balance} {unit}."


# ─── Webhook routes ──────────────────────────────────────────────────────────

@app.route("/webhook", methods=["GET"])
def verify():
    """Meta webhook verification handshake."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("[Webhook] Verified successfully.")
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive incoming WhatsApp messages."""
    data = request.get_json(silent=True) or {}
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                messages = change.get("value", {}).get("messages", [])
                for msg in messages:
                    if msg.get("type") == "text":
                        from_number = msg["from"]
                        body = msg["text"]["body"]
                        print(f"[IN] {from_number}: {body}")
                        reply = handle_message(from_number, body)
                        send_whatsapp(from_number, reply)
    except Exception as e:
        print(f"[ERROR] {e}")
    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def health():
    return "Warehouse Bot is running ✅", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
