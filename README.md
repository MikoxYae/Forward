# Forward Bot

A Telegram bot that clones / forwards media from one channel to another — including channels with **restricted (no-forward) content**, by downloading and re-uploading the media using a logged-in user session.

## Features

- Forward media between channels (same-to-same)
- Bypass restricted/protected channels by download → re-upload
- Anyone can login with their own Telegram account (`/login`)
- Owner-only settings (`/settings`) for source & destination channels
- MongoDB-backed storage for users, sessions, and settings

## Project Structure

```
.
├── miko.py              # Entry point: `python3 miko.py`
├── config.py            # Environment configuration
├── requirements.txt
├── database/
│   └── db.py            # MongoDB (motor) wrapper
└── plugins/
    ├── start.py         # /start, /help
    ├── logins.py        # /login, /logout, /cancel (anyone)
    └── settings.py      # /settings, /setsource, /setdest (owner only)
```

## Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) and get the `BOT_TOKEN`.
2. Get `APP_ID` and `API_HASH` from <https://my.telegram.org>.
3. Set the environment variables (or edit `config.py` defaults):

   ```
   BOT_TOKEN=...
   APP_ID=...
   API_HASH=...
   OWNER=your_telegram_username
   OWNER_ID=your_numeric_id
   MONGO_URI=mongodb+srv://...
   DATABASE_NAME=Forward
   ```

4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. Run the bot:

   ```bash
   python3 miko.py
   ```

## Commands

| Command | Who | Description |
| --- | --- | --- |
| `/start`, `/help` | Anyone | Show help |
| `/login` | Anyone | Login with your Telegram account |
| `/logout` | Anyone | Remove your saved session |
| `/cancel` | Anyone | Cancel current login flow |
| `/settings` | Owner | Open settings panel |
| `/setsource <id>` | Owner | Set source channel |
| `/setdest <id>` | Owner | Set destination channel |
| `/clearsettings` | Owner | Clear settings |

## Login Flow

1. `/login`
2. Send phone number with country code (e.g. `+919876543210`)
3. Telegram sends OTP — send it back with **spaces between digits**
   (e.g. `1 2 3 4 5`) to prevent invalidation.
4. If 2FA is enabled, send the password.
5. Session string is stored in MongoDB.
