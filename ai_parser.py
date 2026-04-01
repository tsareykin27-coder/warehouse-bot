"""
Gemini-powered natural language parser.
Called only when USE_AI=true in environment.

Converts free-form messages like:
  "just got 3 boxes of gloves and 10 bandage rolls"
  "took 2 oxygen masks for the shift"
  "how many gloves do we have left?"
into structured commands the bot can execute.
"""

import os
import json
import requests

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_BASE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash-lite:generateContent"
)

SYSTEM_PROMPT = """
You are a warehouse inventory assistant. Parse the user's message and return a JSON object.

The warehouse bot supports these actions:
- ADD: manager adds stock
- TAKE: employee/manager removes stock from warehouse
- STATUS: check current stock levels
- UNKNOWN: message is not inventory-related

Return ONLY a valid JSON object, no explanation, no markdown, no code block. Examples:

User: "just brought in 50 gloves and 20 bandage rolls"
{"action":"BULK_ADD","items":[{"qty":50,"item":"gloves","unit":"pcs"},{"qty":20,"item":"bandage","unit":"rolls"}]}

User: "took 5 glove boxes for team B"
{"action":"BULK_TAKE","items":[{"qty":5,"item":"glove","unit":"boxes"}]}

User: "ADD 30 masks"
{"action":"ADD","qty":30,"item":"masks","unit":"pcs","note":""}

User: "how many gloves left?"
{"action":"STATUS","item":"gloves"}

User: "check all stock"
{"action":"STATUS","item":"all"}

User: "hello"
{"action":"UNKNOWN"}

User: "delete log 5 482258"
{"action":"DELETE","target":"5","pin":"482258"}

User: "delete all logs 482258"
{"action":"DELETE","target":"ALL","pin":"482258"}

Rules:
- For multiple items in one message → use BULK_ADD or BULK_TAKE
- For a single item → use ADD or TAKE
- Always extract the unit if mentioned (box, kit, pack, bag, roll, pcs, etc.)
- If no unit is mentioned, use "pcs"
- Keep item names lowercase and concise
- Never include the unit word in the item name
- If the message is ambiguous between ADD and TAKE, assume TAKE
"""


def parse_with_ai(user_message: str) -> dict | None:
    """
    Sends user_message to Gemini and returns parsed dict.
    Returns None if AI call fails (caller will fall back to rule-based parser).
    """
    if not GEMINI_API_KEY:
        return None

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": SYSTEM_PROMPT + f'\n\nUser: "{user_message}"\nJSON:'}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 300
        }
    }

    try:
        url = f"{GEMINI_BASE_URL}?key={GEMINI_API_KEY}"
        resp = requests.post(url, json=payload, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Strip markdown code fences if Gemini wraps in ```json ... ```
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        parsed = json.loads(text)
        print(f"[AI] parsed: {parsed}")
        return parsed

    except requests.exceptions.HTTPError as e:
        # Scrub the API key from the error message before logging
        safe_error = str(e)
        if GEMINI_API_KEY:
            safe_error = safe_error.replace(GEMINI_API_KEY, "***")
        # Print the full response body so we can see the exact quota error
        try:
            body = e.response.json()
            body_str = json.dumps(body)
            if GEMINI_API_KEY:
                body_str = body_str.replace(GEMINI_API_KEY, "***")
            print(f"[AI] failed: {safe_error} | body: {body_str}")
        except Exception:
            print(f"[AI] failed: {safe_error}")
        return None
    except Exception as e:
        safe_error = str(e)
        if GEMINI_API_KEY:
            safe_error = safe_error.replace(GEMINI_API_KEY, "***")
        print(f"[AI] failed: {safe_error}")
        return None
