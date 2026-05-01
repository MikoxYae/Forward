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

# Fetch this many message IDs per API call (Telegram max = 200)
FETCH_BATCH = 200

# Per-user running task: {user_id: {cancel, ok, fail, skip, processed, total, src, dest}}
forward_state: dict[int, dict] = {}

# --------------- Link parsing ---------------
# Private channel  : https://t.me/c/<id>/<start>[-<end>]
# Public channel   : https://t.me/<username>/<start>[-<end>]
# Bot direct link  : https://t.me/bot/<username>/<start>[-<end>]
PRIVATE_RE = re.compile(r"https?://t\.me/c/(\d+)/(\d+)(?:[-/](\d+))?/?$")
BOT_RE     = re.compile(r"https?://t\.me/bot/([a-zA-Z][\w\d_]{3,})/(\d+)(?:[-/](\d+))?/?$")
PUBLIC_RE  = re.compile(r"https?://t\.me/([a-zA-Z][\w\d_]{3,})/(\d+)(?:[-/](\d+))?/?$")

def parse_link(url: str):
    url = url.strip()
    m = PRIVATE_RE.match(url)
    if m:
        return int("-100" + m.group(1)), int(m.group(2)), int(m.group(3) or m.group(2))
    m = BOT_RE.match(url)          # must be before PUBLIC_RE
    if m:
        return m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
    m = PUBLIC_RE.match(url)
    if m:
        return m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
    return None

def _resolve_dest(raw: str):
    try:
        return int(raw)
    except (ValueError, TypeError):
        return raw

def _bold_caption(msg: Message) -> str | None:
    return f"<b>{msg.caption.html}</b>" if msg.caption else None

def _sender_username(msg: Message) -> str | None:
    if msg.from_user and msg.from_user.username:
        return msg.from_user.username.lower()
    if msg.sender_chat and msg.sender_chat.username:
        return msg.sender_chat.username.lower()
    return None

def _sender_id(msg: Message) -> int | None:
    if msg.from_user:
        return msg.from_user.id
    if msg.sender_chat:
        return msg.sender_chat.id
    return None

def _sender_ok(msg: Message, src_uname: str | None, src_id: int | None) -> bool:
    # Private numeric channel — every message belongs to it
    if src_id is not None and src_uname is None:
        return True
    mu = _sender_username(msg)
    mi = _sender_id(msg)
    if src_uname and mu:
        return mu == src_uname
    if src_id and mi:
        return mi == src_id
    return True


# --------------- /status ---------------
@Client.on_message(filters.command("status") & filters.private)
async def status_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    state = forward_state.get(user_id)
    if not state:
        return await message.reply_text(
            "ℹ️ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ᴛᴀsᴋ ʀɪɢʜᴛ ɴᴏᴡ.</b>",
            parse_mode=HTML,
        )
    processed = state.get("processed", 0)
    total     = state.get("total", 0)
    ok        = state.get("ok", 0)
    fail      = state.get("fail", 0)
    skip      = state.get("skip", 0)
    src       = state.get("src", "?")
    dest      = state.get("dest", "?")
    pct       = round(processed / total * 100, 1) if total else 0
    await message.reply_text(
        f"📊 <b>ᴄᴜʀʀᴇɴᴛ ᴛᴀsᴋ sᴛᴀᴛᴜs</b>\n\n"
        f"📥 <b>sᴏᴜʀᴄᴇ:</b> <code>{src}</code>\n"
        f"📤 <b>ᴅᴇsᴛ:</b> <code>{dest}</code>\n\n"
        f"⏳ <b>ᴘʀᴏɢʀᴇss:</b> <code>{processed}/{total}</code> (<code>{pct}%</code>)\n"
        f"✅ <b>sᴇɴᴛ:</b> <code>{ok}</code>\n"
        f"❌ <b>ғᴀɪʟ:</b> <code>{fail}</code>\n"
        f"⏭ <b>sᴋɪᴘ:</b> <code>{skip}</code>\n\n"
        f"<b>sᴇɴᴅ /stop ᴛᴏ ᴄᴀɴᴄᴇʟ.</b>",
        parse_mode=HTML,
    )


# --------------- /stop ---------------
@Client.on_message(filters.command("stop") & filters.private)
async def stop_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in forward_state:
        return await message.reply_text("ℹ️ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ᴛᴀsᴋ.</b>", parse_mode=HTML)
    forward_state[user_id]["cancel"] = True
    await message.reply_text("🛑 <b>ᴄᴀɴᴄᴇʟʟɪɴɢ...</b>", parse_mode=HTML)


# --------------- Shared handler (/forward + /batch) ---------------
async def _run_forward(bot: Client, message: Message, cmd_name: str):
    user_id = message.from_user.id

    if len(message.command) < 2:
        return await message.reply_text(
            f"⚡ <b>ᴜsᴀɢᴇ:</b> <code>/{cmd_name} &lt;link&gt;</code>\n\n"
            "📌 <b>sᴜᴘᴘᴏʀᴛᴇᴅ ʟɪɴᴋs:</b>\n"
            "<code>https://t.me/c/1234567890/2-100</code>\n"
            "<code>https://t.me/channelname/5-50</code>\n"
            "<code>https://t.me/bot/Basic_need2bot/102130-134653</code>",
            parse_mode=HTML,
        )

    if forward_state.get(user_id):
        return await message.reply_text(
            "⚠️ <b>ᴀ ᴛᴀsᴋ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ.</b>\n"
            "<b>sᴇɴᴅ /status ᴛᴏ ᴄʜᴇᴄᴋ ᴘʀᴏɢʀᴇss ᴏʀ /stop ᴛᴏ ᴄᴀɴᴄᴇʟ.</b>",
            parse_mode=HTML,
        )

    session_string = await db.get_session(user_id)
    if not session_string:
        return await message.reply_text(
            "🔐 <b>ɴᴏᴛ ʟᴏɢɢᴇᴅ ɪɴ. ᴜsᴇ /login ғɪʀsᴛ.</b>", parse_mode=HTML)

    dest_raw = await db.get_user_setting(user_id, "destination")
    if not dest_raw:
        return await message.reply_text(
            "📭 <b>ᴅᴇsᴛɪɴᴀᴛɪᴏɴ ɴᴏᴛ sᴇᴛ. ᴜsᴇ /setdest &lt;ᴄʜᴀɴɴᴇʟ&gt;.</b>",
            parse_mode=HTML)

    parsed = parse_link(message.command[1])
    if not parsed:
        return await message.reply_text(
            "❌ <b>ɪɴᴠᴀʟɪᴅ ʟɪɴᴋ.</b>\n\n"
            "📌 <b>sᴜᴘᴘᴏʀᴛᴇᴅ ғᴏʀᴍᴀᴛs:</b>\n"
            "<code>https://t.me/c/&lt;id&gt;/&lt;start&gt;-&lt;end&gt;</code>\n"
            "<code>https://t.me/&lt;username&gt;/&lt;start&gt;-&lt;end&gt;</code>\n"
            "<code>https://t.me/bot/&lt;username&gt;/&lt;start&gt;-&lt;end&gt;</code>",
            parse_mode=HTML)

    src, start_id, end_id = parsed
    if end_id < start_id:
        start_id, end_id = end_id, start_id

    dest  = _resolve_dest(dest_raw)
    total = end_id - start_id + 1

    src_uname: str | None = src if isinstance(src, str) else None
    src_id:    int | None = src if isinstance(src, int) else None

    # Initialise state — /status reads from here
    forward_state[user_id] = {
        "cancel":    False,
        "ok":        0,
        "fail":      0,
        "skip":      0,
        "processed": 0,
        "total":     total,
        "src":       src,
        "dest":      dest,
    }

    status_msg = await message.reply_text(
        f"🚀 <b>sᴛᴀʀᴛɪɴɢ...</b>\n"
        f"📥 <b>sʀᴄ:</b> <code>{src}</code>\n"
        f"📤 <b>ᴅsᴛ:</b> <code>{dest}</code>\n"
        f"🔢 <b>ʀᴀɴɢᴇ:</b> <code>{start_id}</code> → <code>{end_id}</code> "
        f"(<code>{total}</code> <b>ᴍsɢs</b>)\n\n"
        f"💡 <b>/status ᴛᴏ ᴄʜᴇᴄᴋ ᴀɴʏᴛɪᴍᴇ · /stop ᴛᴏ ᴄᴀɴᴄᴇʟ</b>",
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
        return await status_msg.edit_text(
            f"❌ <b>sᴇssɪᴏɴ ᴇʀʀᴏʀ:</b> <code>{e}</code>", parse_mode=HTML)

    try:
        user_client.parse_mode = HTML
    except Exception:
        pass

    state       = forward_state[user_id]
    seen_groups : set[str] = set()
    last_edit   = 0.0
    all_ids     = list(range(start_id, end_id + 1))

    try:
        # ── STEP: fetch FETCH_BATCH IDs → send all → fetch next batch ──
        for chunk_start in range(0, len(all_ids), FETCH_BATCH):

            if state.get("cancel"):
                break

            chunk = all_ids[chunk_start : chunk_start + FETCH_BATCH]

            # ── 1. Fetch this chunk (one API call for up to 200 IDs) ──
            try:
                msgs = await user_client.get_messages(src, chunk)
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
                try:
                    msgs = await user_client.get_messages(src, chunk)
                except Exception:
                    state["fail"]      += len(chunk)
                    state["processed"] += len(chunk)
                    continue
            except Exception:
                state["fail"]      += len(chunk)
                state["processed"] += len(chunk)
                continue

            if isinstance(msgs, Message):
                msgs = [msgs]

            # ── 2. Send every message in this chunk to destination ──
            for msg in msgs:
                if state.get("cancel"):
                    break

                state["processed"] += 1

                if not msg or getattr(msg, "empty", False) or msg.service:
                    state["skip"] += 1
                    continue

                if not _sender_ok(msg, src_uname, src_id):
                    state["skip"] += 1
                    continue

                if msg.media_group_id:
                    if msg.media_group_id in seen_groups:
                        continue
                    seen_groups.add(msg.media_group_id)
                    if await _send_media_group(user_client, src, msg.id, dest):
                        state["ok"] += 1
                    else:
                        state["fail"] += 1
                else:
                    if await _send_one(user_client, msg, dest):
                        state["ok"] += 1
                    else:
                        state["fail"] += 1

                await asyncio.sleep(0.5)

                # Update status message every 5 seconds
                now = time.time()
                if now - last_edit > 5:
                    pct = round(state["processed"] / total * 100, 1)
                    try:
                        await status_msg.edit_text(
                            f"⏳ <b>ᴘʀᴏɢʀᴇss:</b> <code>{state['processed']}/{total}</code> "
                            f"(<code>{pct}%</code>)\n"
                            f"✅ <code>{state['ok']}</code> | "
                            f"❌ <code>{state['fail']}</code> | "
                            f"⏭ <code>{state['skip']}</code>",
                            parse_mode=HTML,
                        )
                    except Exception:
                        pass
                    last_edit = now

            # ── 3. Done with this chunk — move to next 200 ──

    finally:
        try:
            await user_client.stop()
        except Exception:
            pass
        ok   = state.get("ok",   0)
        fail = state.get("fail", 0)
        skip = state.get("skip", 0)
        forward_state.pop(user_id, None)

    await status_msg.edit_text(
        f"✅ <b>ᴅᴏɴᴇ!</b>\n\n"
        f"✅ <b>sᴇɴᴛ:</b>  <code>{ok}</code>\n"
        f"❌ <b>ғᴀɪʟ:</b>  <code>{fail}</code>\n"
        f"⏭ <b>sᴋɪᴘ:</b>  <code>{skip}</code>",
        parse_mode=HTML,
    )


@Client.on_message(filters.command(["forward", "batch"]) & filters.private)
async def forward_or_batch_cmd(bot: Client, message: Message):
    await _run_forward(bot, message, message.command[0].lower())


# --------------- Internals ---------------
async def _send_one(user_client: Client, msg: Message, dest) -> bool:
    bold = _bold_caption(msg)
    try:
        await msg.copy(dest, caption=bold, parse_mode=HTML)
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception:
        pass
    return await _download_reupload(user_client, msg, dest)


async def _send_media_group(user_client: Client, src, anchor_id: int, dest) -> bool:
    group: list[Message] = []
    captions = None

    try:
        group    = await user_client.get_media_group(src, anchor_id)
        captions = [
            f"<b>{item.caption.html}</b>" if item.caption else ""
            for item in group
        ]
    except Exception:
        group    = []
        captions = None

    # Try copy_media_group first (non-restricted)
    try:
        await user_client.copy_media_group(dest, src, anchor_id, captions=captions)
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception:
        pass

    # Fallback A: download each album item individually
    if group:
        any_ok = False
        for item in group:
            if await _download_reupload(user_client, item, dest):
                any_ok = True
            await asyncio.sleep(0.5)
        return any_ok

    # Fallback B: album fetch also failed — download anchor alone
    try:
        anchor_msg = await user_client.get_messages(src, anchor_id)
        if anchor_msg and not getattr(anchor_msg, "empty", False):
            return await _download_reupload(user_client, anchor_msg, dest)
    except Exception:
        pass

    return False


async def _download_reupload(user_client: Client, msg: Message, dest) -> bool:
    try:
        if msg.text and not msg.media:
            try:
                await user_client.send_message(
                    dest, f"<b>{msg.text.html}</b>",
                    parse_mode=HTML, disable_web_page_preview=True)
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
                    width=msg.video.width, height=msg.video.height)
            elif msg.animation:
                await user_client.send_animation(dest, path, caption=caption, parse_mode=HTML)
            elif msg.audio:
                await user_client.send_audio(
                    dest, path, caption=caption, parse_mode=HTML,
                    duration=msg.audio.duration,
                    performer=msg.audio.performer, title=msg.audio.title)
            elif msg.voice:
                await user_client.send_voice(
                    dest, path, caption=caption, parse_mode=HTML,
                    duration=msg.voice.duration)
            elif msg.video_note:
                await user_client.send_video_note(dest, path, duration=msg.video_note.duration)
            elif msg.sticker:
                await user_client.send_sticker(dest, path)
            elif msg.document:
                await user_client.send_document(
                    dest, path, caption=caption, parse_mode=HTML,
                    file_name=msg.document.file_name)
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
