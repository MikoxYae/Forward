# CHANGES

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
