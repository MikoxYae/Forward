import asyncio
import os
import re
import time

from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from config import APP_ID, API_HASH
from database.db import db

HTML = enums.ParseMode.HTML

# Per-user forward task state
forward_state: dict[int, dict] = {}

# --------------- Link parsing ---------------
# Private channel: https://t.me/c/<id>/<start>[-<end>]
# Public channel:  https://t.me/<username>/<start>[-<end>]
PRIVATE_RE = re.compile(r"https?://t\.me/c/(\d+)/(\d+)(?:[-/](\d+))?/?$")
PUBLIC_RE  = re.compile(r"https?://t\.me/([a-zA-Z][\w\d_]{3,})/(\d+)(?:[-/](\d+))?/?$")

def parse_link(url: str):
    """Return (chat_id_or_username, start_id, end_id) or None."""
    url = url.strip()

    m = PRIVATE_RE.match(url)
    if m:
        chat  = int("-100" + m.group(1))
        start = int(m.group(2))
        end   = int(m.group(3)) if m.group(3) else start
        return chat, start, end

    m = PUBLIC_RE.match(url)
    if m:
        chat  = m.group(1)
        start = int(m.group(2))
        end   = int(m.group(3)) if m.group(3) else start
        return chat, start, end

    return None

def _resolve_dest(dest_raw: str):
    try:
        return int(dest_raw)
    except (ValueError, TypeError):
        return dest_raw

def _bold_caption(msg: Message) -> str | None:
    """Return msg caption wrapped in <b>...</b> with HTML entities preserved,
    or None if there is no caption."""
    if not msg.caption:
        return None
    return f"<b>{msg.caption.html}</b>"

def _get_sender_username(msg: Message) -> str | None:
    """Return lowercase username of the sender, or None."""
    if msg.from_user and msg.from_user.username:
        return msg.from_user.username.lower()
    if msg.sender_chat and msg.sender_chat.username:
        return msg.sender_chat.username.lower()
    return None

def _get_sender_id(msg: Message) -> int | None:
    """Return numeric ID of the sender (user or chat)."""
    if msg.from_user:
        return msg.from_user.id
    if msg.sender_chat:
        return msg.sender_chat.id
    return None

def _sender_allowed(msg: Message, source_username: str | None, source_id: int | None) -> bool:
    """
    Return True only when the message was sent by the same entity as the
    source channel/bot we are pulling from.

    source_username — lowercased username extracted from the /forward link
                      (None for private numeric-ID channels)
    source_id       — numeric chat id of the source
                      (always set for private channels, may be None for public)
    """
    # Private channel by numeric ID — every message belongs to that channel,
    # no extra sender filter needed.
    if source_id is not None and source_username is None:
        return True

    msg_username = _get_sender_username(msg)
    msg_id       = _get_sender_id(msg)

    # Match by username first
    if source_username and msg_username:
        return msg_username == source_username

    # Fallback: match by numeric id
    if source_id and msg_id:
        return msg_id == source_id

    return True   # can't determine — let it through

# --------------- Commands ---------------
@Client.on_message(filters.command("forward") & filters.private)
async def forward_cmd(bot: Client, message: Message):
    user_id = message.from_user.id

    if len(message.command) < 2:
        return await message.reply_text(
            "⚡ <b>ᴜsᴀɢᴇ:</b> <code>/forward &lt;link&gt;</code>\n\n"
            "📌 <b>ᴇxᴀᴍᴘʟᴇs:</b>\n"
            "<code>/forward https://t.me/c/1234567890/2-100</code>\n"
            "<code>/forward https://t.me/channelname/5-50</code>\n"
            "<code>/forward https://t.me/c/1234567890/42</code>",
            parse_mode=HTML,
        )

    if forward_state.get(user_id):
        return await message.reply_text(
            "⚠️ <b>ᴀ ғᴏʀᴡᴀʀᴅ ᴛᴀsᴋ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ. ᴜsᴇ /stop ᴛᴏ ᴄᴀɴᴄᴇʟ ɪᴛ ғɪʀsᴛ.</b>",
            parse_mode=HTML,
        )

    session_string = await db.get_session(user_id)
    if not session_string:
        return await message.reply_text(
            "🔐 <b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ʟᴏɢɢᴇᴅ ɪɴ. ᴜsᴇ /login ғɪʀsᴛ.</b>",
            parse_mode=HTML,
        )

    dest_raw = await db.get_user_setting(user_id, "destination")
    if not dest_raw:
        return await message.reply_text(
            "📭 <b>ᴅᴇsᴛɪɴᴀᴛɪᴏɴ ɪs ɴᴏᴛ sᴇᴛ. ᴜsᴇ /setdest &lt;ᴄʜᴀɴɴᴇʟ&gt;.</b>",
            parse_mode=HTML,
        )

    parsed = parse_link(message.command[1])
    if not parsed:
        return await message.reply_text(
            "❌ <b>ɪɴᴠᴀʟɪᴅ ʟɪɴᴋ. ᴜsᴇ</b> "
            "<code>https://t.me/c/&lt;id&gt;/&lt;start&gt;-&lt;end&gt;</code> "
            "<b>ᴏʀ</b> <code>https://t.me/&lt;username&gt;/&lt;start&gt;-&lt;end&gt;</code>.",
            parse_mode=HTML,
        )

    src, start_id, end_id = parsed
    if end_id < start_id:
        start_id, end_id = end_id, start_id

    dest  = _resolve_dest(dest_raw)
    total = end_id - start_id + 1

    # Determine source username (for public bots/channels) and source id (for private)
    source_username: str | None = src if isinstance(src, str) else None
    source_id: int | None       = src if isinstance(src, int) else None

    forward_state[user_id] = {"cancel": False}

    status = await message.reply_text(
        f"🚀 <b>sᴛᴀʀᴛɪɴɢ ғᴏʀᴡᴀʀᴅ</b>\n"
        f"📥 <b>sᴏᴜʀᴄᴇ:</b> <code>{src}</code>\n"
        f"📤 <b>ᴅᴇsᴛɪɴᴀᴛɪᴏɴ:</b> <code>{dest}</code>\n"
        f"🔢 <b>ʀᴀɴɢᴇ:</b> <code>{start_id}</code> <b>ᴛᴏ</b> <code>{end_id}</code> "
        f"(<code>{total}</code> <b>ᴍᴇssᴀɢᴇs</b>)\n\n"
        f"⏹ <b>ᴜsᴇ /stop ᴛᴏ ᴄᴀɴᴄᴇʟ.</b>",
        parse_mode=HTML,
    )

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
        return await status.edit_text(
            f"❌ <b>ғᴀɪʟᴇᴅ ᴛᴏ sᴛᴀʀᴛ ʏᴏᴜʀ sᴇssɪᴏɴ:</b> <code>{e}</code>",
            parse_mode=HTML,
        )

    try:
        user_client.parse_mode = HTML
    except Exception:
        pass

    ok = fail = skip = 0
    seen_groups: set[str] = set()
    last_edit = 0.0

    try:
        for msg_id in range(start_id, end_id + 1):
            if forward_state.get(user_id, {}).get("cancel"):
                break

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

            # ── SENDER FILTER ──────────────────────────────────────────────
            # Skip messages that were NOT sent by the source bot/channel.
            if not _sender_allowed(msg, source_username, source_id):
                skip += 1
                continue
            # ──────────────────────────────────────────────────────────────

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

            await asyncio.sleep(1.0)

            now = time.time()
            if now - last_edit > 5:
                try:
                    await status.edit_text(
                        f"⏳ <b>ғᴏʀᴡᴀʀᴅɪɴɢ...</b>\n"
                        f"📊 <b>ᴘʀᴏɢʀᴇss:</b> <code>{msg_id - start_id + 1}/{total}</code>\n"
                        f"✅ <b>ᴏᴋ:</b> <code>{ok}</code> | "
                        f"❌ <b>ғᴀɪʟᴇᴅ:</b> <code>{fail}</code> | "
                        f"⏭ <b>sᴋɪᴘᴘᴇᴅ:</b> <code>{skip}</code>",
                        parse_mode=HTML,
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
        f"✅ <b>ᴅᴏɴᴇ</b>\n"
        f"✅ <b>ᴏᴋ:</b> <code>{ok}</code> | "
        f"❌ <b>ғᴀɪʟᴇᴅ:</b> <code>{fail}</code> | "
        f"⏭ <b>sᴋɪᴘᴘᴇᴅ:</b> <code>{skip}</code>",
        parse_mode=HTML,
    )


@Client.on_message(filters.command("stop") & filters.private)
async def stop_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in forward_state:
        return await message.reply_text(
            "ℹ️ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ғᴏʀᴡᴀʀᴅ ᴛᴀsᴋ.</b>",
            parse_mode=HTML,
        )
    forward_state[user_id]["cancel"] = True
    await message.reply_text(
        "🛑 <b>ᴄᴀɴᴄᴇʟʟɪɴɢ ᴄᴜʀʀᴇɴᴛ ғᴏʀᴡᴀʀᴅ ᴛᴀsᴋ...</b>",
        parse_mode=HTML,
    )


# --------------- Internals ---------------
async def _send_one(user_client: Client, msg: Message, dest) -> bool:
    """Try copy → download+reupload. Captions are wrapped in <b>...</b>."""
    bold = _bold_caption(msg)

    # 1) Copy (fresh send, no forward tag)
    try:
        await msg.copy(dest, caption=bold, parse_mode=HTML)
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception:
        pass

    # 2) Download + re-upload (works for restricted/protected content)
    return await _download_reupload(user_client, msg, dest)


async def _send_media_group(user_client: Client, src, anchor_id: int, dest) -> bool:
    """Copy a whole album with bold captions. Falls back to per-item download."""
    try:
        group    = await user_client.get_media_group(src, anchor_id)
        captions = [
            f"<b>{item.caption.html}</b>" if item.caption else ""
            for item in group
        ]
    except Exception:
        group    = []
        captions = None

    try:
        await user_client.copy_media_group(dest, src, anchor_id, captions=captions)
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception:
        pass

    # Fallback: download each item individually
    any_ok = False
    for item in group:
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
                    dest,
                    f"<b>{msg.text.html}</b>",
                    parse_mode=HTML,
                    disable_web_page_preview=True,
                )
                return True
            except Exception:
                return False

        caption = _bold_caption(msg)
        path    = await user_client.download_media(msg)
        if not path:
            return False

        try:
            if msg.photo:
                await user_client.send_photo(dest, path, caption=caption, parse_mode=HTML)
            elif msg.video:
                await user_client.send_video(
                    dest, path, caption=caption, parse_mode=HTML,
                    duration=msg.video.duration,
                    width=msg.video.width,
                    height=msg.video.height,
                )
            elif msg.animation:
                await user_client.send_animation(dest, path, caption=caption, parse_mode=HTML)
            elif msg.audio:
                await user_client.send_audio(
                    dest, path, caption=caption, parse_mode=HTML,
                    duration=msg.audio.duration,
                    performer=msg.audio.performer,
                    title=msg.audio.title,
                )
            elif msg.voice:
                await user_client.send_voice(
                    dest, path, caption=caption, parse_mode=HTML,
                    duration=msg.voice.duration,
                )
            elif msg.video_note:
                await user_client.send_video_note(dest, path, duration=msg.video_note.duration)
            elif msg.sticker:
                await user_client.send_sticker(dest, path)
            elif msg.document:
                await user_client.send_document(
                    dest, path, caption=caption, parse_mode=HTML,
                    file_name=msg.document.file_name,
                )
            else:
                await user_client.send_document(dest, path, caption=caption, parse_mode=HTML)
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
