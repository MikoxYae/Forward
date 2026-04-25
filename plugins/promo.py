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
