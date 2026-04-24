# MikoxYae Telegram Bots

A collection of Telegram bots, all written in **Python** with **Pyrogram** and backed by **MongoDB**.

## Bots in this repo

### 1. `forward/` — Forward Bot

A Telegram bot that clones / forwards media from one channel to another — including channels with restricted (no-forward) content — by downloading and re-uploading via a logged-in user session.

**Entry:** `python3 miko.py`

Features:

- Forward media between channels (same-to-same)
- Bypass restricted / protected channels via download → re-upload
- Anyone can log in with their own Telegram account (inline Login button or `/login`)
- Per-user source & destination settings
- All forwarded captions auto-bolded with `<b>...</b>` HTML tags
- MongoDB-backed storage for users, sessions, and settings

See `forward/README.md` for the full command list and login flow.

### 2. `auto-accept/` — Auto Accept Request Bot

A Telegram bot that automatically accepts join requests for channels and groups where "Approve New Members" is enabled.

**Entry:** `python3 main.py`

Features:

- Auto-approves every join request the bot receives
- Optional welcome PM with placeholders (`{mention}`, `{first_name}`, `{username}`, `{chat_title}`, `{chat_link}`, `{user_id}`)
- Per-chat custom welcome message + on/off toggle (chat admins)
- Owner-only `/stats`, `/chats`, `/broadcast`
- FloodWait-safe + dead-user cleanup on broadcast

Commands:

| Command | Who | Description |
| --- | --- | --- |
| `/start`, `/help` | Anyone | Bot intro + buttons |
| `/setwelcome <text>` | Chat admin | Set custom welcome message |
| `/clearwelcome` | Chat admin | Reset welcome to default |
| `/togglewelcome` | Chat admin | Turn welcome PM on / off |
| `/welcome` | Anyone | Show current welcome template |
| `/stats` | Owner | Total users, chats, accepted requests |
| `/chats` | Owner | Per-chat acceptance counts |
| `/broadcast` | Owner | Reply to a message to broadcast to all users |

## Setup (per bot)

Each bot is independent and has its own `requirements.txt`.

```bash
cd <bot-folder>
pip install -r requirements.txt
python3 <entry-file>.py
```

## Environment variables (per bot)

Both bots read configuration from environment variables (see each `config.py`):

| Var | Purpose |
| --- | --- |
| `BOT_TOKEN` | from [@BotFather](https://t.me/BotFather) |
| `APP_ID`, `API_HASH` | from [my.telegram.org](https://my.telegram.org) |
| `MONGO_URI` | your MongoDB connection string |
| `DATABASE_NAME` | DB name — use a **different one per bot** (e.g. `Forward` and `AutoAccept`) |
| `OWNER` | your Telegram username (without `@`) |
| `OWNER_ID` | your numeric Telegram user ID |
| `START_PIC` | optional — image URL shown on `/start` |
| `ACCEPT_DELAY` | (auto-accept only) seconds to wait before approving each request — default `0` |

**Never commit real credentials.** Use a `.env` file or your hosting provider's secret manager.
