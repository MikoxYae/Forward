# Forward Bot

<b>ᴀ ᴛᴇʟᴇɢʀᴀᴍ ʙᴏᴛ ᴛʜᴀᴛ ᴄʟᴏɴᴇs / ғᴏʀᴡᴀʀᴅs ᴍᴇᴅɪᴀ ғʀᴏᴍ ᴏɴᴇ ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴀɴᴏᴛʜᴇʀ — ɪɴᴄʟᴜᴅɪɴɢ ᴄʜᴀɴɴᴇʟs ᴡɪᴛʜ ʀᴇsᴛʀɪᴄᴛᴇᴅ (ɴᴏ-ғᴏʀᴡᴀʀᴅ) ᴄᴏɴᴛᴇɴᴛ, ʙʏ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ᴀɴᴅ ʀᴇ-ᴜᴘʟᴏᴀᴅɪɴɢ ᴛʜᴇ ᴍᴇᴅɪᴀ ᴜsɪɴɢ ᴀ ʟᴏɢɢᴇᴅ-ɪɴ ᴜsᴇʀ sᴇssɪᴏɴ.</b>

## ғᴇᴀᴛᴜʀᴇs

- <b>ғᴏʀᴡᴀʀᴅ ᴍᴇᴅɪᴀ ʙᴇᴛᴡᴇᴇɴ ᴄʜᴀɴɴᴇʟs (sᴀᴍᴇ-ᴛᴏ-sᴀᴍᴇ)</b>
- <b>ʙʏᴘᴀss ʀᴇsᴛʀɪᴄᴛᴇᴅ / ᴘʀᴏᴛᴇᴄᴛᴇᴅ ᴄʜᴀɴɴᴇʟs ʙʏ ᴅᴏᴡɴʟᴏᴀᴅ → ʀᴇ-ᴜᴘʟᴏᴀᴅ</b>
- <b>ᴀɴʏᴏɴᴇ ᴄᴀɴ ʟᴏɢɪɴ ᴡɪᴛʜ ᴛʜᴇɪʀ ᴏᴡɴ ᴛᴇʟᴇɢʀᴀᴍ ᴀᴄᴄᴏᴜɴᴛ — ɪɴʟɪɴᴇ ʟᴏɢɪɴ ʙᴜᴛᴛᴏɴ ᴏʀ /login</b>
- <b>ᴘᴇʀ-ᴜsᴇʀ sᴏᴜʀᴄᴇ & ᴅᴇsᴛɪɴᴀᴛɪᴏɴ sᴇᴛᴛɪɴɢs</b>
- <b>ᴀʟʟ ғᴏʀᴡᴀʀᴅᴇᴅ ᴄᴀᴘᴛɪᴏɴs ᴀʀᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ʙᴏʟᴅᴇᴅ ᴜsɪɴɢ <code>&lt;b&gt;...&lt;/b&gt;</code> ʜᴛᴍʟ ᴛᴀɢs</b>
- <b>ᴍᴏɴɢᴏᴅʙ-ʙᴀᴄᴋᴇᴅ sᴛᴏʀᴀɢᴇ ғᴏʀ ᴜsᴇʀs, sᴇssɪᴏɴs, ᴀɴᴅ sᴇᴛᴛɪɴɢs</b>

## ᴘʀᴏᴊᴇᴄᴛ sᴛʀᴜᴄᴛᴜʀᴇ

```
.
├── miko.py              # entry point: python3 miko.py
├── config.py            # environment configuration
├── requirements.txt
├── database/
│   └── db.py            # mongodb (motor) wrapper
└── plugins/
    ├── start.py         # /start, /help — photo + Login/Logout buttons
    ├── logins.py        # /login, /logout, /cancel + button-driven login flow
    ├── settings.py      # /settings, /setsource, /setdest, /clearsettings
    └── forward.py       # /forward, /stop — clones a message range
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
   ```

4. <b>ɪɴsᴛᴀʟʟ ᴅᴇᴘᴇɴᴅᴇɴᴄɪᴇs:</b>

   ```bash
   pip install -r requirements.txt
   ```

5. <b>ʀᴜɴ ᴛʜᴇ ʙᴏᴛ:</b>

   ```bash
   python3 miko.py
   ```

## ᴄᴏᴍᴍᴀɴᴅs

| ᴄᴏᴍᴍᴀɴᴅ | ᴡʜᴏ | ᴅᴇsᴄʀɪᴘᴛɪᴏɴ |
| --- | --- | --- |
| <code>/start</code>, <code>/help</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>sʜᴏᴡ ʜᴇʟᴘ ᴡɪᴛʜ ʟᴏɢɪɴ / ʟᴏɢᴏᴜᴛ ʙᴜᴛᴛᴏɴs</b> |
| <code>/login</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>ʟᴏɢɪɴ ᴡɪᴛʜ ʏᴏᴜʀ ᴛᴇʟᴇɢʀᴀᴍ ᴀᴄᴄᴏᴜɴᴛ</b> |
| <code>/logout</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>ʀᴇᴍᴏᴠᴇ ʏᴏᴜʀ sᴀᴠᴇᴅ sᴇssɪᴏɴ</b> |
| <code>/cancel</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>ᴄᴀɴᴄᴇʟ ᴄᴜʀʀᴇɴᴛ ʟᴏɢɪɴ ғʟᴏᴡ</b> |
| <code>/settings</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>ᴠɪᴇᴡ ʏᴏᴜʀ ᴄᴜʀʀᴇɴᴛ sᴏᴜʀᴄᴇ & ᴅᴇsᴛɪɴᴀᴛɪᴏɴ</b> |
| <code>/setsource &lt;id&gt;</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>sᴇᴛ ʏᴏᴜʀ sᴏᴜʀᴄᴇ ᴄʜᴀɴɴᴇʟ</b> |
| <code>/setdest &lt;id&gt;</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>sᴇᴛ ʏᴏᴜʀ ᴅᴇsᴛɪɴᴀᴛɪᴏɴ ᴄʜᴀɴɴᴇʟ</b> |
| <code>/clearsettings</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>ᴄʟᴇᴀʀ ʏᴏᴜʀ sᴏᴜʀᴄᴇ & ᴅᴇsᴛɪɴᴀᴛɪᴏɴ</b> |
| <code>/forward &lt;link&gt;</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>sᴛᴀʀᴛ ᴄʟᴏɴɪɴɢ ᴀ ᴍᴇssᴀɢᴇ ʀᴀɴɢᴇ</b> |
| <code>/stop</code> | <b>ᴀɴʏᴏɴᴇ</b> | <b>sᴛᴏᴘ ᴛʜᴇ ʀᴜɴɴɪɴɢ ғᴏʀᴡᴀʀᴅ</b> |

## ʟᴏɢɪɴ ғʟᴏᴡ

1. <b>ᴛᴀᴘ ᴛʜᴇ ʟᴏɢɪɴ ʙᴜᴛᴛᴏɴ ᴜɴᴅᴇʀ</b> <code>/start</code><b>, ᴏʀ sᴇɴᴅ</b> <code>/login</code><b>.</b>
2. <b>sᴇɴᴅ ʏᴏᴜʀ ᴘʜᴏɴᴇ ɴᴜᴍʙᴇʀ ᴡɪᴛʜ ᴄᴏᴜɴᴛʀʏ ᴄᴏᴅᴇ (ᴇ.ɢ.</b> <code>+919876543210</code><b>).</b>
3. <b>ᴛᴇʟᴇɢʀᴀᴍ sᴇɴᴅs ᴛʜᴇ ᴏᴛᴘ — sᴇɴᴅ ɪᴛ ʙᴀᴄᴋ ᴡɪᴛʜ <i>sᴘᴀᴄᴇs ʙᴇᴛᴡᴇᴇɴ ᴅɪɢɪᴛs</i> (ᴇ.ɢ.</b> <code>1 2 3 4 5</code><b>) sᴏ ᴛᴇʟᴇɢʀᴀᴍ ᴅᴏᴇs ɴᴏᴛ ɪɴᴠᴀʟɪᴅᴀᴛᴇ ɪᴛ.</b>
4. <b>ɪғ ᴛᴡᴏ-sᴛᴇᴘ ᴠᴇʀɪғɪᴄᴀᴛɪᴏɴ ɪs ᴇɴᴀʙʟᴇᴅ, sᴇɴᴅ ʏᴏᴜʀ ᴘᴀssᴡᴏʀᴅ.</b>
5. <b>ᴛʜᴇ sᴇssɪᴏɴ sᴛʀɪɴɢ ɪs sᴀᴠᴇᴅ ɪɴ ᴍᴏɴɢᴏᴅʙ.</b>

<b>ᴛʜᴇ ʟᴏɢɪɴ ʙᴜᴛᴛᴏɴ ᴇᴅɪᴛs ᴛʜᴇ sᴀᴍᴇ</b> <code>/start</code> <b>ᴍᴇssᴀɢᴇ ᴀᴛ ᴇᴀᴄʜ sᴛᴇᴘ — ᴋᴇᴇᴘɪɴɢ ᴛʜᴇ ᴄʜᴀᴛ ᴄʟᴇᴀɴ. ᴀ ʙᴀᴄᴋ ʙᴜᴛᴛᴏɴ ʀᴇᴛᴜʀɴs ᴛᴏ ᴛʜᴇ ᴍᴀɪɴ ᴘᴀɴᴇʟ.</b>

## ғᴏʀᴡᴀʀᴅ ᴜsᴀɢᴇ

```
/forward https://t.me/c/<channel_id>/<start>-<end>
/forward https://t.me/<username>/<start>-<end>
/forward https://t.me/c/<channel_id>/<msg_id>      # single message
```

<b>ᴇxᴀᴍᴘʟᴇ:</b>

```
/forward https://t.me/c/3954900378/2-100
```

<b>ᴄʟᴏɴᴇs ᴍᴇssᴀɢᴇs 2 ᴛʜʀᴏᴜɢʜ 100 ғʀᴏᴍ ᴛʜᴇ ɢɪᴠᴇɴ ᴄʜᴀɴɴᴇʟ ᴛᴏ ʏᴏᴜʀ sᴀᴠᴇᴅ ᴅᴇsᴛɪɴᴀᴛɪᴏɴ — ᴛᴇxᴛ, ᴍᴇᴅɪᴀ, ᴀʟʙᴜᴍs, ᴀɴᴅ ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴄᴏɴᴛᴇɴᴛ ᴀʟʟ ʜᴀɴᴅʟᴇᴅ. ᴄᴀᴘᴛɪᴏɴs ᴀʀᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴡʀᴀᴘᴘᴇᴅ ɪɴ</b> <code>&lt;b&gt;...&lt;/b&gt;</code> <b>ʙᴏʟᴅ ᴛᴀɢs.</b>
