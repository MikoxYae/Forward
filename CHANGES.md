# CHANGES

## Fix 3: Destination peer not resolved → ALL messages fail (PeerIdInvalid)

### Problem
Every message was counted as **fail** when using `/forward` with a numeric destination
channel ID (e.g. `/setdest -1001234567890`).

### Root Cause
`user_client` is started as an **in-memory session** — it has zero peer cache.
The code already resolved the **source** channel's `access_hash` so `get_messages`
works. But the **destination** channel was never resolved. Every subsequent send call
(`msg.copy`, `send_photo`, `send_video`, etc.) hits Pyrogram's peer lookup, finds
nothing, and raises `PeerIdInvalid` → the message is counted as fail without a useful
error shown to the user.

### Fix
Added a **3-step destination peer resolution** block (identical pattern to source
resolution) that runs right after the source pre-flight check:

| Step | Action |
|---|---|
| 1 | `get_chat(dest)` — fast path if already cached |
| 2 | Raw `GetChannels` with `access_hash=0` — works when user is a member |
| 3 | Walk `iter_dialogs` — definitive check that also caches the peer |

If all three steps fail the bot now shows a clear error telling the user their
account is not a member/admin of the destination channel.

### Also fixed (same PR)
- `_send_one`: after a `FloodWait` the copy is now **retried once** before
  falling through to the download-reupload path (previously it slept and then
  immediately went to re-upload).

---

## Fix 2: Batch/Album broken on restricted channels

## Fix 1: Sender Filter for `/forward` command

### Problem
When using `/forward` with a public bot/channel link (e.g. `https://t.me/Basic_need2bot/102130-134653`),
the bot forwarded **all messages** in the range — including messages from **other bots/users** in the same chat.

### Fix
Added `_sender_allowed()` helper that checks each message's sender (by username for public links,
by numeric ID for private `t.me/c/...` links) against the source in the link.

- ✅ Messages from the source bot/channel → forwarded
- ❌ Messages from any other sender → skipped

---

## Fix 2: Batch/Album broken on restricted channels

### Problem
When a message was part of a media group (album/batch) on a **restricted channel**:
1. `get_media_group()` fails → `group = []`  (empty list)
2. `copy_media_group()` also fails (restricted)
3. Fallback loop runs on empty `group` → **nothing forwarded** ❌
4. Bot silently returns `False`, album is lost

### Root Cause
```python
except Exception:
    group = []   # ← silent failure, group wiped
    captions = None

# ... copy_media_group fails too ...

for item in group:   # ← group is [], loop never runs
    download_reupload(item)

return False  # ← entire album silently dropped
```

### Fix
Added a **4-step fallback chain** in `_send_media_group`:

| Step | Action | Works when |
|---|---|---|
| 1 | `get_media_group` | Always tried first |
| 2 | `copy_media_group` | Non-restricted channels |
| 3 | Per-item `download_reupload` loop | Restricted + album fetch succeeded |
| 4 | Single anchor-message `download_reupload` | Restricted + album fetch failed |

Step 4 is the key new addition — even if the full album can't be fetched, the **anchor message** (the one whose ID was in the range) is still downloaded and re-uploaded individually, so nothing is silently lost.

### Files Changed
- `plugins/forward.py` — both fixes applied
