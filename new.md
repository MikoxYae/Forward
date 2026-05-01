# Changelog & New Features

## 1. Bot Chat Support (`/forward` + `/batch`)

Bot ke messages directly save karo — restricted bots se bhi.

### Link Formats

| Type | Format | Example |
|---|---|---|
| Single bot message | `https://t.me/bot/<botusername>/<msg_id>` | `https://t.me/bot/save_restrict_1bot/8628` |
| Bot batch (range) | `https://t.me/bot/<botusername>/<first>-<last>` | `https://t.me/bot/save_restrict_1bot/8628-8650` |
| Private channel | `https://t.me/c/<id>/<start>-<end>` | `https://t.me/c/1234567890/10-200` |
| Public channel | `https://t.me/<username>/<start>-<end>` | `https://t.me/mychannel/1-500` |

### How to get Bot Message IDs

1. Install **Plus Messenger** (unofficial Telegram client)
2. Open the bot chat → long-press any message
3. Message ID will be visible in the options

### Requirements

- Must be logged in (`/login`)
- Destination must be set in `/settings`
- The bot must have already sent those messages to you (your own DM history with the bot)

---

## 2. New Command: `/batch`

```
/batch <link>
```

Same as `/forward` but labeled separately for clarity.  
Both `/forward` and `/batch` now support **bot chat links**.

```
/batch https://t.me/bot/save_restrict_1bot/8628-8650
/batch https://t.me/c/1234567890/10-200
/batch https://t.me/channelname/1-500
```

Use `/stop` to cancel any running task.

---

## 3. Settings Improvements

New buttons added in `/settings`:

| Button | Action |
|---|---|
| `🗑 Remove Src` | Remove saved source channel |
| `🗑 Remove Dest` | Remove saved destination channel |
| `📋 List Settings` | Show current login/source/dest status |

The old `🧹 Clear Fwd` button (clears both) is removed from main view — use the individual remove buttons instead.

---

## 4. Commands Menu — New Button

In `/start` → Commands menu, a new button **📦 Batch / Bot Save** has been added.

It explains:
- What bot chat saving is
- How to get message IDs using Plus Messenger
- All supported link formats
- Requirements

---

## 5. Faster Auto-Accept

Join requests are now accepted **instantly** using concurrent processing:

- Up to **15 simultaneous approvals** run at the same time (was 1 at a time before)
- No artificial delay between requests
- DB saves and welcome PMs run in background — they do NOT block the approval
- FloodWait is handled with automatic retry (up to 3 attempts per user)

---

## 6. Faster Forwarding

Forward/batch speed improved:

- Delay between messages reduced from **1.0s → 0.2s**
- Media group fallback delay reduced from **0.5s → 0.2s**
- FloodWait is still respected (automatic sleep when Telegram asks)
- Progress update interval: every 4 seconds (was 5)

---

## File Changes Summary

| File | What changed |
|---|---|
| `plugins/forward.py` | Bot chat link parsing, `/batch` command, faster loop (0.2s delay), shared `_run_forward()` function |
| `plugins/accept.py` | Concurrent approvals (15 semaphore), background DB saves, no artificial delay |
| `plugins/start.py` | New `📦 Batch / Bot Save` button in commands menu, `BATCH_TEXT` description added |
| `plugins/settings.py` | Remove Source, Remove Dest, List Settings buttons added |
| `plugins/logins.py` | `/batch` added to excluded commands in login flow filter |
| `new.md` | This file |
