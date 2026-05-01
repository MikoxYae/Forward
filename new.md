# Changelog — multi-bot branch

---

## v3 — Separate Destinations + Bot Chat Filtering + Force-Sub Detection

### Settings — Alag Alag Destinations
- `/forward` aur `/batch` ke liye ab **alag destination set** ho sakta hai
- `📤 Fwd Dest` button → `/forward` ke liye destination
- `📦 Batch Dest` button → `/batch` (bot chat save) ke liye destination
- Agar Batch Dest set nahi → `/batch` apne aap Fwd Dest use karta hai (fallback)
- `🗑 Rm Fwd Dest` — sirf forward destination hatao
- `🗑 Rm Batch Dest` — sirf batch destination hatao
- `📋 List Settings` — dono destinations clearly dikhata hai

### Bot Chat — Sirf Bot Ke Messages Save Honge
- `/batch t.me/bot/...` ke range mein ab **outgoing messages skip** hote hain
- Outgoing = jo messages aapne bot ko bheje (commands, queries)
- Sirf bot ke replies/content/files save honge
- Pehle: range mein sab messages aate the including apne commands

### Force Subscribe Detection — Auto Skip
- Agar bot ne force subscribe message bheja (join channel/group type), wo automatically **detect aur skip** hoga
- Detection: message mein join/subscribe words + inline button with `t.me/+` invite link
- Progress counter mein `skipped` mein count hoga

---

## v2 — Bug Fixes

### settings.py
- Double `query.answer()` bug fix — Remove Fwd/Batch Dest toast ab sahi dikhta hai
- `📦 Batch Dest` button add
- `📤 Fwd Dest` button — "Set Source" ki jagah (source always link se aata hai)

### logins.py
- `/logout` command add — seedha type karne par kaam karega
- `logout` excluded commands mein add — login flow intercept nahi karega

### forward.py
- `_send_one`: FloodWait ke baad `msg.copy()` ek baar retry hoti hai
- `_send_media_group`: same retry logic for `copy_media_group()`
- `_upload_file()`: naya helper — sab media types ke liye FloodWait retry
- `_download_reupload()`: text messages mein bhi FloodWait retry

---

## v1 — New Features

### Bot Chat Link (`t.me/bot/<username>/<msgid>`)
- Naya format: `https://t.me/bot/<botusername>/<msgid>[-<msgid>]`
- `/forward` aur `/batch` dono mein kaam karta hai
- Plus Messenger (unofficial client) se bot chat message IDs milte hain
- Login required

### `/batch` Command
- Alag `batch_dest` setting use karta hai (fallback: fwd dest)
- Sab link formats support — including bot chat links
- Start menu mein button add: `📦 Batch / Bot Save`
- Login flow se exclude

### Auto-Accept — 15 Guna Faster
- 15 simultaneous approvals — `asyncio.Semaphore(15)`
- DB save, counters, welcome PM — sab background mein concurrently
- Koi artificial delay nahi

### Faster Forwarding
- Loop delay: `1.0s → 0.2s`
- FloodWait auto-handled
- Progress har 4 second mein update

---

## Commands

| Command | Kaam |
|---|---|
| `/login` | Apne Telegram account se sign in |
| `/logout` | Sign out, session remove |
| `/cancel` | Login flow cancel |
| `/forward <link>` | Channel ya bot chat se forward |
| `/batch <link>` | Bot chat se batch save (alag dest) |
| `/stop` | Running task cancel |
| `/settings` | Settings panel kholo |
| `/approve <chat>` | Sab pending join requests bulk approve |

## Link Formats

```
Private channel:   https://t.me/c/<id>/<start>-<end>
Public channel:    https://t.me/<username>/<start>-<end>
Bot chat single:   https://t.me/bot/<botusername>/<msgid>
Bot chat range:    https://t.me/bot/<botusername>/<start>-<end>
```

## Important Notes

- **Bot chat save**: login required. Plus Messenger se message IDs lena padega.
- **Force subscribe**: source bot agar join channel bole → bot wo message skip karega automatically.
- **Protected content**: `msg.copy()` fail → bytes directly download → re-upload. Forward restriction se protect nahi hota.
- **Outgoing skip**: bot chat mode mein apne bheje hue commands skip honge — sirf bot ke responses save honge.
- **Batch fallback**: `/batch` ke liye agar `batch_dest` set nahi, to `fwd dest` use hoga. Agar dono nahi → error.
