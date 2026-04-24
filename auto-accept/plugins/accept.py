import asyncio
import logging

from pyrogram import Client, enums
from pyrogram.errors import FloodWait, UserAlreadyParticipant, RPCError
from pyrogram.types import ChatJoinRequest

from config import ACCEPT_DELAY, DEFAULT_WELCOME
from database.db import db


HTML = enums.ParseMode.HTML
log = logging.getLogger("auto-accept.accept")


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


@Client.on_chat_join_request()
async def auto_accept(bot: Client, request: ChatJoinRequest):
    chat = request.chat
    user = request.from_user

    try:
        await db.add_chat(
            chat.id,
            title=getattr(chat, "title", None),
            username=getattr(chat, "username", None),
        )
    except Exception as e:
        log.warning(f"db.add_chat failed for {chat.id}: {e}")

    if ACCEPT_DELAY > 0:
        await asyncio.sleep(ACCEPT_DELAY)

    try:
        await bot.approve_chat_join_request(chat.id, user.id)
    except FloodWait as e:
        log.warning(f"FloodWait {e.value}s while approving {user.id} in {chat.id}")
        await asyncio.sleep(e.value)
        try:
            await bot.approve_chat_join_request(chat.id, user.id)
        except Exception as ee:
            log.error(f"approve retry failed for {user.id} in {chat.id}: {ee}")
            return
    except UserAlreadyParticipant:
        return
    except RPCError as e:
        log.error(f"approve failed for {user.id} in {chat.id}: {e}")
        return
    except Exception as e:
        log.error(f"approve unexpected error for {user.id} in {chat.id}: {e}")
        return

    try:
        await db.add_user(user.id, user.username, user.first_name)
    except Exception as e:
        log.warning(f"db.add_user failed for {user.id}: {e}")

    try:
        await db.increment_counter("approved_total")
        await db.increment_counter(f"approved_chat:{chat.id}")
    except Exception:
        pass

    welcome_enabled = await db.get_chat_setting(chat.id, "welcome_enabled", True)
    if not welcome_enabled:
        return

    template = await db.get_chat_setting(chat.id, "welcome_text", None)
    if not template:
        template = DEFAULT_WELCOME

    text = _format_welcome(template, user=user, chat=chat)

    try:
        await bot.send_message(
            chat_id=user.id,
            text=text,
            parse_mode=HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        log.info(f"welcome PM to {user.id} not delivered: {e}")
