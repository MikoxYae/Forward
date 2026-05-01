import asyncio
import os
import re
import time

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup
from pyrogram.errors import FloodWait

from config import APP_ID, API_HASH
from database.db import db


HTML = enums.ParseMode.HTML

# Per-user forward task state
forward_state: dict[int, dict] = {}


# --------------- Force-subscribe detection ---------------
def _is_force_sub_msg(msg: Message) -> bool:
    """Return True if this message looks like a bot's force-subscribe gate.

    Detection: text/caption has join-related keywords AND the inline keyboard
    contains at least one button with a t.me invite link.
    """
    text = (msg.text or msg.caption or "").lower()
    join_words = ("join", "subscribe", "channel", "group", "member",
                  "access", "unlock", "watch", "view")
    if not any(w in text for w in join_words):
        return False
    kb = getattr(msg, "reply_markup", None)
    if not isinstance(kb, InlineKeyboardMarkup):
        return False
    for row in kb.inline_keyboard:
        for btn in row:
            url = getattr(btn, "url", None) or ""
            if "t.me/+" in url or "joinchat" in url:
                return True
    return False


# --------------- Link parsing ---------------
# Private channel:  https://t.me/c/<internal_id>/<msg_id>[-<msg_id>]
# Public channel:   https://t.me/<username>/<msg_id>[-<msg_id>]
# Bot chat:         https://t.me/bot/<bot_username>/<msg_id>[-<msg_id>]
PRIVATE_RE = re.compile(r"https?://t\.me/c/(\d+)/(\d+)(?:[-/](\d+))?/?$")
PUBLIC_RE  = re.compile(r"https?://t\.me/([a-zA-Z][\w\d_]{3,})/(\d+)(?:[-/](\d+))?/?$")
BOT_RE     = re.compile(r"https?://t\.me/bot/([a-zA-Z][\w\d_]{3,})/(\d+)(?:[-/](\d+))?/?$")


def parse_link(url: str):
    """Return (chat_id_or_username, start_id, end_id, is_bot_chat) or None."""
    url = url.strip()

    m = BOT_RE.match(url)
    if m:
        username = m.group(1)
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        return username, start, end, True

    m = PRIVATE_RE.match(url)
    if m:
        chat = int("-100" + m.group(1))
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        return chat, start, end, False

    m = PUBLIC_RE.match(url)
    if m:
        chat = m.group(1)
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        return chat, start, end, False

    return None


def _resolve_dest(dest_raw: str):
    try:
        return int(dest_raw)
    except (ValueError, TypeError):
        return dest_raw


def _bold_caption(msg: Message) -> str | None:
    if not msg.caption:
        return None
    return f"<b>{msg.caption.html}</b>"


# --------------- Core forward loop (shared by /forward and /batch) ---------------
async def _run_forward(
    bot: Client,
    message: Message,
    user_id: int,
    src,
    start_id: int,
    end_id: int,
    dest,
    is_bot_chat: bool = False,
    label: str = "ғᴏʀᴡᴀʀᴅ",
):
    total = end_id - start_id + 1
    forward_state[user_id] = {"cancel": False}

    mode_note = " <b>(ʙᴏᴛ ᴄʜᴀᴛ)</b>" if is_bot_chat else ""
    status = await message.reply_text(
        f"<b>sᴛᴀʀᴛɪɴɢ {label}</b>{mode_note}\n"
        f"<b>sᴏᴜʀᴄᴇ:</b> <code>{src}</code>\n"
        f"<b>ᴅᴇsᴛɪɴᴀᴛɪᴏɴ:</b> <code>{dest}</code>\n"
        f"<b>ʀᴀɴɢᴇ:</b> <code>{start_id}</code> <b>ᴛᴏ</b> <code>{end_id}</code> "
        f"(<code>{total}</code> <b>ᴍᴇssᴀɢᴇs</b>)\n\n"
        f"<b>ᴜsᴇ /stop ᴛᴏ ᴄᴀɴᴄᴇʟ.</b>",
        parse_mode=HTML,
    )

    session_string = await db.get_session(user_id)
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
            f"<b>ғᴀɪʟᴇᴅ ᴛᴏ sᴛᴀʀᴛ sᴇssɪᴏɴ:</b> <code>{e}</code>",
            parse_mode=HTML,
        )

    try:
        user_client.parse_mode = HTML
    except Exception:
        pass

    # For bot chats: resolve bot username to chat_id via user client
    fetch_from = src
    if is_bot_chat:
        try:
            bot_chat = await user_client.get_users(src)
            fetch_from = bot_chat.id
        except Exception:
            fetch_from = src

    ok = fail = skip = 0
    seen_groups: set[str] = set()
    last_edit = 0.0

    try:
        for msg_id in range(start_id, end_id + 1):
            if forward_state.get(user_id, {}).get("cancel"):
                break

            try:
                msg = await user_client.get_messages(fetch_from, msg_id)
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                try:
                    msg = await user_client.get_messages(fetch_from, msg_id)
                except Exception:
                    fail += 1
                    continue
            except Exception:
                fail += 1
                continue

            if not msg or getattr(msg, "empty", False) or msg.service:
                skip += 1
                continue

            # Bot chat: skip messages sent BY the user (outgoing = commands/queries)
            if is_bot_chat and getattr(msg, "outgoing", False):
                skip += 1
                continue

            # Bot chat: skip force-subscribe gate messages
            if is_bot_chat and _is_force_sub_msg(msg):
                skip += 1
                continue

            if msg.media_group_id:
                if msg.media_group_id in seen_groups:
                    continue
                seen_groups.add(msg.media_group_id)
                if await _send_media_group(user_client, fetch_from, msg.id, dest):
                    ok += 1
                else:
                    fail += 1
            else:
                if await _send_one(user_client, msg, dest):
                    ok += 1
                else:
                    fail += 1

            # Fast forwarding — minimal delay, only sleep if needed
            await asyncio.sleep(0.2)

            now = time.time()
            if now - last_edit > 4:
                try:
                    await status.edit_text(
                        f"<b>{label}ɪɴɢ...</b>\n"
                        f"<b>ᴘʀᴏɢʀᴇss:</b> <code>{msg_id - start_id + 1}/{total}</code>\n"
                        f"<b>ᴏᴋ:</b> <code>{ok}</code> <b>|</b> "
                        f"<b>ғᴀɪʟᴇᴅ:</b> <code>{fail}</code> <b>|</b> "
                        f"<b>sᴋɪᴘᴘᴇᴅ:</b> <code>{skip}</code>",
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
        f"<b>✅ ᴅᴏɴᴇ</b>\n"
        f"<b>ᴏᴋ:</b> <code>{ok}</code> <b>|</b> "
        f"<b>ғᴀɪʟᴇᴅ:</b> <code>{fail}</code> <b>|</b> "
        f"<b>sᴋɪᴘᴘᴇᴅ:</b> <code>{skip}</code>",
        parse_mode=HTML,
    )


# --------------- /forward command ---------------
@Client.on_message(filters.command("forward") & filters.private)
async def forward_cmd(bot: Client, message: Message):
    user_id = message.from_user.id

    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/forward &lt;link&gt;</code>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇs:</b>\n"
            "<code>/forward https://t.me/c/1234567890/2-100</code>\n"
            "<code>/forward https://t.me/channelname/5-50</code>\n"
            "<code>/forward https://t.me/bot/save_restrict_1bot/8628</code>\n"
            "<code>/forward https://t.me/bot/save_restrict_1bot/8628-8650</code>",
            parse_mode=HTML,
        )

    if forward_state.get(user_id):
        return await message.reply_text(
            "<b>ᴀ ᴛᴀsᴋ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ. ᴜsᴇ /stop ᴛᴏ ᴄᴀɴᴄᴇʟ ɪᴛ ғɪʀsᴛ.</b>",
            parse_mode=HTML,
        )

    session_string = await db.get_session(user_id)
    if not session_string:
        return await message.reply_text(
            "<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ʟᴏɢɢᴇᴅ ɪɴ. ᴜsᴇ /login ғɪʀsᴛ.</b>",
            parse_mode=HTML,
        )

    dest_raw = await db.get_user_setting(user_id, "destination")
    if not dest_raw:
        return await message.reply_text(
            "<b>ᴅᴇsᴛɪɴᴀᴛɪᴏɴ ɪs ɴᴏᴛ sᴇᴛ. ᴜsᴇ /settings → sᴇᴛ ᴅᴇsᴛ.</b>",
            parse_mode=HTML,
        )

    parsed = parse_link(message.command[1])
    if not parsed:
        return await message.reply_text(
            "<b>ɪɴᴠᴀʟɪᴅ ʟɪɴᴋ.</b>\n\n"
            "<b>sᴜᴘᴘᴏʀᴛᴇᴅ ғᴏʀᴍᴀᴛs:</b>\n"
            "<code>https://t.me/c/&lt;id&gt;/&lt;start&gt;-&lt;end&gt;</code>\n"
            "<code>https://t.me/&lt;username&gt;/&lt;start&gt;-&lt;end&gt;</code>\n"
            "<code>https://t.me/bot/&lt;botusername&gt;/&lt;msgid&gt;</code>",
            parse_mode=HTML,
        )

    src, start_id, end_id, is_bot = parsed
    if end_id < start_id:
        start_id, end_id = end_id, start_id

    dest = _resolve_dest(dest_raw)
    await _run_forward(bot, message, user_id, src, start_id, end_id, dest, is_bot)


# --------------- /batch command ---------------
@Client.on_message(filters.command("batch") & filters.private)
async def batch_cmd(bot: Client, message: Message):
    user_id = message.from_user.id

    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/batch &lt;link&gt;</code>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇs:</b>\n"
            "<code>/batch https://t.me/bot/save_restrict_1bot/8628-8650</code>\n"
            "<code>/batch https://t.me/c/1234567890/10-200</code>\n"
            "<code>/batch https://t.me/channelname/1-500</code>\n\n"
            "<b>ɴᴏᴛᴇ:</b> ʟᴏɢɪɴ ʀᴇǫᴜɪʀᴇᴅ ғᴏʀ ʙᴏᴛ ᴄʜᴀᴛ ᴍᴇssᴀɢᴇs.\n"
            "<b>ᴛɪᴘ:</b> ᴜsᴇ ᴘʟᴜs ᴍᴇssᴇɴɢᴇʀ ᴛᴏ ɢᴇᴛ ʙᴏᴛ ᴄʜᴀᴛ ᴍᴇssᴀɢᴇ ɪᴅs.",
            parse_mode=HTML,
        )

    if forward_state.get(user_id):
        return await message.reply_text(
            "<b>ᴀ ᴛᴀsᴋ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ. ᴜsᴇ /stop ᴛᴏ ᴄᴀɴᴄᴇʟ ɪᴛ ғɪʀsᴛ.</b>",
            parse_mode=HTML,
        )

    session_string = await db.get_session(user_id)
    if not session_string:
        return await message.reply_text(
            "<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ʟᴏɢɢᴇᴅ ɪɴ. ᴜsᴇ /login ғɪʀsᴛ.</b>",
            parse_mode=HTML,
        )

    # Batch has its own destination; falls back to the shared forward destination.
    dest_raw = await db.get_user_setting(user_id, "batch_dest")
    if not dest_raw:
        dest_raw = await db.get_user_setting(user_id, "destination")
    if not dest_raw:
        return await message.reply_text(
            "<b>ʙᴀᴛᴄʜ ᴅᴇsᴛɪɴᴀᴛɪᴏɴ ɪs ɴᴏᴛ sᴇᴛ.</b>\n"
            "<b>ᴜsᴇ /settings → 📦 ʙᴀᴛᴄʜ ᴅᴇsᴛ ᴛᴏ sᴇᴛ ɪᴛ.</b>",
            parse_mode=HTML,
        )

    parsed = parse_link(message.command[1])
    if not parsed:
        return await message.reply_text(
            "<b>ɪɴᴠᴀʟɪᴅ ʟɪɴᴋ.</b>\n\n"
            "<b>sᴜᴘᴘᴏʀᴛᴇᴅ ғᴏʀᴍᴀᴛs:</b>\n"
            "<code>https://t.me/bot/&lt;botusername&gt;/&lt;start&gt;-&lt;end&gt;</code>\n"
            "<code>https://t.me/c/&lt;id&gt;/&lt;start&gt;-&lt;end&gt;</code>\n"
            "<code>https://t.me/&lt;username&gt;/&lt;start&gt;-&lt;end&gt;</code>",
            parse_mode=HTML,
        )

    src, start_id, end_id, is_bot = parsed
    if end_id < start_id:
        start_id, end_id = end_id, start_id

    dest = _resolve_dest(dest_raw)
    await _run_forward(bot, message, user_id, src, start_id, end_id, dest, is_bot, label="ʙᴀᴛᴄʜ")


# --------------- /stop command ---------------
@Client.on_message(filters.command("stop") & filters.private)
async def stop_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in forward_state:
        return await message.reply_text(
            "<b>ɴᴏ ᴀᴄᴛɪᴠᴇ ᴛᴀsᴋ.</b>",
            parse_mode=HTML,
        )
    forward_state[user_id]["cancel"] = True
    await message.reply_text(
        "<b>ᴄᴀɴᴄᴇʟʟɪɴɢ...</b>",
        parse_mode=HTML,
    )


# --------------- Internals ---------------
async def _send_one(user_client: Client, msg: Message, dest) -> bool:
    bold = _bold_caption(msg)

    for attempt in range(2):
        try:
            await msg.copy(dest, caption=bold, parse_mode=HTML)
            return True
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception:
            break

    return await _download_reupload(user_client, msg, dest)


async def _send_media_group(user_client: Client, src, anchor_id: int, dest) -> bool:
    try:
        group = await user_client.get_media_group(src, anchor_id)
        captions = [
            f"<b>{item.caption.html}</b>" if item.caption else ""
            for item in group
        ]
    except Exception:
        group = []
        captions = None

    for attempt in range(2):
        try:
            await user_client.copy_media_group(dest, src, anchor_id, captions=captions)
            return True
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception:
            break

    any_ok = False
    for item in group:
        if await _download_reupload(user_client, item, dest):
            any_ok = True
        await asyncio.sleep(0.2)
    return any_ok


async def _upload_file(user_client: Client, msg: Message, dest, path: str, caption) -> bool:
    """Upload a local file to dest. Handles FloodWait with one retry."""
    async def _do_upload():
        if msg.photo:
            return await user_client.send_photo(dest, path, caption=caption, parse_mode=HTML)
        if msg.video:
            return await user_client.send_video(
                dest, path, caption=caption, parse_mode=HTML,
                duration=msg.video.duration, width=msg.video.width, height=msg.video.height,
            )
        if msg.animation:
            return await user_client.send_animation(dest, path, caption=caption, parse_mode=HTML)
        if msg.audio:
            return await user_client.send_audio(
                dest, path, caption=caption, parse_mode=HTML,
                duration=msg.audio.duration, performer=msg.audio.performer, title=msg.audio.title,
            )
        if msg.voice:
            return await user_client.send_voice(
                dest, path, caption=caption, parse_mode=HTML, duration=msg.voice.duration,
            )
        if msg.video_note:
            return await user_client.send_video_note(dest, path, duration=msg.video_note.duration)
        if msg.sticker:
            return await user_client.send_sticker(dest, path)
        if msg.document:
            return await user_client.send_document(
                dest, path, caption=caption, parse_mode=HTML, file_name=msg.document.file_name,
            )
        return await user_client.send_document(dest, path, caption=caption, parse_mode=HTML)

    for attempt in range(2):
        try:
            await _do_upload()
            return True
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception:
            return False
    return False


async def _download_reupload(user_client: Client, msg: Message, dest) -> bool:
    try:
        # Text-only messages (no media, no download needed)
        if msg.text and not msg.media:
            for attempt in range(2):
                try:
                    await user_client.send_message(
                        dest,
                        f"<b>{msg.text.html}</b>",
                        parse_mode=HTML,
                        disable_web_page_preview=True,
                    )
                    return True
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                except Exception:
                    return False
            return False

        caption = _bold_caption(msg)
        path = await user_client.download_media(msg)
        if not path:
            return False

        try:
            return await _upload_file(user_client, msg, dest, path, caption)
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
