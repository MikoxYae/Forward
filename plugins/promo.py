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
def _is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


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


async def _owner_only(message: Message) -> bool:
    if not _is_owner(message.from_user.id):
        await message.reply_text(
            "<b>ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴛʜᴇ ᴏᴡɴᴇʀ.</b>",
            parse_mode=HTML,
        )
        return False
    return True


# ------------------------------------------------------------------
# Posting helpers
# ------------------------------------------------------------------
async def _post_once(bot: Client, promo: dict) -> int | None:
    target = promo["target_chat"]
    src_chat = promo["source_chat_id"]
    src_msg = promo["source_msg_id"]
    try:
        sent = await bot.copy_message(target, src_chat, src_msg)
        return sent.id
    except FloodWait as e:
        log.warning(f"promo {promo['_id']} FloodWait {e.value}s on post")
        await asyncio.sleep(e.value + 1)
        try:
            sent = await bot.copy_message(target, src_chat, src_msg)
            return sent.id
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
        # Initial cycle: also deletes a previous post if there is one — this
        # prevents stale posts from piling up when the loop is restarted
        # (e.g. after /ptime, /editpromo, or a bot restart).
        promo = await db.get_promo(promo_id)
        if not promo or not promo.get("enabled"):
            return
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
async def _validate_target(bot: Client, target):
    """Returns (chat, error_msg_or_None)."""
    try:
        chat = await bot.get_chat(target)
    except Exception as e:
        return None, f"<b>ᴄᴀɴɴᴏᴛ ᴀᴄᴄᴇss ᴛʜᴀᴛ ᴄʜᴀᴛ:</b> <code>{e}</code>"

    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat.id, me.id)
        if member.status not in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER,
        ):
            return None, (
                "<b>ɪ ᴀᴍ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀᴛ.</b>\n"
                "<b>ᴀᴅᴅ ᴍᴇ ᴀs ᴀᴅᴍɪɴ ᴡɪᴛʜ \"ᴘᴏsᴛ ᴍᴇssᴀɢᴇs\" ᴀɴᴅ \"ᴅᴇʟᴇᴛᴇ ᴍᴇssᴀɢᴇs\" ᴘᴇʀᴍɪssɪᴏɴs.</b>"
            )
        if chat.type == enums.ChatType.CHANNEL and getattr(member, "privileges", None):
            if not member.privileges.can_post_messages:
                return None, "<b>ɪ ʟᴀᴄᴋ ᴛʜᴇ \"ᴘᴏsᴛ ᴍᴇssᴀɢᴇs\" ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴ.</b>"
            if not member.privileges.can_delete_messages:
                return None, "<b>ɪ ʟᴀᴄᴋ ᴛʜᴇ \"ᴅᴇʟᴇᴛᴇ ᴍᴇssᴀɢᴇs\" ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴ.</b>"
    except Exception as e:
        log.info(f"could not check admin perms in {chat.id}: {e}")
        # Don't fail outright — the post attempt itself will surface the issue.
    return chat, None


# ------------------------------------------------------------------
# /setp <chat>
# ------------------------------------------------------------------
@Client.on_message(filters.command("setp") & filters.private)
async def setp_cmd(bot: Client, message: Message):
    if not await _owner_only(message):
        return

    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/setp &lt;ᴄʜᴀᴛ_ɪᴅ ᴏʀ @ᴜsᴇʀɴᴀᴍᴇ&gt;</code>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/setp -1001234567890</code>",
            parse_mode=HTML,
        )

    target = _parse_chat(" ".join(message.command[1:]))
    chat, err = await _validate_target(bot, target)
    if err:
        return await message.reply_text(err, parse_mode=HTML)

    promo_set_state[message.from_user.id] = {
        "target_chat": chat.id,
        "target_title": getattr(chat, "title", None) or str(target),
        "edit_promo_id": None,
    }

    await message.reply_text(
        f"<b>ᴛᴀʀɢᴇᴛ:</b> <code>{chat.title}</code> (<code>{chat.id}</code>)\n\n"
        "<b>ɴᴏᴡ sᴇɴᴅ ᴛʜᴇ ᴘʀᴏᴍᴏ ᴍᴇssᴀɢᴇ.</b>\n\n"
        "<b>ᴀʟʟᴏᴡᴇᴅ:</b> ᴘʟᴀɪɴ ᴛᴇxᴛ, ᴘʜᴏᴛᴏ, ᴠɪᴅᴇᴏ, ᴀᴜᴅɪᴏ, ᴠᴏɪᴄᴇ, ᴀɴɪᴍᴀᴛɪᴏɴ, sᴛɪᴄᴋᴇʀ, ᴅᴏᴄᴜᴍᴇɴᴛ, ᴏʀ ᴀɴʏ ᴄᴏᴍʙᴏ + ᴄᴀᴘᴛɪᴏɴ. <b>ᴀʟʟ ғᴏʀᴍᴀᴛᴛɪɴɢ (ʟɪɴᴋs, ʙᴏʟᴅ, ɪᴛᴀʟɪᴄ ᴇᴛᴄ.) ɪs ᴋᴇᴘᴛ.</b>\n\n"
        "<b>sᴇɴᴅ /cancelp ᴛᴏ ᴀʙᴏʀᴛ.</b>",
        parse_mode=HTML,
    )


# ------------------------------------------------------------------
# /editpromo <id>
# ------------------------------------------------------------------
@Client.on_message(filters.command("editpromo") & filters.private)
async def editpromo_cmd(bot: Client, message: Message):
    if not await _owner_only(message):
        return
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/editpromo &lt;promo_id&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)

    promo = await db.get_promo(promo_id)
    if not promo:
        return await message.reply_text(
            f"<b>ɴᴏ ᴘʀᴏᴍᴏ ᴡɪᴛʜ ɪᴅ</b> <code>{promo_id}</code><b>.</b>",
            parse_mode=HTML,
        )

    promo_set_state[message.from_user.id] = {
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
    if not await _owner_only(message):
        return
    state = promo_set_state.pop(message.from_user.id, None)
    if state:
        await message.reply_text("<b>ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>", parse_mode=HTML)
    else:
        await message.reply_text("<b>ɴᴏᴛʜɪɴɢ ᴛᴏ ᴄᴀɴᴄᴇʟ.</b>", parse_mode=HTML)


# ------------------------------------------------------------------
# Capture next non-command message during /setp or /editpromo
# ------------------------------------------------------------------
async def _promo_capture_filter(_, __, message: Message) -> bool:
    if not message.from_user:
        return False
    if message.from_user.id not in promo_set_state:
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

    # ---- Edit flow: replace existing promo's source ----
    if edit_id:
        await db.update_promo(
            edit_id,
            source_chat_id=src_chat_id,
            source_msg_id=src_msg_id,
        )
        promo = await db.get_promo(edit_id)
        if promo and promo.get("enabled"):
            # Restart loop so the new content is posted right away.
            _spawn_task(bot, edit_id)
        return await message.reply_text(
            f"<b>✅ ᴘʀᴏᴍᴏ</b> <code>{edit_id}</code> <b>ᴜᴘᴅᴀᴛᴇᴅ.</b>",
            parse_mode=HTML,
        )

    # ---- Create flow ----
    target_chat = state["target_chat"]
    target_title = state.get("target_title") or str(target_chat)

    promo_id = await db.add_promo(
        owner_id=user_id,
        target_chat=target_chat,
        source_chat_id=src_chat_id,
        source_msg_id=src_msg_id,
        interval_minutes=20,
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
# /list, /listp
# ------------------------------------------------------------------
@Client.on_message(filters.command(["list", "listp"]) & filters.private)
async def list_cmd(bot: Client, message: Message):
    if not await _owner_only(message):
        return
    lines = ["<b>ᴀʟʟ ᴘʀᴏᴍᴏs:</b>", ""]
    n = 0
    async for p in db.all_promos():
        n += 1
        state = "ᴏɴ" if p.get("enabled") else "ᴏғғ"
        lines.append(
            f"• <b>ɪᴅ</b> <code>{p['_id']}</code> — "
            f"<b>ᴛᴀʀɢᴇᴛ</b> <code>{_fmt_target(p['target_chat'])}</code> — "
            f"<b>ᴇᴠᴇʀʏ</b> <code>{p.get('interval_minutes', 20)}</code> <b>ᴍɪɴ</b> — "
            f"<b>{state}</b>"
        )
    if n == 0:
        lines.append("<b>ɴᴏ ᴘʀᴏᴍᴏs ʏᴇᴛ. ᴜsᴇ /setp ᴛᴏ ᴄʀᴇᴀᴛᴇ ᴏɴᴇ.</b>")
    await message.reply_text("\n".join(lines), parse_mode=HTML)


# ------------------------------------------------------------------
# /ptime <id> <min>
# ------------------------------------------------------------------
@Client.on_message(filters.command("ptime") & filters.private)
async def ptime_cmd(bot: Client, message: Message):
    if not await _owner_only(message):
        return
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

    promo = await db.get_promo(promo_id)
    if not promo:
        return await message.reply_text(
            f"<b>ɴᴏ ᴘʀᴏᴍᴏ ᴡɪᴛʜ ɪᴅ</b> <code>{promo_id}</code><b>.</b>",
            parse_mode=HTML,
        )

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
    if not await _owner_only(message):
        return
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/promoon &lt;promo_id&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)
    promo = await db.get_promo(promo_id)
    if not promo:
        return await message.reply_text(
            f"<b>ɴᴏ ᴘʀᴏᴍᴏ ᴡɪᴛʜ ɪᴅ</b> <code>{promo_id}</code><b>.</b>",
            parse_mode=HTML,
        )
    await db.update_promo(promo_id, enabled=True)
    _spawn_task(bot, promo_id)
    await message.reply_text(
        f"<b>ᴘʀᴏᴍᴏ</b> <code>{promo_id}</code> <b>ɪs ɴᴏᴡ ᴏɴ.</b>",
        parse_mode=HTML,
    )


@Client.on_message(filters.command("promooff") & filters.private)
async def promooff_cmd(bot: Client, message: Message):
    if not await _owner_only(message):
        return
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/promooff &lt;promo_id&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)
    promo = await db.get_promo(promo_id)
    if not promo:
        return await message.reply_text(
            f"<b>ɴᴏ ᴘʀᴏᴍᴏ ᴡɪᴛʜ ɪᴅ</b> <code>{promo_id}</code><b>.</b>",
            parse_mode=HTML,
        )
    await db.update_promo(promo_id, enabled=False)
    _kill_task(promo_id)
    await message.reply_text(
        f"<b>ᴘʀᴏᴍᴏ</b> <code>{promo_id}</code> <b>ɪs ɴᴏᴡ ᴏғғ.</b>",
        parse_mode=HTML,
    )


# ------------------------------------------------------------------
# /promonow <id>  — fire one cycle right now
# ------------------------------------------------------------------
@Client.on_message(filters.command("promonow") & filters.private)
async def promonow_cmd(bot: Client, message: Message):
    if not await _owner_only(message):
        return
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/promonow &lt;promo_id&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)

    promo = await db.get_promo(promo_id)
    if not promo:
        return await message.reply_text(
            f"<b>ɴᴏ ᴘʀᴏᴍᴏ ᴡɪᴛʜ ɪᴅ</b> <code>{promo_id}</code><b>.</b>",
            parse_mode=HTML,
        )

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
            "ᴄʜᴇᴄᴋ ʙᴏᴛ ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴs ᴀɴᴅ sᴇʀᴠᴇʀ ʟᴏɢs.</b>",
            parse_mode=HTML,
        )


# ------------------------------------------------------------------
# /promopreview <id>  — DM the saved promo back to owner
# ------------------------------------------------------------------
@Client.on_message(filters.command("promopreview") & filters.private)
async def promopreview_cmd(bot: Client, message: Message):
    if not await _owner_only(message):
        return
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/promopreview &lt;promo_id&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)

    promo = await db.get_promo(promo_id)
    if not promo:
        return await message.reply_text(
            f"<b>ɴᴏ ᴘʀᴏᴍᴏ ᴡɪᴛʜ ɪᴅ</b> <code>{promo_id}</code><b>.</b>",
            parse_mode=HTML,
        )

    await message.reply_text(
        f"<b>ᴘʀᴇᴠɪᴇᴡ ᴏғ ᴘʀᴏᴍᴏ</b> <code>{promo_id}</code><b>:</b>",
        parse_mode=HTML,
    )
    try:
        await bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=promo["source_chat_id"],
            message_id=promo["source_msg_id"],
        )
    except Exception as e:
        await message.reply_text(
            f"<b>❌ ᴄᴏᴜʟᴅ ɴᴏᴛ ʟᴏᴀᴅ ᴘʀᴏᴍᴏ ᴄᴏɴᴛᴇɴᴛ:</b> <code>{e}</code>\n"
            "<b>ᴛʜᴇ sᴏᴜʀᴄᴇ ᴍᴇssᴀɢᴇ ᴍᴀʏ ʜᴀᴠᴇ ʙᴇᴇɴ ᴅᴇʟᴇᴛᴇᴅ. ᴜsᴇ /editpromo "
            f"{promo_id} ᴛᴏ ʀᴇsᴇᴛ ɪᴛ.</b>",
            parse_mode=HTML,
        )


# ------------------------------------------------------------------
# /delpromo <id>
# ------------------------------------------------------------------
@Client.on_message(filters.command("delpromo") & filters.private)
async def delpromo_cmd(bot: Client, message: Message):
    if not await _owner_only(message):
        return
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/delpromo &lt;promo_id&gt;</code>",
            parse_mode=HTML,
        )
    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)
    promo = await db.get_promo(promo_id)
    if not promo:
        return await message.reply_text(
            f"<b>ɴᴏ ᴘʀᴏᴍᴏ ᴡɪᴛʜ ɪᴅ</b> <code>{promo_id}</code><b>.</b>",
            parse_mode=HTML,
        )
    _kill_task(promo_id)
    last_id = promo.get("last_post_id")
    if last_id:
        try:
            await bot.delete_messages(promo["target_chat"], last_id)
        except Exception:
            pass
    await db.delete_promo(promo_id)
    await message.reply_text(
        f"<b>ᴘʀᴏᴍᴏ</b> <code>{promo_id}</code> <b>ᴅᴇʟᴇᴛᴇᴅ.</b>",
        parse_mode=HTML,
    )


# ------------------------------------------------------------------
# /promostatus [<id>]
# ------------------------------------------------------------------
@Client.on_message(filters.command("promostatus") & filters.private)
async def promostatus_cmd(bot: Client, message: Message):
    if not await _owner_only(message):
        return

    if len(message.command) < 2:
        lines = ["<b>ᴘʀᴏᴍᴏ sᴛᴀᴛᴜs (ᴀʟʟ):</b>", ""]
        n = 0
        async for p in db.all_promos():
            n += 1
            state = "ᴏɴ" if p.get("enabled") else "ᴏғғ"
            running = "ʀᴜɴɴɪɴɢ" if (
                _running_tasks.get(p["_id"])
                and not _running_tasks[p["_id"]].done()
            ) else "sᴛᴏᴘᴘᴇᴅ"
            last = p.get("last_post_at")
            last_str = last.strftime("%Y-%m-%d %H:%M:%S UTC") if last else "—"
            lines.append(
                f"<b>ɪᴅ</b> <code>{p['_id']}</code> | "
                f"<b>ᴛᴀʀɢᴇᴛ</b> <code>{_fmt_target(p['target_chat'])}</code> | "
                f"<b>ᴇᴠᴇʀʏ</b> <code>{p.get('interval_minutes', 20)}</code> <b>ᴍɪɴ</b> | "
                f"<b>{state}</b> | <b>{running}</b> | <b>ʟᴀsᴛ:</b> <code>{last_str}</code>"
            )
        if n == 0:
            lines.append("<b>ɴᴏ ᴘʀᴏᴍᴏs ʏᴇᴛ.</b>")
        return await message.reply_text("\n".join(lines), parse_mode=HTML)

    try:
        promo_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("<b>ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>", parse_mode=HTML)

    p = await db.get_promo(promo_id)
    if not p:
        return await message.reply_text(
            f"<b>ɴᴏ ᴘʀᴏᴍᴏ ᴡɪᴛʜ ɪᴅ</b> <code>{promo_id}</code><b>.</b>",
            parse_mode=HTML,
        )

    state = "ᴏɴ" if p.get("enabled") else "ᴏғғ"
    running = "ʀᴜɴɴɪɴɢ" if (
        _running_tasks.get(p["_id"])
        and not _running_tasks[p["_id"]].done()
    ) else "sᴛᴏᴘᴘᴇᴅ"
    last = p.get("last_post_at")
    last_str = last.strftime("%Y-%m-%d %H:%M:%S UTC") if last else "—"
    created = p.get("created_at")
    created_str = created.strftime("%Y-%m-%d %H:%M:%S UTC") if created else "—"

    await message.reply_text(
        f"<b>ᴘʀᴏᴍᴏ</b> <code>{promo_id}</code>\n\n"
        f"<b>ᴛᴀʀɢᴇᴛ:</b> <code>{_fmt_target(p['target_chat'])}</code>\n"
        f"<b>ɪɴᴛᴇʀᴠᴀʟ:</b> <code>{p.get('interval_minutes', 20)}</code> <b>ᴍɪɴᴜᴛᴇs</b>\n"
        f"<b>sᴛᴀᴛᴜs:</b> <code>{state}</code>\n"
        f"<b>ʟᴏᴏᴘ:</b> <code>{running}</code>\n"
        f"<b>ʟᴀsᴛ ᴘᴏsᴛ ɪᴅ:</b> <code>{p.get('last_post_id') or '—'}</code>\n"
        f"<b>ʟᴀsᴛ ᴘᴏsᴛ ᴀᴛ:</b> <code>{last_str}</code>\n"
        f"<b>ᴄʀᴇᴀᴛᴇᴅ:</b> <code>{created_str}</code>",
        parse_mode=HTML,
    )
