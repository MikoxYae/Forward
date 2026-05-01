import asyncio
import logging

from pyrogram import Client, enums
from pyrogram.errors import FloodWait, UserAlreadyParticipant, RPCError
from pyrogram.types import ChatJoinRequest

from config import DEFAULT_WELCOME
from database.db import db


HTML = enums.ParseMode.HTML
log = logging.getLogger("miko.accept")

# Semaphore: allow up to 15 concurrent approvals (fast but safe)
_approve_sem = asyncio.Semaphore(15)


def _chat_link(chat) -> str:
    if getattr(chat, "username", None):
        return f"https://t.me/{chat.username}"
    return ""


def _format_welcome(template: str, *, user, chat) -> str:
    chat_title = getattr(chat, "title", "") or ""
    chat_link = _chat_link(chat) or "#"
    mention = user.mention if user else "ᴜsᴇʀ"
    first_name = (user.first_name if user else "") or ""
    username = ("@" + user.username) if (user and user.username) else mention
    return (
        template.replace("{mention}", mention)
        .replace("{first_name}", first_name)
        .replace("{username}", username)
        .replace("{chat_title}", chat_title)
        .replace("{chat_link}", chat_link)
        .replace("{user_id}", str(user.id) if user else "")
    )


async def _do_approve(bot: Client, chat_id: int, user_id: int) -> bool:
    """Approve a single user with FloodWait handling. Returns True on success."""
    async with _approve_sem:
        for attempt in range(3):
            try:
                await bot.approve_chat_join_request(chat_id, user_id)
                return True
            except FloodWait as e:
                wait = e.value + 1
                log.warning(f"FloodWait {wait}s approving {user_id} in {chat_id}")
                await asyncio.sleep(wait)
            except UserAlreadyParticipant:
                return True
            except RPCError as e:
                log.error(f"approve failed for {user_id} in {chat_id}: {e}")
                return False
            except Exception as e:
                log.error(f"approve unexpected for {user_id} in {chat_id}: {e}")
                return False
        return False


async def _send_welcome(bot: Client, chat, user):
    """Fire-and-forget welcome PM after approval."""
    try:
        welcome_enabled = await db.get_chat_setting(chat.id, "welcome_enabled", True)
        if not welcome_enabled:
            return

        template = await db.get_chat_setting(chat.id, "welcome_text", None) or DEFAULT_WELCOME
        text = _format_welcome(template, user=user, chat=chat)

        await bot.send_message(
            chat_id=user.id,
            text=text,
            parse_mode=HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        log.info(f"welcome PM to {user.id} not delivered: {e}")


@Client.on_chat_join_request()
async def auto_accept(bot: Client, request: ChatJoinRequest):
    chat = request.chat
    user = request.from_user

    # Save chat to DB (non-blocking, fire-and-forget)
    asyncio.create_task(_save_chat(chat))

    # Approve immediately — no delay, no waiting for DB
    approved = await _do_approve(bot, chat.id, user.id)
    if not approved:
        return

    # Post-approval tasks run concurrently in background
    asyncio.create_task(_post_approve(bot, chat, user))


async def _save_chat(chat):
    try:
        await db.add_chat(
            chat.id,
            title=getattr(chat, "title", None),
            username=getattr(chat, "username", None),
        )
    except Exception as e:
        log.warning(f"db.add_chat failed for {chat.id}: {e}")


async def _post_approve(bot: Client, chat, user):
    """Run DB saves, counters, and welcome PM concurrently after approval."""
    await asyncio.gather(
        _save_user_and_counters(chat, user),
        _send_welcome(bot, chat, user),
        return_exceptions=True,
    )


async def _save_user_and_counters(chat, user):
    try:
        await db.add_user(user.id, user.username, user.first_name)
    except Exception as e:
        log.warning(f"db.add_user failed for {user.id}: {e}")
    try:
        await asyncio.gather(
            db.increment_counter("approved_total"),
            db.increment_counter(f"approved_chat:{chat.id}"),
            return_exceptions=True,
        )
    except Exception:
        pass
