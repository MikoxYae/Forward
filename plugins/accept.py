import asyncio
import logging
import re

from pyrogram import Client, enums
from pyrogram.errors import FloodWait, UserAlreadyParticipant, RPCError
from pyrogram.types import ChatJoinRequest

from config import DEFAULT_WELCOME
from database.db import db


HTML = enums.ParseMode.HTML
log = logging.getLogger("miko.accept")

# Semaphore: allow up to 15 concurrent approvals (fast but safe)
_approve_sem = asyncio.Semaphore(15)

# Keep strong references to background tasks so the GC doesn't kill them
# before they finish (Python event loop only holds *weak* refs to tasks).
_bg_tasks: set = set()


def _bg(coro) -> asyncio.Task:
    """Schedule a fire-and-forget coroutine, keeping a strong reference."""
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


def _chat_link(chat) -> str:
    if getattr(chat, "username", None):
        return f"https://t.me/{chat.username}"
    return ""


def _format_welcome(template: str, *, user, chat) -> str:
    chat_title = getattr(chat, "title", "") or ""
    raw_link = _chat_link(chat)
    mention = user.mention if user else "ᴜsᴇʀ"
    first_name = (user.first_name if user else "") or ""
    username = ("@" + user.username) if (user and user.username) else mention

    result = (
        template.replace("{mention}", mention)
        .replace("{first_name}", first_name)
        .replace("{username}", username)
        .replace("{chat_title}", chat_title)
        .replace("{chat_link}", raw_link if raw_link else "#")
        .replace("{user_id}", str(user.id) if user else "")
    )

    # Private channel — strip broken <a href="#"> so Telegram won't reject
    if not raw_link:
        result = re.sub(r'<a\s+href="#"[^>]*>(.*?)</a>', r'\1', result, flags=re.DOTALL)

    return result


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
    """Send welcome PM immediately after approval.

    Called inline (not in a background task) so Pyrogram's peer cache for
    the user — populated when the ChatJoinRequest update arrived — is still
    warm and resolve_peer(user.id) will succeed.
    """
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
        log.info(f"welcome PM sent to {user.id} for chat {chat.id}")
    except Exception as e:
        log.warning(f"welcome PM to {user.id} not delivered: {e}")


@Client.on_chat_join_request()
async def auto_accept(bot: Client, request: ChatJoinRequest):
    chat = request.chat
    user = request.from_user

    # Save chat to DB (non-blocking, fire-and-forget — use _bg to hold reference)
    _bg(_save_chat(chat))

    # Check the requesting user's Auto Accept preference.
    # Wrap in try/except so a MongoDB error never blocks the approval flow.
    try:
        user_pref = await db.get_user_setting(user.id, "auto_accept_enabled")
    except Exception as e:
        log.warning(f"get_user_setting failed for {user.id}: {e} — proceeding")
        user_pref = None

    if user_pref is False:
        log.info(f"auto_accept skipped for {user.id} (user opted out)")
        return

    # Approve the user
    approved = await _do_approve(bot, chat.id, user.id)
    if not approved:
        return

    # ── Send welcome PM inline ──────────────────────────────────────────────
    # IMPORTANT: must be awaited here (not via create_task) so that Pyrogram's
    # peer cache — populated from the ChatJoinRequest update — is still valid.
    # Moving this into a background task causes PeerIdInvalid errors because
    # the task may run after the peer entry ages out of the in-memory cache.
    await _send_welcome(bot, chat, user)

    # DB saves and counters are non-critical — run them in the background.
    _bg(_save_user_and_counters(chat, user))


async def _save_chat(chat):
    try:
        await db.add_chat(
            chat.id,
            title=getattr(chat, "title", None),
            username=getattr(chat, "username", None),
        )
    except Exception as e:
        log.warning(f"db.add_chat failed for {chat.id}: {e}")


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
