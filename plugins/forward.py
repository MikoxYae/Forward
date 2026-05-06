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

# Telegram allows up to 200 IDs per messages.GetMessages call
FETCH_BATCH = 200

# Per-user running task
forward_state: dict[int, dict] = {}

# --------------- Link parsing ---------------
# t.me/c/<id>/<start>[-<end>]
# t.me/bot/<username>/<start>[-<end>]   ← bot direct link (checked BEFORE public)
# t.me/<username>/<start>[-<end>]
PRIVATE_RE = re.compile(r"https?://t\.me/c/(\d+)/(\d+)(?:[-/](\d+))?/?$")
BOT_RE     = re.compile(r"https?://t\.me/bot/([a-zA-Z][\w\d_]{3,})/(\d+)(?:[-/](\d+))?/?$")
PUBLIC_RE  = re.compile(r"https?://t\.me/([a-zA-Z][\w\d_]{3,})/(\d+)(?:[-/](\d+))?/?$")

def parse_link(url: str):
    url = url.strip()
    m = PRIVATE_RE.match(url)
    if m:
        return int("-100" + m.group(1)), int(m.group(2)), int(m.group(3) or m.group(2))
    m = BOT_RE.match(url)          # BOT_RE before PUBLIC_RE — important!
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

def _get_sender_username(msg: Message) -> str | None:
    if msg.from_user and msg.from_user.username:
        return msg.from_user.username.lower()
    if msg.sender_chat and msg.sender_chat.username:
        return msg.sender_chat.username.lower()
    return None

def _get_sender_id(msg: Message) -> int | None:
    if msg.from_user:
        return msg.from_user.id
    if msg.sender_chat:
        return msg.sender_chat.id
    return None

def _sender_ok(msg: Message, src_uname: str | None, src_id: int | None) -> bool:
    """
    True  → forward this message
    False → skip it

    Rules:
    - Private channel (numeric id, no username): always forward — every
      message in that channel belongs to it.
    - Public / bot link (username given): only forward if the message's
      sender username matches. If neither side has a username we can
      compare, let the message through (can't determine → don't block).
    """
    # Private numeric channel — no sender filter needed
    if src_id is not None and src_uname is None:
        return True

    msg_uname = _get_sender_username(msg)
    msg_id    = _get_sender_id(msg)

    # Match by username
    if src_uname and msg_uname:
        return msg_uname == src_uname

    # Fallback match by numeric id (only useful when src resolved to int)
    if src_id and msg_id:
        return msg_id == src_id

    # Can't determine sender — let it through so nothing is silently lost
    return True


# --------------- /status ---------------
@Client.on_message(filters.command("status") & filters.private)
async def status_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    state   = forward_state.get(user_id)
    if not state:
        # Check if a saved resume exists
        resume = await db.get_resume(user_id)
        if resume:
            return await message.reply_text(
                f"💾 <b>sᴀᴠᴇᴅ ʀᴇsᴜᴍᴇ ғᴏᴜɴᴅ</b>\n\n"
                f"📥 <b>sʀᴄ:</b> <code>{resume['src']}</code>\n"
                f"📤 <b>ᴅsᴛ:</b> <code>{resume['dest']}</code>\n"
                f"🔢 <b>ʀᴀɴɢᴇ:</b> <code>{resume['start_id']}</code> → <code>{resume['end_id']}</code>\n"
                f"📍 <b>ʟᴀsᴛ ᴅᴏɴᴇ:</b> <code>{resume['last_id']}</code>\n\n"
                f"<b>sᴇɴᴅ /resume ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ ғʀᴏᴍ ᴛʜᴇʀᴇ.</b>",
                parse_mode=HTML,
            )
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
        f"📊 <b>ʟɪᴠᴇ sᴛᴀᴛᴜs</b>\n\n"
        f"📥 <b>sʀᴄ:</b> <code>{src}</code>\n"
        f"📤 <b>ᴅsᴛ:</b> <code>{dest}</code>\n\n"
        f"⏳ <b>ᴘʀᴏɢʀᴇss:</b> <code>{processed}/{total}</code> (<code>{pct}%</code>)\n"
        f"✅ <b>sᴇɴᴛ:</b>   <code>{ok}</code>\n"
        f"❌ <b>ғᴀɪʟ:</b>   <code>{fail}</code>\n"
        f"⏭ <b>sᴋɪᴘ:</b>   <code>{skip}</code>\n\n"
        f"<b>/stop ᴛᴏ ᴄᴀɴᴄᴇʟ</b>",
        parse_mode=HTML,
    )


# --------------- /stop ---------------
@Client.on_message(filters.command("stop") & filters.private)
async def stop_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in forward_state:
        return await message.reply_text(
            "ℹ️ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ᴛᴀsᴋ.</b>", parse_mode=HTML)
    forward_state[user_id]["cancel"] = True
    await message.reply_text("🛑 <b>ᴄᴀɴᴄᴇʟʟɪɴɢ...</b>", parse_mode=HTML)


# --------------- /resume ---------------
@Client.on_message(filters.command("resume") & filters.private)
async def resume_cmd(bot: Client, message: Message):
    user_id = message.from_user.id

    if forward_state.get(user_id):
        return await message.reply_text(
            "⚠️ <b>ᴀ ᴛᴀsᴋ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ. /stop ɪᴛ ғɪʀsᴛ.</b>",
            parse_mode=HTML)

    resume = await db.get_resume(user_id)
    if not resume:
        return await message.reply_text(
            "ℹ️ <b>ɴᴏ sᴀᴠᴇᴅ ʀᴇsᴜᴍᴇ ғᴏᴜɴᴅ.</b>\n"
            "<b>sᴛᴀʀᴛ ᴀ ɴᴇᴡ ᴛᴀsᴋ ᴡɪᴛʜ /batch ᴏʀ /forward.</b>",
            parse_mode=HTML)

    # Build a fake message.command so _run_forward_range works
    src      = resume["src"]
    dest_raw = resume["dest"]
    start_id = resume["last_id"] + 1   # continue from after last done
    end_id   = resume["end_id"]

    if start_id > end_id:
        await db.clear_resume(user_id)
        return await message.reply_text(
            "✅ <b>ᴀʟʟ ᴍᴇssᴀɢᴇs ᴀʟʀᴇᴀᴅʏ ᴅᴏɴᴇ! ɴᴏᴛʜɪɴɢ ᴛᴏ ʀᴇsᴜᴍᴇ.</b>",
            parse_mode=HTML)

    remaining = end_id - start_id + 1
    await message.reply_text(
        f"▶️ <b>ʀᴇsᴜᴍɪɴɢ...</b>\n"
        f"📥 <b>sʀᴄ:</b> <code>{src}</code>\n"
        f"📤 <b>ᴅsᴛ:</b> <code>{dest_raw}</code>\n"
        f"📍 <b>ᴄᴏɴᴛɪɴᴜɪɴɢ ғʀᴏᴍ:</b> <code>{start_id}</code> → <code>{end_id}</code>\n"
        f"(<code>{remaining}</code> <b>ʀᴇᴍᴀɪɴɪɴɢ</b>)",
        parse_mode=HTML,
    )

    await _run_forward_range(bot, message, src, dest_raw, start_id, end_id)


# --------------- /forward + /batch ---------------
@Client.on_message(filters.command(["forward", "batch"]) & filters.private)
async def forward_or_batch_cmd(bot: Client, message: Message):
    user_id = message.from_user.id

    if len(message.command) < 2:
        cmd = message.command[0].lower()
        return await message.reply_text(
            f"⚡ <b>ᴜsᴀɢᴇ:</b> <code>/{cmd} &lt;link&gt;</code>\n\n"
            "📌 <b>sᴜᴘᴘᴏʀᴛᴇᴅ ʟɪɴᴋs:</b>\n"
            "<code>https://t.me/c/1234567890/2-100</code>\n"
            "<code>https://t.me/channelname/5-50</code>\n"
            "<code>https://t.me/bot/Basic_need2bot/102130-134653</code>",
            parse_mode=HTML)

    if forward_state.get(user_id):
        return await message.reply_text(
            "⚠️ <b>ᴀ ᴛᴀsᴋ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ.</b>\n"
            "<b>/status ᴛᴏ ᴄʜᴇᴄᴋ · /stop ᴛᴏ ᴄᴀɴᴄᴇʟ</b>",
            parse_mode=HTML)

    parsed = parse_link(message.command[1])
    if not parsed:
        return await message.reply_text(
            "❌ <b>ɪɴᴠᴀʟɪᴅ ʟɪɴᴋ.</b>\n\n"
            "📌 <b>sᴜᴘᴘᴏʀᴛᴇᴅ:</b>\n"
            "<code>https://t.me/c/&lt;id&gt;/&lt;start&gt;-&lt;end&gt;</code>\n"
            "<code>https://t.me/&lt;username&gt;/&lt;start&gt;-&lt;end&gt;</code>\n"
            "<code>https://t.me/bot/&lt;username&gt;/&lt;start&gt;-&lt;end&gt;</code>",
            parse_mode=HTML)

    src, start_id, end_id = parsed
    if end_id < start_id:
        start_id, end_id = end_id, start_id

    cmd = message.command[0].lower()
    if cmd == "batch":
        dest_raw = await db.get_user_setting(user_id, "batch_dest") or \
                   await db.get_user_setting(user_id, "destination")
    else:
        dest_raw = await db.get_user_setting(user_id, "destination")

    if not dest_raw:
        return await message.reply_text(
            "📭 <b>ᴅᴇsᴛɪɴᴀᴛɪᴏɴ ɴᴏᴛ sᴇᴛ.</b>\n"
            "<b>ᴜsᴇ /setdest ᴏʀ ᴏᴘᴇɴ /settings ᴘᴀɴᴇʟ.</b>",
            parse_mode=HTML)

    await _run_forward_range(bot, message, src, dest_raw, start_id, end_id)


# --------------- Core engine ---------------
async def _run_forward_range(bot: Client, message: Message,
                              src, dest_raw: str,
                              start_id: int, end_id: int):
    user_id = message.from_user.id

    session_string = await db.get_session(user_id)
    if not session_string:
        return await message.reply_text(
            "🔐 <b>ɴᴏᴛ ʟᴏɢɢᴇᴅ ɪɴ. ᴜsᴇ /login ғɪʀsᴛ.</b>",
            parse_mode=HTML)

    dest  = _resolve_dest(dest_raw)
    total = end_id - start_id + 1

    src_uname: str | None = src if isinstance(src, str) else None
    src_id:    int | None = src if isinstance(src, int) else None

    forward_state[user_id] = {
        "cancel":      False,
        "ok":          0,
        "fail":        0,
        "skip":        0,
        "processed":   0,
        "total":       total,
        "src":         str(src),
        "dest":        str(dest),
        "first_error": None,
    }
    state = forward_state[user_id]

    status_msg = await message.reply_text(
        f"🚀 <b>sᴛᴀʀᴛɪɴɢ...</b>\n"
        f"📥 <b>sʀᴄ:</b> <code>{src}</code>\n"
        f"📤 <b>ᴅsᴛ:</b> <code>{dest}</code>\n"
        f"🔢 <b>ʀᴀɴɢᴇ:</b> <code>{start_id}</code> → <code>{end_id}</code> "
        f"(<code>{total}</code> <b>ᴍsɢs</b>)\n\n"
        f"💡 <b>/status · /stop</b>",
        parse_mode=HTML,
    )

    user_client = Client(
        name=f"user_{user_id}",
        api_id=APP_ID, api_hash=API_HASH,
        session_string=session_string,
        in_memory=True,
    )
    try:
        await user_client.start()
    except Exception as e:
        forward_state.pop(user_id, None)
        return await status_msg.edit_text(
            f"❌ <b>sᴇssɪᴏɴ ᴇʀʀᴏʀ:</b> <code>{e}</code>\n\n"
            f"<b>ᴛʀʏ /logout ᴀɴᴅ /login ᴀɢᴀɪɴ.</b>",
            parse_mode=HTML)

    try:
        user_client.parse_mode = HTML
    except Exception:
        pass

    # ── PEER RESOLVE: in-memory sessions have empty peer cache ──
    # For private channels (int IDs), Pyrogram needs access_hash which
    # is only known after the peer appears in dialogs. Iterate until found.
    if isinstance(src, int):
        try:
            await status_msg.edit_text(
                f"🔍 <b>ʀᴇsᴏʟᴠɪɴɢ ᴄʜᴀɴɴᴇʟ ᴘᴇᴇʀ...</b>\n"
                f"<i>(ᴏɴʟʏ ɴᴇᴇᴅᴇᴅ ᴏɴᴄᴇ ᴘᴇʀ sᴇssɪᴏɴ)</i>",
                parse_mode=HTML,
            )
        except Exception:
            pass
        peer_resolved = False
        try:
            # Try direct resolve first (works if peer was already seen)
            await user_client.get_chat(src)
            peer_resolved = True
        except Exception:
            pass

        if not peer_resolved:
            # Walk dialogs until we find the channel and cache its access_hash
            try:
                async for dialog in user_client.iter_dialogs():
                    if dialog.chat.id == src:
                        peer_resolved = True
                        break
            except Exception:
                pass

        if not peer_resolved:
            forward_state.pop(user_id, None)
            try:
                await user_client.stop()
            except Exception:
                pass
            return await status_msg.edit_text(
                f"❌ <b>ᴄʜᴀɴɴᴇʟ ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ</b>\n\n"
                f"🔑 <b>ʏᴏᴜʀ ʟᴏɢɢᴇᴅ-ɪɴ ᴀᴄᴄᴏᴜɴᴛ ɪs ɴᴏᴛ ᴀ ᴍᴇᴍʙᴇʀ ᴏғ ᴛʜᴀᴛ ᴄʜᴀɴɴᴇʟ.</b>\n"
                f"ᴊᴏɪɴ ɪᴛ ɪɴ ᴛᴇʟᴇɢʀᴀᴍ ᴡɪᴛʜ ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ, ᴛʜᴇɴ ʀᴇᴛʀʏ.\n\n"
                f"⚠️ <b>ʙᴏᴛ ᴅᴏᴇs ɴᴏᴛ ɴᴇᴇᴅ ᴛᴏ ʙᴇ ᴀᴅᴍɪɴ ɪɴ sᴏᴜʀᴄᴇ.</b>",
                parse_mode=HTML,
            )

    # ── PRE-FLIGHT: verify we can actually read from source ──
    try:
        test_msg = await user_client.get_messages(src, start_id)
        if test_msg is None or getattr(test_msg, "empty", False):
            pass  # empty message is fine — channel is accessible
    except Exception as e:
        forward_state.pop(user_id, None)
        try:
            await user_client.stop()
        except Exception:
            pass
        err_name = type(e).__name__
        hint = (
            "🔑 <b>ʏᴏᴜʀ ʟᴏɢɢᴇᴅ-ɪɴ ᴀᴄᴄᴏᴜɴᴛ ᴄᴀɴɴᴏᴛ ʀᴇᴀᴅ ᴛʜɪs ᴄʜᴀɴɴᴇʟ.</b>\n"
            "ᴍᴀᴋᴇ sᴜʀᴇ ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ ɪs ᴀ ᴍᴇᴍʙᴇʀ, ᴛʜᴇɴ ʀᴇᴛʀʏ.\n\n"
            "⚠️ <b>ʙᴏᴛ ᴅᴏᴇs ɴᴏᴛ ɴᴇᴇᴅ ᴛᴏ ʙᴇ ᴀᴅᴍɪɴ ɪɴ sᴏᴜʀᴄᴇ.</b>"
            if "Admin" in err_name or "Private" in err_name or "Forbidden" in err_name
            else f"<code>{err_name}: {e}</code>"
        )
        return await status_msg.edit_text(
            f"❌ <b>sᴏᴜʀᴄᴇ ʀᴇᴀᴅ ᴇʀʀᴏʀ</b> (<code>{err_name}</code>)\n\n{hint}",
            parse_mode=HTML,
        )

    seen_groups: set[str] = set()
    last_edit   = 0.0
    last_saved_id = start_id - 1
    all_ids     = list(range(start_id, end_id + 1))

    try:
        for chunk_start in range(0, len(all_ids), FETCH_BATCH):
            if state.get("cancel"):
                break

            chunk = all_ids[chunk_start : chunk_start + FETCH_BATCH]

            # ── STEP 1: Fetch this batch (1 API call for up to 200 IDs) ──
            try:
                msgs = await user_client.get_messages(src, chunk)
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
                try:
                    msgs = await user_client.get_messages(src, chunk)
                except Exception as e2:
                    if not state["first_error"]:
                        state["first_error"] = f"get_messages: {type(e2).__name__}: {e2}"
                    state["fail"]      += len(chunk)
                    state["processed"] += len(chunk)
                    continue
            except Exception as e:
                if not state["first_error"]:
                    state["first_error"] = f"get_messages: {type(e).__name__}: {e}"
                state["fail"]      += len(chunk)
                state["processed"] += len(chunk)
                continue

            if isinstance(msgs, Message):
                msgs = [msgs]

            # ── STEP 2: Send every message in this batch to destination ──
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
                    sent, err = await _send_media_group(user_client, src, msg.id, dest)
                else:
                    sent, err = await _send_one(user_client, msg, dest)

                if sent:
                    state["ok"] += 1
                else:
                    state["fail"] += 1
                    if err and not state["first_error"]:
                        state["first_error"] = err

                last_saved_id = msg.id
                await asyncio.sleep(0.5)

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

            # ── STEP 3: Save resume after every batch ──
            await db.save_resume(
                user_id, str(src), str(dest_raw),
                start_id, end_id, last_saved_id,
            )

    finally:
        try:
            await user_client.stop()
        except Exception:
            pass
        ok   = state.get("ok",   0)
        fail = state.get("fail", 0)
        skip = state.get("skip", 0)
        cancelled = state.get("cancel", False)
        forward_state.pop(user_id, None)

    if cancelled:
        await status_msg.edit_text(
            f"🛑 <b>sᴛᴏᴘᴘᴇᴅ</b>\n\n"
            f"✅ <code>{ok}</code> | ❌ <code>{fail}</code> | ⏭ <code>{skip}</code>\n\n"
            f"<b>💾 ᴘʀᴏɢʀᴇss sᴀᴠᴇᴅ. sᴇɴᴅ /resume ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ.</b>",
            parse_mode=HTML,
        )
    else:
        await db.clear_resume(user_id)
        first_error = state.get("first_error")
        done_text = (
            f"✅ <b>ᴅᴏɴᴇ!</b>\n\n"
            f"✅ <b>sᴇɴᴛ:</b>  <code>{ok}</code>\n"
            f"❌ <b>ғᴀɪʟ:</b>  <code>{fail}</code>\n"
            f"⏭ <b>sᴋɪᴘ:</b>  <code>{skip}</code>"
        )
        if fail > 0 and first_error:
            done_text += f"\n\n⚠️ <b>ғɪʀsᴛ ᴇʀʀᴏʀ:</b>\n<code>{first_error}</code>"
        await status_msg.edit_text(done_text, parse_mode=HTML)


# --------------- Internals ---------------
async def _send_one(user_client: Client, msg: Message, dest) -> tuple[bool, str | None]:
    bold = _bold_caption(msg)
    copy_err: str | None = None
    try:
        await msg.copy(dest, caption=bold, parse_mode=HTML)
        return True, None
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
        copy_err = f"FloodWait({e.value}s) on copy"
    except Exception as e:
        copy_err = f"copy: {type(e).__name__}: {e}"
    ok, err = await _download_reupload(user_client, msg, dest)
    return ok, (err or copy_err)


async def _send_media_group(user_client: Client, src, anchor_id: int, dest) -> tuple[bool, str | None]:
    group: list[Message] = []
    captions = None
    last_err: str | None = None
    try:
        group    = await user_client.get_media_group(src, anchor_id)
        captions = [f"<b>{i.caption.html}</b>" if i.caption else "" for i in group]
    except Exception as e:
        group = []; captions = None
        last_err = f"get_media_group: {type(e).__name__}: {e}"

    try:
        await user_client.copy_media_group(dest, src, anchor_id, captions=captions)
        return True, None
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
        last_err = f"FloodWait({e.value}s) on copy_media_group"
    except Exception as e:
        last_err = f"copy_media_group: {type(e).__name__}: {e}"

    if group:
        any_ok = False
        for item in group:
            ok, err = await _download_reupload(user_client, item, dest)
            if ok:
                any_ok = True
            elif err and not any_ok:
                last_err = err
            await asyncio.sleep(0.5)
        return any_ok, (None if any_ok else last_err)

    try:
        anc = await user_client.get_messages(src, anchor_id)
        if anc and not getattr(anc, "empty", False):
            return await _download_reupload(user_client, anc, dest)
    except Exception as e:
        last_err = f"anchor get_messages: {type(e).__name__}: {e}"
    return False, last_err


async def _download_reupload(user_client: Client, msg: Message, dest) -> tuple[bool, str | None]:
    try:
        if msg.text and not msg.media:
            try:
                await user_client.send_message(
                    dest, f"<b>{msg.text.html}</b>",
                    parse_mode=HTML, disable_web_page_preview=True)
                return True, None
            except Exception as e:
                return False, f"send_message: {type(e).__name__}: {e}"

        caption = _bold_caption(msg)
        path    = await user_client.download_media(msg)
        if not path:
            return False, "download_media returned None (no downloadable media or access denied)"

        try:
            if msg.photo:
                await user_client.send_photo(dest, path, caption=caption, parse_mode=HTML)
            elif msg.video:
                await user_client.send_video(dest, path, caption=caption, parse_mode=HTML,
                    duration=msg.video.duration, width=msg.video.width, height=msg.video.height)
            elif msg.animation:
                await user_client.send_animation(dest, path, caption=caption, parse_mode=HTML)
            elif msg.audio:
                await user_client.send_audio(dest, path, caption=caption, parse_mode=HTML,
                    duration=msg.audio.duration, performer=msg.audio.performer, title=msg.audio.title)
            elif msg.voice:
                await user_client.send_voice(dest, path, caption=caption, parse_mode=HTML,
                    duration=msg.voice.duration)
            elif msg.video_note:
                await user_client.send_video_note(dest, path, duration=msg.video_note.duration)
            elif msg.sticker:
                await user_client.send_sticker(dest, path)
            elif msg.document:
                await user_client.send_document(dest, path, caption=caption, parse_mode=HTML,
                    file_name=msg.document.file_name)
            else:
                await user_client.send_document(dest, path, caption=caption, parse_mode=HTML)
            return True, None
        except Exception as e:
            return False, f"send_{type(msg.media).__name__ if msg.media else 'doc'}: {type(e).__name__}: {e}"
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
        return False, f"FloodWait({e.value}s) in download_reupload"
    except Exception as e:
        return False, f"download_reupload: {type(e).__name__}: {e}"
