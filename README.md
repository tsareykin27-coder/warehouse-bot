# Warehouse Logistics Bot (Telegram)

A Telegram bot that tracks warehouse inventory in real-time, backed by Google Sheets.

## How it works

```
Telegram message → Telegram Bot API webhook → Flask server (Render) → Google Sheets
```

## Roles

| Role | Permissions |
|------|-------------|
| Manager | ADD stock, TAKE stock, STATUS |
| Employee | TAKE stock, STATUS only |
| Anyone else | Bot replies with their Telegram ID so manager can authorize them |

## Commands

```
ADD 50 gloves
ADD 10 oxygen-mask restock from supplier
TAKE 5 gloves
TAKE 2 "oxygen mask" used in field
STATUS gloves
STATUS ALL
```

## Google Sheets structure

**Inventory sheet:** Item | Unit | Quantity | Last Updated
**Log sheet:** Timestamp | User ID | Role | Action | Item | Quantity | Balance After | Note

## Setup

1. Create bot via @BotFather on Telegram → get BOT_TOKEN
2. Set up Google Sheets + Service Account → get credentials.json + SHEET_ID
3. Deploy to Render (see below)
4. Set environment variables on Render
5. Run `python set_webhook.py https://your-app.onrender.com`

## Local development

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in .env — place credentials.json in project root for local auth
python main.py
```
