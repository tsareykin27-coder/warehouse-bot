# Warehouse Logistics Bot

A WhatsApp bot that tracks warehouse inventory in real-time using Google Sheets as the backend.

## How it works

```
WhatsApp message → Meta Business API webhook → Flask server → Google Sheets
```

## Roles

| Role | Permissions |
|------|-------------|
| Manager | ADD stock, TAKE stock, STATUS |
| Employee | TAKE stock, STATUS only |

## Commands

```
ADD 50 gloves                     ← manager adds stock
ADD 10 oxygen-mask restock note   ← with optional note
TAKE 5 gloves                     ← log withdrawal
TAKE 2 "oxygen mask" field call   ← quoted item name
STATUS gloves                     ← check one item
STATUS ALL                        ← full inventory
```

## Google Sheets structure

**Inventory sheet:** Item | Unit | Quantity | Last Updated  
**Log sheet:** Timestamp | Phone | Role | Action | Item | Quantity | Balance After | Note

## Setup

See full setup guide in the skill file or follow `DEPLOY.md`.

## Local development

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in .env with your values + place credentials.json in root
python main.py
```

## Deploy on Render

See Render configuration section in setup guide.
