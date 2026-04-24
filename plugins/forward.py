import asyncio
import os
import re
import time

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from config import APP_ID, API_HASH
from database.db import db


# Per-user forward task state
forward_state: dict[int, dict] = {}


# --------------- Link parsing ---------------
# Private channel:  https://t.me/c/<internal_id>/<msg_id>[-<msg_id>]
# Public channel:   https://t.me/<username>/<msg_id>[-<msg_id>]
PRIVATE_RE = re.compile(r"https?://t\.me/c/(\d+)/(\d+)(?:[-/](\d+))?/?$")
PUBLIC_RE = re.compile(r"https?://t\.me/([a-zA-Z][\w\d_]{3,})/(\d+)(?:[-/](\d+))?/?$")


def parse_link(url: str):
    """Return (chat_id_or_username, start_id, end_id) or None."""
    url = url.strip()

    m = PRIVATE_RE.match(url)
    if m:
        chat = int("-100" + m.group(1))
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        return chat, start, end

    m = PUBLIC_RE.match(url)
    if m:
        chat = m.group(1)
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        return chat, start, end

    return None


def _resolve_dest(dest_raw: str):
    try:
        return int(dest_raw)
    except (ValueError, TypeError):
        return dest_raw


# --------------- Commands ---------------
@Client.on_message(filters.command("forward") & filters.private)
async def forward_cmd(bot: Client, message: Message):
    user_id = message.from_user.id

    if len(message.command) < 2:
        return await message.reply_text(
            "**Usage:** `/forward <link>`\n\n"
            "**Examples:**\n"
            "`/forward https://t.me/c/1234567890/2-100`\n"
            "`/forward https://t.me/channelname/5-50`\n"
            "`/forward https://t.me/c/1234567890/42`  (single message)"
        )

    if forward_state.get(user_id):
        return await message.reply_text(
            "A forward task is already running. Use /stop to cancel it first."
        )

    session_string = await db.get_session(user_id)
    if not session_string:
        return await message.reply_text(
            "You are not logged in. Use /login first."
        )

    dest_raw = await db.get_user_setting(user_id, "destination")
    if not dest_raw:
        return await message.reply_text(
            "Destination is not set. Use /setdest <channel_id_or_username>."
        )

    parsed = parse_link(message.command[1])
    if not parsed:
        return await message.reply_text(
            "Invalid link.\nUse `https://t.me/c/<id>/<start>-<end>` "
            "or `https://t.me/<username>/<start>-<end>`."
        )

    src, start_id, end_id = parsed
    if end_id < start_id:
        start_id, end_id = end_id, start_id

    dest = _resolve_dest(dest_raw)
    total = end_id - start_id + 1

    forward_state[user_id] = {"cancel": False}

    status = await message.reply_text(
        f"**Starting forward**\n"
        f"Source: `{src}`\n"
        f"Destination: `{dest}`\n"
        f"Range: `{start_id}` to `{end_id}` ({total} messages)\n\n"
        f"Use /stop to cancel."
    )

    # Spin up the user's MTProto session
    user_client = Client(
        name=f"user_{user_id}",
        api_id=APP_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True,
    )
    try:
        await user_client.start()
    except Exception as e:
        forward_state.pop(user_id, None)
        return await status.edit_text(f"Failed to start your session: `{e}`")

    ok = fail = skip = 0
    seen_groups: set[str] = set()
    last_edit = 0.0

    try:
        for msg_id in range(start_id, end_id + 1):
            if forward_state.get(user_id, {}).get("cancel"):
                break

            # Fetch the message
            try:
                msg = await user_client.get_messages(src, msg_id)
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                try:
                    msg = await user_client.get_messages(src, msg_id)
                except Exception:
                    fail += 1
                    continue
            except Exception:
                fail += 1
                continue

            if not msg or getattr(msg, "empty", False) or msg.service:
                skip += 1
                continue

            # Album / media-group handling: copy whole group once
            if msg.media_group_id:
                if msg.media_group_id in seen_groups:
                    continue
                seen_groups.add(msg.media_group_id)
                if await _send_media_group(user_client, src, msg.id, dest):
                    ok += 1
                else:
                    fail += 1
            else:
                if await _send_one(user_client, msg, dest):
                    ok += 1
                else:
                    fail += 1

            # Pacing to avoid floods
            await asyncio.sleep(1.0)

            now = time.time()
            if now - last_edit > 5:
                try:
                    await status.edit_text(
                        f"**Forwarding...**\n"
                        f"Progress: `{msg_id - start_id + 1}/{total}`\n"
                        f"OK: `{ok}` | Failed: `{fail}` | Skipped: `{skip}`"
                    )
                except Exception:
                    pass
                last_edit = now
    finally:
        try:
            await user_client.stop()
        except Exception:
            pass
        forward_state.pop(user_id, None)

    await status.edit_text(
        f"**Done**\n"
        f"OK: `{ok}` | Failed: `{fail}` | Skipped: `{skip}`"
    )


@Client.on_message(filters.command("stop") & filters.private)
async def stop_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in forward_state:
        return await message.reply_text("No active forward task.")
    forward_state[user_id]["cancel"] = True
    await message.reply_text("Cancelling current forward task...")


# --------------- Internals ---------------
async def _send_one(user_client: Client, msg: Message, dest) -> bool:
    """Try forward → copy → download+reupload. Return True on success."""
    # 1) Native forward (keeps attribution)
    try:
        await msg.forward(dest)
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception:
        pass

    # 2) Copy (fresh send, no forward tag)
    try:
        await msg.copy(dest)
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception:
        pass

    # 3) Download + re-upload (works for restricted/protected content)
    return await _download_reupload(user_client, msg, dest)


async def _send_media_group(user_client: Client, src, anchor_id: int, dest) -> bool:
    """Copy a whole album. Falls back to per-item download+reupload."""
    try:
        await user_client.copy_media_group(dest, src, anchor_id)
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception:
        pass

    # Fallback: download each item in the group and send individually
    try:
        items = await user_client.get_media_group(src, anchor_id)
    except Exception:
        items = []
    any_ok = False
    for item in items:
        if await _download_reupload(user_client, item, dest):
            any_ok = True
        await asyncio.sleep(0.5)
    return any_ok


async def _download_reupload(user_client: Client, msg: Message, dest) -> bool:
    """Last-resort: pull media bytes and re-upload as a fresh message."""
    try:
        # Pure text
        if msg.text and not msg.media:
            try:
                await user_client.send_message(
                    dest, msg.text.html, disable_web_page_preview=True
                )
                return True
            except Exception:
                return False

        caption = msg.caption.html if msg.caption else None
        path = await user_client.download_media(msg)
        if not path:
            return False

        try:
            if msg.photo:
                await user_client.send_photo(dest, path, caption=caption)
            elif msg.video:
                await user_client.send_video(
                    dest,
                    path,
                    caption=caption,
                    duration=msg.video.duration,
                    width=msg.video.width,
                    height=msg.video.height,
                )
            elif msg.animation:
                await user_client.send_animation(dest, path, caption=caption)
            elif msg.audio:
                await user_client.send_audio(
                    dest,
                    path,
                    caption=caption,
                    duration=msg.audio.duration,
                    performer=msg.audio.performer,
                    title=msg.audio.title,
                )
            elif msg.voice:
                await user_client.send_voice(
                    dest, path, caption=caption, duration=msg.voice.duration
                )
            elif msg.video_note:
                await user_client.send_video_note(
                    dest, path, duration=msg.video_note.duration
                )
            elif msg.sticker:
                await user_client.send_sticker(dest, path)
            elif msg.document:
                await user_client.send_document(
                    dest, path, caption=caption,
                    file_name=msg.document.file_name,
                )
            else:
                await user_client.send_document(dest, path, caption=caption)
            return True
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
        return False
    except Exception:
        return False
