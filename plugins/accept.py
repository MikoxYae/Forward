import asyncio
import logging
import re

from pyrogram import Client, enums
from pyrogram.errors import FloodWait, UserAlreadyParticipant, RPCError, PeerIdInvalid
from pyrogram.types import ChatJoinRequest

from config import DEFAULT_WELCOME, NEW_REQ_MODE
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
    """Send welcome PM after approval.

    If the bot hasn't cached the user's peer yet (PEER_ID_INVALID) — which
    happens for old pending requests and sometimes for new ones too — we
    resolve the peer via get_chat_member (user is now in the chat, bot is
    admin so this always works) and retry once.
    """
    try:
        welcome_enabled = await db.get_chat_setting(chat.id, "welcome_enabled", True)
        if not welcome_enabled:
            return

        template = await db.get_chat_setting(chat.id, "welcome_text", None) or DEFAULT_WELCOME
        text = _format_welcome(template, user=user, chat=chat)

        try:
            await bot.send_message(
                chat_id=user.id,
                text=text,
                parse_mode=HTML,
                disable_web_page_preview=True,
            )
        except PeerIdInvalid:
            # Peer not in bot's cache — this happens when Pyrogram hasn't
            # finished storing the peer from the ChatJoinRequest update yet.
            # Wait briefly so Telegram can propagate the membership, then
            # resolve via get_chat_member (bot is admin → always works).
            log.debug(f"PEER_ID_INVALID for {user.id} — waiting 0.5s then resolving via get_chat_member")
            await asyncio.sleep(0.5)
            cm = await bot.get_chat_member(chat.id, user.id)
            resolved_user = cm.user if cm.user else user
            await bot.send_message(
                chat_id=resolved_user.id,
                text=_format_welcome(template, user=resolved_user, chat=chat),
                parse_mode=HTML,
                disable_web_page_preview=True,
            )

        log.info(f"welcome PM sent to {user.id} for chat {chat.id}")
    except Exception as e:
        log.warning(f"welcome PM to {user.id} not delivered: {e}")


@Client.on_chat_join_request()
async def auto_accept(bot: Client, request: ChatJoinRequest):
    if not NEW_REQ_MODE:
        return

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
