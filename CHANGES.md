# CHANGES

## Fix: Sender Filter for `/forward` command

### Problem
When using `/forward` with a public bot/channel link (e.g. `https://t.me/Basic_need2bot/102130-134653`),
the bot was forwarding **all messages** in that ID range — including messages sent by **other bots or users**
inside the same chat. This caused irrelevant content from other senders to leak into the destination channel.

### Root Cause
The forward loop fetched every message by ID in the given range but had **no check** on who sent the message.
In public group-style bots, multiple bots or users may post in the same chat, each with different `from_user`
or `sender_chat` fields.

### Fix
Added a sender filter (`_sender_allowed`) that compares the **username** (for public links) or **numeric ID**
(for private `t.me/c/...` links) of each message's sender against the source entity from the `/forward` link.

- ✅ Messages from the source bot/channel → forwarded as normal
- ❌ Messages from any other sender → **skipped** (counted in the skip counter)

For private numeric-ID channels (`-100...`), the filter is bypassed since every message in that channel
already belongs to it.

### Files Changed
- `plugins/forward.py` — added `_get_sender_username`, `_get_sender_id`, `_sender_allowed` helpers
  and applied the filter inside the main forward loop.
