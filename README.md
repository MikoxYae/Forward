# Forward + Auto-Accept Bot

<b>ᴀ ᴛᴇʟᴇɢʀᴀᴍ ʙᴏᴛ ᴛʜᴀᴛ ᴄʟᴏɴᴇs / ғᴏʀᴡᴀʀᴅs ᴍᴇᴅɪᴀ ʙᴇᴛᴡᴇᴇɴ ᴄʜᴀɴɴᴇʟs (ɪɴᴄʟᴜᴅɪɴɢ ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴏɴᴇs) ᴀɴᴅ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴀᴄᴄᴇᴘᴛs ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs ɪɴ ᴀɴʏ ᴄʜᴀɴɴᴇʟ / ɢʀᴏᴜᴘ ᴡʜᴇʀᴇ ɪᴛ ɪs ᴀɴ ᴀᴅᴍɪɴ — ᴀʟʟ ɪɴ ᴀ sɪɴɢʟᴇ ʙᴏᴛ.</b>

## ғᴇᴀᴛᴜʀᴇs

### ғᴏʀᴡᴀʀᴅ

- <b>ғᴏʀᴡᴀʀᴅ ᴍᴇᴅɪᴀ ʙᴇᴛᴡᴇᴇɴ ᴄʜᴀɴɴᴇʟs (sᴀᴍᴇ-ᴛᴏ-sᴀᴍᴇ)</b>
- <b>ʙʏᴘᴀss ʀᴇsᴛʀɪᴄᴛᴇᴅ / ᴘʀᴏᴛᴇᴄᴛᴇᴅ ᴄʜᴀɴɴᴇʟs ʙʏ ᴅᴏᴡɴʟᴏᴀᴅ → ʀᴇ-ᴜᴘʟᴏᴀᴅ</b>
- <b>ᴀɴʏᴏɴᴇ ᴄᴀɴ ʟᴏɢɪɴ ᴡɪᴛʜ ᴛʜᴇɪʀ ᴏᴡɴ ᴛᴇʟᴇɢʀᴀᴍ ᴀᴄᴄᴏᴜɴᴛ — ɪɴʟɪɴᴇ ʟᴏɢɪɴ ʙᴜᴛᴛᴏɴ ᴏʀ <code>/login</code></b>
- <b>ᴘᴇʀ-ᴜsᴇʀ sᴏᴜʀᴄᴇ & ᴅᴇsᴛɪɴᴀᴛɪᴏɴ sᴇᴛᴛɪɴɢs</b>
- <b>ᴀʟʟ ғᴏʀᴡᴀʀᴅᴇᴅ ᴄᴀᴘᴛɪᴏɴs ᴀʀᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ʙᴏʟᴅᴇᴅ ᴜsɪɴɢ <code>&lt;b&gt;...&lt;/b&gt;</code> ʜᴛᴍʟ ᴛᴀɢs</b>

### ᴀᴜᴛᴏ-ᴀᴄᴄᴇᴘᴛ

- <b>ᴀᴜᴛᴏ-ᴀᴘᴘʀᴏᴠᴇs ᴇᴠᴇʀʏ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ ᴛʜᴇ ʙᴏᴛ sᴇᴇs (ᴄʜᴀɴɴᴇʟ ᴏʀ ɢʀᴏᴜᴘ)</b>
- <b>ᴏᴘᴛɪᴏɴᴀʟ ᴡᴇʟᴄᴏᴍᴇ ᴘᴍ ᴡɪᴛʜ ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀs (<code>{mention}</code>, <code>{first_name}</code>, <code>{username}</code>, <code>{chat_title}</code>, <code>{chat_link}</code>, <code>{user_id}</code>)</b>
- <b>ᴘᴇʀ-ᴄʜᴀᴛ ᴄᴜsᴛᴏᴍ ᴡᴇʟᴄᴏᴍᴇ ᴍᴇssᴀɢᴇ + ᴏɴ / ᴏғғ ᴛᴏɢɢʟᴇ (ᴄʜᴀᴛ ᴀᴅᴍɪɴs)</b>
- <b>ᴏᴡɴᴇʀ-ᴏɴʟʏ <code>/stats</code>, <code>/chats</code>, <code>/broadcast</code></b>
- <b>ғʟᴏᴏᴅᴡᴀɪᴛ-sᴀғᴇ ᴀɴᴅ ᴀᴜᴛᴏ-ᴄʟᴇᴀɴs ᴅᴇᴀᴅ ᴜsᴇʀs ᴏɴ ʙʀᴏᴀᴅᴄᴀsᴛ</b>

## ᴘʀᴏᴊᴇᴄᴛ sᴛʀᴜᴄᴛᴜʀᴇ

```
.
├── miko.py              # entry point: python3 miko.py
├── config.py            # environment configuration
├── requirements.txt
├── database/
│   └── db.py            # mongodb (motor) wrapper — users, sessions, chats, settings, counters
└── plugins/
    ├── start.py         # /start, /help — photo + Login/Logout buttons
    ├── logins.py        # /login, /logout, /cancel + button-driven login flow
    ├── settings.py      # /settings, /setsource, /setdest, /clearsettings
    ├── forward.py       # /forward, /stop — clones a message range
    ├── approve.py       # /approve <chat> — bulk-approve old pending join requests
    ├── accept.py        # auto-accept ChatJoinRequest handler + welcome PM
    ├── welcome.py       # /setwelcome, /clearwelcome, /togglewelcome, /welcome
    ├── stats.py         # /stats, /chats — owner only
    └── broadcast.py     # /broadcast — owner only
```

## sᴇᴛᴜᴘ

1. <b>ᴄʀᴇᴀᴛᴇ ᴀ ʙᴏᴛ ᴠɪᴀ</b> [@BotFather](https://t.me/BotFather) <b>ᴀɴᴅ ɢᴇᴛ ᴛʜᴇ</b> <code>BOT_TOKEN</code><b>.</b>
2. <b>ɢᴇᴛ</b> <code>APP_ID</code> <b>ᴀɴᴅ</b> <code>API_HASH</code> <b>ғʀᴏᴍ</b> <https://my.telegram.org><b>.</b>
3. <b>sᴇᴛ ᴛʜᴇ ᴇɴᴠɪʀᴏɴᴍᴇɴᴛ ᴠᴀʀɪᴀʙʟᴇs (ᴏʀ ᴇᴅɪᴛ ᴛʜᴇ ᴅᴇғᴀᴜʟᴛs ɪɴ</b> <code>config.py</code><b>):</b>

   ```
   BOT_TOKEN=...
   APP_ID=...
   API_HASH=...
   OWNER=your_telegram_username
   OWNER_ID=your_numeric_id
   MONGO_URI=mongodb+srv://...
   DATABASE_NAME=Forward
   START_PIC=https://graph.org/file/...   # optional
   ACCEPT_DELAY=0                          # optional, seconds before each approve
   DEFAULT_WELCOME=...                     # optional, default welcome PM template
   ```

4. <b>ɪɴsᴛᴀʟʟ ᴅᴇᴘᴇɴᴅᴇɴᴄɪᴇs:</b>

   ```bash
   pip install -r requirements.txt
   ```

5. <b>ʀᴜɴ ᴛʜᴇ ʙᴏᴛ:</b>

   ```bash
   python3 miko.py
   ```

6. <b>ғᴏʀ ᴀᴜᴛᴏ-ᴀᴄᴄᴇᴘᴛ — ᴀᴅᴅ ᴛʜᴇ ʙᴏᴛ ᴀs ᴀɴ ᴀᴅᴍɪɴ ɪɴ ʏᴏᴜʀ ᴄʜᴀɴɴᴇʟ / ɢʀᴏᴜᴘ ᴡɪᴛʜ "ᴀᴅᴅ ᴍᴇᴍʙᴇʀs" ᴘᴇʀᴍɪssɪᴏɴ, ᴀɴᴅ ᴇɴᴀʙʟᴇ "ᴀᴘᴘʀᴏᴠᴇ ɴᴇᴡ ᴍᴇᴍʙᴇʀs".</b>

## ᴄᴏᴍᴍᴀɴᴅs

| ᴄᴏᴍᴍᴀɴᴅ | ᴡʜᴏ | ᴅᴇsᴄʀɪᴘᴛɪᴏɴ |
| --- | --- | --- |
| <code>/start</code>, <code>/help</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>sʜᴏᴡ ʜᴇʟᴘ + ʟᴏɢɪɴ / ʟᴏɢᴏᴜᴛ ʙᴜᴛᴛᴏɴs</b> |
| <code>/login</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>ʟᴏɢɪɴ ᴡɪᴛʜ ʏᴏᴜʀ ᴛᴇʟᴇɢʀᴀᴍ ᴀᴄᴄᴏᴜɴᴛ</b> |
| <code>/logout</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>ʀᴇᴍᴏᴠᴇ ʏᴏᴜʀ sᴀᴠᴇᴅ sᴇssɪᴏɴ</b> |
| <code>/cancel</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>ᴄᴀɴᴄᴇʟ ᴄᴜʀʀᴇɴᴛ ʟᴏɢɪɴ ғʟᴏᴡ</b> |
| <code>/settings</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>ᴠɪᴇᴡ ʏᴏᴜʀ ᴄᴜʀʀᴇɴᴛ sᴏᴜʀᴄᴇ & ᴅᴇsᴛɪɴᴀᴛɪᴏɴ</b> |
| <code>/setsource &lt;id&gt;</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>sᴇᴛ ʏᴏᴜʀ sᴏᴜʀᴄᴇ ᴄʜᴀɴɴᴇʟ</b> |
| <code>/setdest &lt;id&gt;</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>sᴇᴛ ʏᴏᴜʀ ᴅᴇsᴛɪɴᴀᴛɪᴏɴ ᴄʜᴀɴɴᴇʟ</b> |
| <code>/clearsettings</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>ᴄʟᴇᴀʀ ʏᴏᴜʀ sᴏᴜʀᴄᴇ & ᴅᴇsᴛɪɴᴀᴛɪᴏɴ</b> |
| <code>/forward &lt;link&gt;</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>sᴛᴀʀᴛ ᴄʟᴏɴɪɴɢ ᴀ ᴍᴇssᴀɢᴇ ʀᴀɴɢᴇ</b> |
| <code>/stop</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>sᴛᴏᴘ ᴛʜᴇ ʀᴜɴɴɪɴɢ ғᴏʀᴡᴀʀᴅ</b> |
| <code>/approve &lt;chat&gt;</code> | <b>ʟᴏɢɢᴇᴅ-ɪɴ ᴜsᴇʀ</b> | <b>ʙᴜʟᴋ-ᴀᴘᴘʀᴏᴠᴇ ᴀʟʟ ᴘᴇɴᴅɪɴɢ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs ɪɴ ᴀ ᴄʜᴀɴɴᴇʟ ᴜsɪɴɢ ʏᴏᴜʀ sᴇssɪᴏɴ (ʏᴏᴜ ᴍᴜsᴛ ʙᴇ ᴀᴅᴍɪɴ ᴛʜᴇʀᴇ)</b> |
| <code>/setwelcome &lt;text&gt;</code> | <b>ᴄʜᴀᴛ ᴀᴅᴍɪɴ</b> | <b>sᴇᴛ ᴄᴜsᴛᴏᴍ ᴡᴇʟᴄᴏᴍᴇ ᴘᴍ ғᴏʀ ᴛʜᴇ ᴄʜᴀᴛ</b> |
| <code>/clearwelcome</code> | <b>ᴄʜᴀᴛ ᴀᴅᴍɪɴ</b> | <b>ʀᴇsᴇᴛ ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴅᴇғᴀᴜʟᴛ</b> |
| <code>/togglewelcome</code> | <b>ᴄʜᴀᴛ ᴀᴅᴍɪɴ</b> | <b>ᴛᴜʀɴ ᴡᴇʟᴄᴏᴍᴇ ᴘᴍ ᴏɴ / ᴏғғ</b> |
| <code>/welcome</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>sʜᴏᴡ ᴄᴜʀʀᴇɴᴛ ᴡᴇʟᴄᴏᴍᴇ ᴛᴇᴍᴘʟᴀᴛᴇ + sᴛᴀᴛᴜs</b> |
| <code>/stats</code> | <b>ᴏᴡɴᴇʀ</b> | <b>ᴛᴏᴛᴀʟ ᴜsᴇʀs, ᴄʜᴀᴛs, ᴀɴᴅ ʀᴇǫᴜᴇsᴛs ᴀᴄᴄᴇᴘᴛᴇᴅ</b> |
| <code>/chats</code> | <b>ᴏᴡɴᴇʀ</b> | <b>ᴘᴇʀ-ᴄʜᴀᴛ ᴀᴄᴄᴇᴘᴛᴀɴᴄᴇ ᴄᴏᴜɴᴛs</b> |
| <code>/broadcast</code> | <b>ᴏᴡɴᴇʀ</b> | <b>ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ sᴇɴᴅ ɪᴛ ᴛᴏ ᴀʟʟ ᴜsᴇʀs</b> |

## ʟᴏɢɪɴ ғʟᴏᴡ

1. <b>ᴛᴀᴘ ᴛʜᴇ ʟᴏɢɪɴ ʙᴜᴛᴛᴏɴ ᴜɴᴅᴇʀ</b> <code>/start</code><b>, ᴏʀ sᴇɴᴅ</b> <code>/login</code><b>.</b>
2. <b>sᴇɴᴅ ʏᴏᴜʀ ᴘʜᴏɴᴇ ɴᴜᴍʙᴇʀ ᴡɪᴛʜ ᴄᴏᴜɴᴛʀʏ ᴄᴏᴅᴇ (ᴇ.ɢ.</b> <code>+919876543210</code><b>).</b>
3. <b>ᴛᴇʟᴇɢʀᴀᴍ sᴇɴᴅs ᴛʜᴇ ᴏᴛᴘ — sᴇɴᴅ ɪᴛ ʙᴀᴄᴋ ᴡɪᴛʜ <i>sᴘᴀᴄᴇs ʙᴇᴛᴡᴇᴇɴ ᴅɪɢɪᴛs</i> (ᴇ.ɢ.</b> <code>1 2 3 4 5</code><b>) sᴏ ᴛᴇʟᴇɢʀᴀᴍ ᴅᴏᴇs ɴᴏᴛ ɪɴᴠᴀʟɪᴅᴀᴛᴇ ɪᴛ.</b>
4. <b>ɪғ ᴛᴡᴏ-sᴛᴇᴘ ᴠᴇʀɪғɪᴄᴀᴛɪᴏɴ ɪs ᴇɴᴀʙʟᴇᴅ, sᴇɴᴅ ʏᴏᴜʀ ᴘᴀssᴡᴏʀᴅ.</b>
5. <b>ᴛʜᴇ sᴇssɪᴏɴ sᴛʀɪɴɢ ɪs sᴀᴠᴇᴅ ɪɴ ᴍᴏɴɢᴏᴅʙ.</b>
