import asyncio
import logging
import re
from datetime import datetime

from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, ChannelPrivate, ChatWriteForbidden, RPCError
from pyrogram.types import Message

from config import OWNER_ID
from database.db import db


HTML = enums.ParseMode.HTML
log = logging.getLogger("miko.promo")

# How many promos a single (non-owner) user may have at once.
PROMO_PER_USER_LIMIT = 5


# ------------------------------------------------------------------
# In-memory state
# ------------------------------------------------------------------
# user_id -> {"target_chat": ..., "target_title": ..., "edit_promo_id": <int|None>}
# Only set during a /setp or /editpromo flow.
promo_set_state: dict[int, dict] = {}

# promo_id -> asyncio.Task (running promo loop)
_running_tasks: dict[int, asyncio.Task] = {}

_scheduler_started = False
_scheduler_lock = asyncio.Lock()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _parse_chat(arg: str):
    arg = arg.strip()
    if arg.startswith("@"):
        return arg
    try:
        return int(arg)
    except ValueError:
        if re.match(r"^[a-zA-Z][a-zA-Z0-9_]{3,}$", arg):
            return "@" + arg
        return arg


def _fmt_target(target) -> str:
    return str(target)


async def _get_user_promo(promo_id: int, user_id: int):
    """Return (promo, error_html). Verifies the promo belongs to user_id."""
    promo = await db.get_promo(promo_id)
    if not promo:
        return None, f"<b>ɴᴏ ᴘʀᴏᴍᴏ ᴡɪᴛʜ ɪᴅ</b> <code>{promo_id}</code><b>.</b>"
    if int(promo.get("owner_id", 0)) != int(user_id):
        return None, (
            "<b>ᴛʜɪs ᴘʀᴏᴍᴏ ᴅᴏᴇsɴ'ᴛ ʙᴇʟᴏɴɢ ᴛᴏ ʏᴏᴜ.</b>\n"
            "<b>ᴜsᴇ /list ᴛᴏ sᴇᴇ ʏᴏᴜʀ ᴏᴡɴ ᴘʀᴏᴍᴏs.</b>"
        )
    return promo, None


async def _check_promo_limit(user_id: int):
    """Returns error_html if the user already has the max number of promos,
    or None if they can create another. The owner is exempt."""
    if int(user_id) == int(OWNER_ID):
        return None
    n = await db.count_user_promos(user_id)
    if n >= PROMO_PER_USER_LIMIT:
        return (
            f"<b>ʏᴏᴜ'ᴠᴇ ʀᴇᴀᴄʜᴇᴅ ᴛʜᴇ ʟɪᴍɪᴛ ᴏғ {PROMO_PER_USER_LIMIT} ᴘʀᴏᴍᴏs.</b>\n"
            "<b>ᴅᴇʟᴇᴛᴇ ᴀɴ ᴏʟᴅ ᴏɴᴇ ғɪʀsᴛ ᴜsɪɴɢ /delpromo &lt;id&gt;.</b>"
        )
    return None


# ------------------------------------------------------------------
# Content extraction / sending
# ------------------------------------------------------------------
# We snapshot every promo message at capture time and store the cached
# content in MongoDB. This way the promo keeps posting forever even if
# the user later deletes the original message in their DM with the bot
# (which was the root cause of "Empty messages cannot be copied" +
# "'NoneType' object has no attribute 'id'" errors).

def _extract_content(message: Message) -> dict | None:
    """Return a serializable dict describing the message, or None if
    the message has no supported content."""
    if message.text:
        return {
            "type": "text",
            "text_html": message.text.html or "",
        }
    if message.photo:
        return {
            "type": "photo",
            "file_id": message.photo.file_id,
            "caption_html": message.caption.html if message.caption else None,
        }
    if message.video:
        return {
            "type": "video",
            "file_id": message.video.file_id,
            "caption_html": message.caption.html if message.caption else None,
            "duration": message.video.duration,
            "width": message.video.width,
            "height": message.video.height,
        }
    if message.animation:
        return {
            "type": "animation",
            "file_id": message.animation.file_id,
            "caption_html": message.caption.html if message.caption else None,
            "duration": message.animation.duration,
            "width": message.animation.width,
            "height": message.animation.height,
        }
    if message.audio:
        return {
            "type": "audio",
            "file_id": message.audio.file_id,
            "caption_html": message.caption.html if message.caption else None,
            "duration": message.audio.duration,
            "performer": message.audio.performer,
            "title": message.audio.title,
        }
    if message.voice:
        return {
            "type": "voice",
            "file_id": message.voice.file_id,
            "caption_html": message.caption.html if message.caption else None,
            "duration": message.voice.duration,
        }
    if message.video_note:
        return {
            "type": "video_note",
            "file_id": message.video_note.file_id,
            "duration": message.video_note.duration,
        }
    if message.sticker:
        return {
            "type": "sticker",
            "file_id": message.sticker.file_id,
        }
    if message.document:
        return {
            "type": "document",
            "file_id": message.document.file_id,
            "caption_html": message.caption.html if message.caption else None,
            "file_name": message.document.file_name,
        }
    return None


async def _send_content(bot: Client, target_chat, content: dict):
    """Send the cached promo content. Returns the sent Message or None."""
    t = content.get("type")
    cap = content.get("caption_html") or None
    fid = content.get("file_id")

    if t == "text":
        return await bot.send_message(
            target_chat,
            content.get("text_html") or "",
            parse_mode=HTML,
            disable_web_page_preview=True,
        )
    if t == "photo":
        return await bot.send_photo(
            target_chat, fid, caption=cap, parse_mode=HTML,
        )
    if t == "video":
        return await bot.send_video(
            target_chat, fid,
            caption=cap, parse_mode=HTML,
            duration=content.get("duration") or 0,
            width=content.get("width") or 0,
            height=content.get("height") or 0,
        )
    if t == "animation":
        return await bot.send_animation(
            target_chat, fid,
            caption=cap, parse_mode=HTML,
            duration=content.get("duration") or 0,
            width=content.get("width") or 0,
            height=content.get("height") or 0,
        )
    if t == "audio":
        return await bot.send_audio(
            target_chat, fid,
            caption=cap, parse_mode=HTML,
            duration=content.get("duration") or 0,
            performer=content.get("performer"),
            title=content.get("title"),
        )
    if t == "voice":
        return await bot.send_voice(
            target_chat, fid,
            caption=cap, parse_mode=HTML,
            duration=content.get("duration") or 0,
        )
    if t == "video_note":
        return await bot.send_video_note(
            target_chat, fid,
            duration=content.get("duration") or 0,
        )
    if t == "sticker":
        return await bot.send_sticker(target_chat, fid)
    if t == "document":
        return await bot.send_document(
            target_chat, fid,
            caption=cap, parse_mode=HTML,
            file_name=content.get("file_name"),
        )
    return None


# ------------------------------------------------------------------
# Posting helpers
# ------------------------------------------------------------------
async def _post_once(bot: Client, promo: dict) -> int | None:
    target = promo["target_chat"]
    content = promo.get("content")

    async def _do_send():
        if content:
            return await _send_content(bot, target, content)
        # Backward-compat path for promos created before content caching.
        src_chat = promo.get("source_chat_id")
        src_msg = promo.get("source_msg_id")
        if not src_chat or not src_msg:
            return None
        return await bot.copy_message(target, src_chat, src_msg)

    try:
        sent = await _do_send()
        if not sent:
            log.warning(
                f"promo {promo['_id']} send returned no message — "
                "source may be deleted or content invalid. "
                "Use /editpromo to re-record the message."
            )
            return None
        return sent.id
    except FloodWait as e:
        log.warning(f"promo {promo['_id']} FloodWait {e.value}s on post")
        await asyncio.sleep(e.value + 1)
        try:
            sent = await _do_send()
            return sent.id if sent else None
        except Exception as ee:
            log.error(f"promo {promo['_id']} retry post failed: {ee}")
            return None
    except (ChannelPrivate, ChatWriteForbidden) as e:
        log.error(f"promo {promo['_id']} cannot post (no access): {e}")
        return None
    except RPCError as e:
        log.error(f"promo {promo['_id']} RPC error: {e}")
        return None
    except Exception as e:
        log.error(f"promo {promo['_id']} unexpected post error: {e}")
        return None


async def _delete_previous(bot: Client, promo: dict):
    last_id = promo.get("last_post_id")
    if not last_id:
        return
    try:
        await bot.delete_messages(promo["target_chat"], last_id)
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
        try:
            await bot.delete_messages(promo["target_chat"], last_id)
        except Exception:
            pass
    except Exception as e:
        log.info(f"promo {promo['_id']} delete prev {last_id} skipped: {e}")


async def _post_cycle(bot: Client, promo_id: int) -> int | None:
    """Delete previous + post new + persist last_post_id. Returns new id or None."""
    promo = await db.get_promo(promo_id)
    if not promo:
        return None
    await _delete_previous(bot, promo)
    new_id = await _post_once(bot, promo)
    if new_id:
        await db.update_promo(
            promo_id,
            last_post_id=new_id,
            last_post_at=datetime.utcnow(),
        )
    return new_id


# ------------------------------------------------------------------
# Loop (per promo)
# ------------------------------------------------------------------
async def _promo_loop(bot: Client, promo_id: int):
    log.info(f"[promo:{promo_id}] loop started")
    try:
        promo = await db.get_promo(promo_id)
        if not promo or not promo.get("enabled"):
            return
        # Initial cycle: also deletes a previous post if there is one — this
        # prevents stale posts from piling up when the loop is restarted
        # (e.g. after /ptime, /editpromo, or a bot restart).
        await _post_cycle(bot, promo_id)

        while True:
            promo = await db.get_promo(promo_id)
            if not promo or not promo.get("enabled"):
                return
            interval = max(1, int(promo.get("interval_minutes", 20)))
            await asyncio.sleep(interval * 60)

            promo = await db.get_promo(promo_id)
            if not promo or not promo.get("enabled"):
                return
            await _post_cycle(bot, promo_id)
    except asyncio.CancelledError:
        log.info(f"[promo:{promo_id}] loop cancelled")
        raise
    except Exception as e:
        log.error(f"[promo:{promo_id}] crashed: {e}")


def _spawn_task(bot: Client, promo_id: int):
    old = _running_tasks.get(promo_id)
    if old and not old.done():
        old.cancel()
    task = asyncio.create_task(_promo_loop(bot, promo_id))
    _running_tasks[promo_id] = task


def _kill_task(promo_id: int):
    old = _running_tasks.pop(promo_id, None)
    if old and not old.done():
        old.cancel()


def _is_running(promo_id: int) -> bool:
    t = _running_tasks.get(promo_id)
    return bool(t and not t.done())


# ------------------------------------------------------------------
# Startup hook
# ------------------------------------------------------------------
async def start_promo_scheduler(bot: Client):
    global _scheduler_started
    async with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    count = 0
    async for promo in db.enabled_promos():
        _spawn_task(bot, promo["_id"])
        count += 1
    log.info(f"promo scheduler started — {count} active promo(s)")


# ------------------------------------------------------------------
# Target validation
# ------------------------------------------------------------------
async def _validate_target_for_user(bot: Client, target, user_id: int):
    """Returns (chat, error_html_or_None). Verifies:
       1) bot can access the chat
       2) bot is admin with post + delete perms (channels)
       3) the requesting user is admin/owner in the chat
    """
    try:
        chat = await bot.get_chat(target)
    except Exception as e:
        return None, f"<b>ᴄᴀɴɴᴏᴛ ᴀᴄᴄᴇss ᴛʜᴀᴛ ᴄʜᴀᴛ:</b> <code>{e}</code>"

    # Bot's own admin perms
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat.id, me.id)
        if member.status not in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER,
        ):
            return None, (
                "<b>ɪ ᴀᴍ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀᴛ.</b>\n"
                "<b>ᴀᴅᴅ ᴍᴇ ᴀs ᴀᴅᴍɪɴ ᴡɪᴛʜ \"ᴘᴏsᴛ ᴍᴇssᴀɢᴇs\" + \"ᴅᴇʟᴇᴛᴇ ᴍᴇssᴀɢᴇs\".</b>"
            )
        if chat.type == enums.ChatType.CHANNEL and getattr(member, "privileges", None):
            if not member.privileges.can_post_messages:
                return None, "<b>ɪ ʟᴀᴄᴋ ᴛʜᴇ \"ᴘᴏsᴛ ᴍᴇssᴀɢᴇs\" ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴ.</b>"
            if not member.privileges.can_delete_messages:
                return None, "<b>ɪ ʟᴀᴄᴋ ᴛʜᴇ \"ᴅᴇʟᴇᴛᴇ ᴍᴇssᴀɢᴇs\" ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴ.</b>"
    except Exception as e:
        log.info(f"could not check bot admin perms in {chat.id}: {e}")
        # If we can't verify, fail open — the post attempt itself will report.

    # User's admin status (so a random user can't schedule promos in someone
    # else's channel just because the bot happens to be admin there).
    if int(user_id) != int(OWNER_ID):
        try:
            umember = await bot.get_chat_member(chat.id, user_id)
            if umember.status not in (
                enums.ChatMemberStatus.ADMINISTRATOR,
                enums.ChatMemberStatus.OWNER,
            ):
                return None, (
                    "<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀᴛ.</b>\n"
                    "<b>ᴏɴʟʏ ᴀᴅᴍɪɴs ᴄᴀɴ sᴄʜᴇᴅᴜʟᴇ ᴘʀᴏᴍᴏs ɪɴ ᴀ ᴄʜᴀᴛ.</b>"
                )
        except Exception as e:
            return None, (
                f"<b>ᴄᴏᴜʟᴅ ɴᴏᴛ ᴠᴇʀɪғʏ ʏᴏᴜʀ ᴀᴅᴍɪɴ sᴛᴀᴛᴜs:</b> <code>{e}</code>\n"
                "<b>ᴀʀᴇ ʏᴏᴜ ᴀ ᴍᴇᴍʙᴇʀ ᴏғ ᴛʜᴀᴛ ᴄʜᴀᴛ?</b>"
            )

    return chat, None


# ------------------------------------------------------------------
# /setp <chat>
# ------------------------------------------------------------------
@Client.on_message(filters.command("setp") & filters.private)
async def setp_cmd(bot: Client, message: Message):
    user_id = message.from_user.id

    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/setp &lt;ᴄʜᴀᴛ_ɪᴅ ᴏʀ @ᴜsᴇʀɴᴀᴍᴇ&gt;</code>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/setp -1001234567890</code>",
            parse_mode=HTML,
        )

    err = await _check_promo_limit(user_id)
    if err:
        return await message.reply_text(err, parse_mode=HTML)

    target = _parse_chat(" ".join(message.command[1:]))
    chat, err = await _validate_target_for_user(bot, target, user_id)
    if err:
        return await message.reply_text(err, parse_mode=HTML)

    promo_set_state[user_id] = {
        "target_chat": chat.id,
        "target_title": getattr(chat, "title", None) or str(target),
        "edit_promo_id": None,
    }

    await message.reply_text(
        f"<b>ᴛᴀʀɢᴇᴛ:</b> <code>{chat.title}</code> (<code>{chat.id}</code>)\n\n"
        "<b>ɴᴏᴡ sᴇɴᴅ ᴛʜᴇ ᴘʀᴏᴍᴏ ᴍᴇssᴀɢᴇ.</b>\n\n"
        "<b>ᴀʟʟᴏᴡᴇᴅ:</b> ᴘʟᴀɪɴ ᴛᴇxᴛ, ᴘʜᴏᴛᴏ, ᴠɪᴅᴇᴏ, ᴀᴜᴅɪᴏ, ᴠᴏɪᴄᴇ, ᴀɴɪᴍᴀᴛɪᴏɴ, "
        "sᴛɪᴄᴋᴇʀ, ᴅᴏᴄᴜᴍᴇɴᴛ, ᴏʀ ᴀɴʏ ᴄᴏᴍʙᴏ + ᴄᴀᴘᴛɪᴏɴ. <b>ᴀʟʟ ғᴏʀᴍᴀᴛᴛɪɴɢ "
        "(ʟɪɴᴋs, ʙᴏʟᴅ, ɪᴛᴀʟɪᴄ ᴇᴛᴄ.) ɪs ᴋᴇᴘᴛ.</b>\n\n"
        "<b>sᴇɴᴅ /cancelp ᴛᴏ ᴀʙᴏʀᴛ.</b>",
        parse_mode=HTML,
    )


# ------------------------------------------------------------------
# /editpromo <id>
# ------------------------------------------------------------------
@Client.on_message(filters.command("editpromo") & filters.private)
async def editpromo_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/editpromo &lt;promo_id&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)

    promo, err = await _get_user_promo(promo_id, user_id)
    if err:
        return await message.reply_text(err, parse_mode=HTML)

    promo_set_state[user_id] = {
        "target_chat": promo["target_chat"],
        "target_title": str(promo["target_chat"]),
        "edit_promo_id": promo_id,
    }
    await message.reply_text(
        f"<b>ᴇᴅɪᴛɪɴɢ ᴘʀᴏᴍᴏ</b> <code>{promo_id}</code><b>.</b>\n"
        "<b>ɴᴏᴡ sᴇɴᴅ ᴛʜᴇ ɴᴇᴡ ᴘʀᴏᴍᴏ ᴄᴏɴᴛᴇɴᴛ — ᴀɴʏ ᴛᴇxᴛ / ᴍᴇᴅɪᴀ / ᴄᴏᴍʙᴏ.</b>\n"
        "<b>sᴇɴᴅ /cancelp ᴛᴏ ᴀʙᴏʀᴛ.</b>",
        parse_mode=HTML,
    )


# ------------------------------------------------------------------
# /cancelp
# ------------------------------------------------------------------
@Client.on_message(filters.command("cancelp") & filters.private)
async def cancelp_cmd(bot: Client, message: Message):
    state = promo_set_state.pop(message.from_user.id, None)
    if state:
        await message.reply_text("<b>ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>", parse_mode=HTML)
    else:
        await message.reply_text("<b>ɴᴏᴛʜɪɴɢ ᴛᴏ ᴄᴀɴᴄᴇʟ.</b>", parse_mode=HTML)


# ------------------------------------------------------------------
# Capture next non-command message during /setp or /editpromo.
# Skips when the settings panel is currently awaiting input.
# ------------------------------------------------------------------
async def _promo_capture_filter(_, __, message: Message) -> bool:
    if not message.from_user:
        return False
    user_id = message.from_user.id
    # Defer to settings panel if it's the active wizard.
    try:
        from plugins.settings import settings_state  # local import avoids circular
        if user_id in settings_state and settings_state[user_id].get("awaiting"):
            return False
    except Exception:
        pass
    if user_id not in promo_set_state:
        return False
    if message.text and message.text.startswith("/"):
        return False
    return True


@Client.on_message(
    filters.private & filters.create(_promo_capture_filter),
    group=-1,
)
async def capture_promo_message(bot: Client, message: Message):
    user_id = message.from_user.id
    state = promo_set_state.pop(user_id, None)
    if not state:
        return

    src_chat_id = message.chat.id
    src_msg_id = message.id
    edit_id = state.get("edit_promo_id")

    # Snapshot the message content so we don't depend on the source DM
    # message staying alive (it can be deleted by the user).
    content = _extract_content(message)
    if not content:
        return await message.reply_text(
            "<b>ᴜɴsᴜᴘᴘᴏʀᴛᴇᴅ ᴄᴏɴᴛᴇɴᴛ. sᴇɴᴅ ᴛᴇxᴛ, ᴘʜᴏᴛᴏ, ᴠɪᴅᴇᴏ, ᴀᴜᴅɪᴏ, ᴠᴏɪᴄᴇ, "
            "ᴀɴɪᴍᴀᴛɪᴏɴ, sᴛɪᴄᴋᴇʀ, ᴠɪᴅᴇᴏ ɴᴏᴛᴇ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ.</b>",
            parse_mode=HTML,
        )

    # ---- Edit flow: replace existing promo's source ----
    if edit_id:
        promo, err = await _get_user_promo(edit_id, user_id)
        if err:
            return await message.reply_text(err, parse_mode=HTML)
        await db.update_promo(
            edit_id,
            source_chat_id=src_chat_id,
            source_msg_id=src_msg_id,
            content=content,
        )
        if promo.get("enabled"):
            _spawn_task(bot, edit_id)
        return await message.reply_text(
            f"<b>✅ ᴘʀᴏᴍᴏ</b> <code>{edit_id}</code> <b>ᴜᴘᴅᴀᴛᴇᴅ.</b>",
            parse_mode=HTML,
        )

    # ---- Create flow ----
    target_chat = state["target_chat"]
    target_title = state.get("target_title") or str(target_chat)

    # Re-check the limit in case the user stalled and created elsewhere meanwhile.
    err = await _check_promo_limit(user_id)
    if err:
        return await message.reply_text(err, parse_mode=HTML)

    promo_id = await db.add_promo(
        owner_id=user_id,
        target_chat=target_chat,
        source_chat_id=src_chat_id,
        source_msg_id=src_msg_id,
        interval_minutes=20,
        content=content,
    )
    _spawn_task(bot, promo_id)

    await message.reply_text(
        f"<b>✅ ᴘʀᴏᴍᴏ sᴀᴠᴇᴅ.</b>\n\n"
        f"<b>ɪᴅ:</b> <code>{promo_id}</code>\n"
        f"<b>ᴛᴀʀɢᴇᴛ:</b> <code>{target_title}</code> (<code>{target_chat}</code>)\n"
        f"<b>ɪɴᴛᴇʀᴠᴀʟ:</b> <code>20</code> <b>ᴍɪɴᴜᴛᴇs</b> (ᴅᴇғᴀᴜʟᴛ)\n"
        f"<b>sᴛᴀᴛᴜs:</b> <code>ᴏɴ</code>\n\n"
        f"<code>/ptime {promo_id} &lt;min&gt;</code>  <code>/promooff {promo_id}</code>  <code>/promoon {promo_id}</code>\n"
        f"<code>/promonow {promo_id}</code>  <code>/editpromo {promo_id}</code>  <code>/promopreview {promo_id}</code>\n"
        f"<code>/promostatus {promo_id}</code>  <code>/delpromo {promo_id}</code>  <code>/list</code>",
        parse_mode=HTML,
    )


# ------------------------------------------------------------------
# /list, /listp — only the caller's promos
# ------------------------------------------------------------------
@Client.on_message(filters.command(["list", "listp"]) & filters.private)
async def list_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    lines = ["<b>ʏᴏᴜʀ ᴘʀᴏᴍᴏs:</b>", ""]
    n = 0
    async for p in db.user_promos(user_id):
        n += 1
        state = "ᴏɴ" if p.get("enabled") else "ᴏғғ"
        lines.append(
            f"• <b>ɪᴅ</b> <code>{p['_id']}</code> — "
            f"<b>ᴛᴀʀɢᴇᴛ</b> <code>{_fmt_target(p['target_chat'])}</code> — "
            f"<b>ᴇᴠᴇʀʏ</b> <code>{p.get('interval_minutes', 20)}</code> <b>ᴍɪɴ</b> — "
            f"<b>{state}</b>"
        )
    if n == 0:
        lines.append("<b>ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴄʀᴇᴀᴛᴇᴅ ᴀɴʏ ᴘʀᴏᴍᴏs ʏᴇᴛ.</b>")
        lines.append("<b>ᴜsᴇ /setp ᴏʀ ᴏᴘᴇɴ /settings ᴛᴏ ᴄʀᴇᴀᴛᴇ ᴏɴᴇ.</b>")
    await message.reply_text("\n".join(lines), parse_mode=HTML)


# ------------------------------------------------------------------
# /ptime <id> <min>
# ------------------------------------------------------------------
@Client.on_message(filters.command("ptime") & filters.private)
async def ptime_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if len(message.command) < 3:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/ptime &lt;promo_id&gt; &lt;minutes&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
        minutes = int(message.command[2])
    except ValueError:
        return await message.reply_text(
            "<b>ɪᴅ ᴀɴᴅ ᴍɪɴᴜᴛᴇs ᴍᴜsᴛ ʙᴇ ɪɴᴛᴇɢᴇʀs.</b>",
            parse_mode=HTML,
        )
    if minutes < 1:
        return await message.reply_text("<b>ᴍɪɴᴜᴛᴇs ᴍᴜsᴛ ʙᴇ ᴀᴛ ʟᴇᴀsᴛ 1.</b>", parse_mode=HTML)

    promo, err = await _get_user_promo(promo_id, user_id)
    if err:
        return await message.reply_text(err, parse_mode=HTML)

    await db.update_promo(promo_id, interval_minutes=minutes)
    if promo.get("enabled"):
        _spawn_task(bot, promo_id)
    await message.reply_text(
        f"<b>ɪɴᴛᴇʀᴠᴀʟ ғᴏʀ ᴘʀᴏᴍᴏ</b> <code>{promo_id}</code> "
        f"<b>sᴇᴛ ᴛᴏ</b> <code>{minutes}</code> <b>ᴍɪɴᴜᴛᴇs.</b>",
        parse_mode=HTML,
    )


# ------------------------------------------------------------------
# /promoon /promooff
# ------------------------------------------------------------------
@Client.on_message(filters.command("promoon") & filters.private)
async def promoon_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/promoon &lt;promo_id&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)
    promo, err = await _get_user_promo(promo_id, user_id)
    if err:
        return await message.reply_text(err, parse_mode=HTML)
    await db.update_promo(promo_id, enabled=True)
    _spawn_task(bot, promo_id)
    await message.reply_text(
        f"<b>ᴘʀᴏᴍᴏ</b> <code>{promo_id}</code> <b>ɪs ɴᴏᴡ ᴏɴ.</b>",
        parse_mode=HTML,
    )


@Client.on_message(filters.command("promooff") & filters.private)
async def promooff_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/promooff &lt;promo_id&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)
    promo, err = await _get_user_promo(promo_id, user_id)
    if err:
        return await message.reply_text(err, parse_mode=HTML)
    await db.update_promo(promo_id, enabled=False)
    _kill_task(promo_id)
    await message.reply_text(
        f"<b>ᴘʀᴏᴍᴏ</b> <code>{promo_id}</code> <b>ɪs ɴᴏᴡ ᴏғғ.</b>",
        parse_mode=HTML,
    )


# ------------------------------------------------------------------
# /promonow <id>
# ------------------------------------------------------------------
@Client.on_message(filters.command("promonow") & filters.private)
async def promonow_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/promonow &lt;promo_id&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)

    promo, err = await _get_user_promo(promo_id, user_id)
    if err:
        return await message.reply_text(err, parse_mode=HTML)

    new_id = await _post_cycle(bot, promo_id)
    if new_id:
        await message.reply_text(
            f"<b>✅ ᴘᴏsᴛᴇᴅ ᴘʀᴏᴍᴏ</b> <code>{promo_id}</code> "
            f"<b>(ᴍsɢ ɪᴅ</b> <code>{new_id}</code><b>).</b>",
            parse_mode=HTML,
        )
    else:
        await message.reply_text(
            f"<b>❌ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴘᴏsᴛ ᴘʀᴏᴍᴏ</b> <code>{promo_id}</code><b>. "
            "ᴄʜᴇᴄᴋ ʙᴏᴛ ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴs ᴀɴᴅ sᴇʀᴠᴇʀ ʟᴏɢs. "
            "ɪғ ᴛʜɪs ᴘʀᴏᴍᴏ ᴡᴀs ᴄʀᴇᴀᴛᴇᴅ ʙᴇғᴏʀᴇ ᴛʜᴇ ʟᴀᴛᴇsᴛ ᴜᴘᴅᴀᴛᴇ, ᴜsᴇ "
            "/editpromo &lt;ɪᴅ&gt; ᴀɴᴅ ʀᴇsᴇɴᴅ ᴛʜᴇ ᴘʀᴏᴍᴏ ᴍᴇssᴀɢᴇ.</b>",
            parse_mode=HTML,
        )


# ------------------------------------------------------------------
# /promopreview <id>
# ------------------------------------------------------------------
@Client.on_message(filters.command("promopreview") & filters.private)
async def promopreview_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/promopreview &lt;promo_id&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)

    promo, err = await _get_user_promo(promo_id, user_id)
    if err:
        return await message.reply_text(err, parse_mode=HTML)

    content = promo.get("content")
    try:
        if content:
            sent = await _send_content(bot, message.chat.id, content)
        else:
            sent = await bot.copy_message(
                message.chat.id,
                promo["source_chat_id"],
                promo["source_msg_id"],
            )
        if not sent:
            raise RuntimeError("send returned no message")
    except Exception as e:
        return await message.reply_text(
            f"<b>❌ ᴘʀᴇᴠɪᴇᴡ ғᴀɪʟᴇᴅ:</b> <code>{e}</code>",
            parse_mode=HTML,
        )


# ------------------------------------------------------------------
# /promostatus <id>
# ------------------------------------------------------------------
@Client.on_message(filters.command("promostatus") & filters.private)
async def promostatus_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/promostatus &lt;promo_id&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)

    promo, err = await _get_user_promo(promo_id, user_id)
    if err:
        return await message.reply_text(err, parse_mode=HTML)

    last_at = promo.get("last_post_at")
    last_at_str = last_at.strftime("%Y-%m-%d %H:%M:%S UTC") if last_at else "ɴᴇᴠᴇʀ"
    state = "ᴏɴ" if promo.get("enabled") else "ᴏғғ"
    running = "ʏᴇs" if _is_running(promo_id) else "ɴᴏ"
    ctype = (promo.get("content") or {}).get("type") or "ʟᴇɢᴀᴄʏ-ᴄᴏᴘʏ"

    await message.reply_text(
        f"<b>ᴘʀᴏᴍᴏ</b> <code>{promo_id}</code>\n"
        f"<b>ᴛᴀʀɢᴇᴛ:</b> <code>{_fmt_target(promo['target_chat'])}</code>\n"
        f"<b>ᴄᴏɴᴛᴇɴᴛ ᴛʏᴘᴇ:</b> <code>{ctype}</code>\n"
        f"<b>ɪɴᴛᴇʀᴠᴀʟ:</b> <code>{promo.get('interval_minutes', 20)}</code> <b>ᴍɪɴ</b>\n"
        f"<b>ᴇɴᴀʙʟᴇᴅ:</b> <code>{state}</code>\n"
        f"<b>ʟᴏᴏᴘ ʀᴜɴɴɪɴɢ:</b> <code>{running}</code>\n"
        f"<b>ʟᴀsᴛ ᴘᴏsᴛᴇᴅ:</b> <code>{last_at_str}</code>",
        parse_mode=HTML,
    )


# ------------------------------------------------------------------
# /delpromo <id>
# ------------------------------------------------------------------
@Client.on_message(filters.command("delpromo") & filters.private)
async def delpromo_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/delpromo &lt;promo_id&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)

    promo, err = await _get_user_promo(promo_id, user_id)
    if err:
        return await message.reply_text(err, parse_mode=HTML)

    _kill_task(promo_id)
    await db.delete_promo(promo_id)
    await message.reply_text(
        f"<b>ᴘʀᴏᴍᴏ</b> <code>{promo_id}</code> <b>ᴅᴇʟᴇᴛᴇᴅ.</b>",
        parse_mode=HTML,
    )
