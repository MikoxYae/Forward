import asyncio
import logging
import re
import time

from pyrogram import Client, filters, enums
from pyrogram import Client as PyroClient
from pyrogram.errors import (
    FloodWait,
    ChatAdminRequired,
    UserAlreadyParticipant,
    RPCError,
)
from pyrogram.types import Message

from config import APP_ID, API_HASH
from database.db import db


HTML = enums.ParseMode.HTML
log = logging.getLogger("miko.approve")


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


@Client.on_message(filters.command("approve") & filters.private)
async def approve_cmd(bot: Client, message: Message):
    user_id = message.from_user.id

    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/approve &lt;ᴄʜᴀᴛ_ɪᴅ ᴏʀ @ᴜsᴇʀɴᴀᴍᴇ&gt;</code>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/approve -1001234567890</code>\n\n"
            "<b>ᴀᴘᴘʀᴏᴠᴇs ᴀʟʟ ᴘᴇɴᴅɪɴɢ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs ɪɴ ᴀ ᴄʜᴀɴɴᴇʟ / ɢʀᴏᴜᴘ "
            "ᴜsɪɴɢ ʏᴏᴜʀ ʟᴏɢɢᴇᴅ-ɪɴ sᴇssɪᴏɴ. ʏᴏᴜ ᴍᴜsᴛ ʙᴇ ᴀᴅᴍɪɴ ᴛʜᴇʀᴇ ᴡɪᴛʜ "
            "\"ᴀᴅᴅ ᴍᴇᴍʙᴇʀs\" ᴘᴇʀᴍɪssɪᴏɴ.</b>",
            parse_mode=HTML,
        )

    session_str = await db.get_session(user_id)
    if not session_str:
        return await message.reply_text(
            "<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ʟᴏɢɢᴇᴅ ɪɴ. ᴜsᴇ /login ғɪʀsᴛ.</b>",
            parse_mode=HTML,
        )

    chat_arg = " ".join(message.command[1:])
    chat_ref = _parse_chat(chat_arg)

    status = await message.reply_text(
        "<b>ᴄᴏɴɴᴇᴄᴛɪɴɢ ᴡɪᴛʜ ʏᴏᴜʀ sᴇssɪᴏɴ…</b>",
        parse_mode=HTML,
    )

    uc = PyroClient(
        name=f"approve_{user_id}",
        api_id=APP_ID,
        api_hash=API_HASH,
        session_string=session_str,
        in_memory=True,
    )

    try:
        await uc.start()
    except Exception as e:
        return await status.edit_text(
            f"<b>ғᴀɪʟᴇᴅ ᴛᴏ sᴛᴀʀᴛ sᴇssɪᴏɴ:</b> <code>{e}</code>",
            parse_mode=HTML,
        )

    try:
        try:
            chat = await uc.get_chat(chat_ref)
        except Exception as e:
            return await status.edit_text(
                f"<b>ᴄʜᴀᴛ ɴᴏᴛ ғᴏᴜɴᴅ ᴏʀ ɪɴᴀᴄᴄᴇssɪʙʟᴇ:</b> <code>{e}</code>",
                parse_mode=HTML,
            )

        chat_id = chat.id
        chat_title = getattr(chat, "title", None) or "ᴜɴᴋɴᴏᴡɴ"

        try:
            await db.add_chat(chat_id, title=chat_title, username=getattr(chat, "username", None))
        except Exception:
            pass

        await status.edit_text(
            f"<b>ᴄʜᴀᴛ:</b> <code>{chat_title}</code>\n"
            f"<b>ᴀᴘᴘʀᴏᴠɪɴɢ ᴘᴇɴᴅɪɴɢ ʀᴇǫᴜᴇsᴛs…</b>",
            parse_mode=HTML,
        )

        # Single stage: enumerate pending requests, save each user to DB
        # AND approve them one-by-one in the SAME loop.
        #
        # This avoids the bulk `approve_all_chat_join_requests` path which
        # was timing out with -503 on large pending lists. Per-user calls
        # are cheap individually and FloodWait is handled per call.
        #
        # Users we cannot approve (deactivated accounts, accounts that
        # are already in too many channels, etc.) are immediately declined
        # so they don't sit in the pending queue forever.
        approved = 0
        failed = 0
        declined = 0
        saved = 0
        last_edit = 0.0

        async def _safe_decline(uid: int):
            """Best-effort decline so a stuck user is removed from the
            pending list. Returns True if the decline call succeeded."""
            nonlocal declined
            try:
                await uc.decline_chat_join_request(chat_id, uid)
                declined += 1
                return True
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                try:
                    await uc.decline_chat_join_request(chat_id, uid)
                    declined += 1
                    return True
                except Exception as ee:
                    log.info(f"decline retry failed for {uid}: {ee}")
                    return False
            except Exception as e:
                log.info(f"decline failed for {uid}: {e}")
                return False

        try:
            async for req in uc.get_chat_join_requests(chat_id):
                user = req.user
                if not user:
                    continue

                # Save to DB right next to the approval — exactly what
                # the user asked for: "approve mea db mea save krte krte
                # he user ko approve kro".
                try:
                    await db.add_user(user.id, user.username, user.first_name)
                    saved += 1
                except Exception:
                    pass

                # Approve this single user.
                try:
                    await uc.approve_chat_join_request(chat_id, user.id)
                    approved += 1
                except FloodWait as e:
                    log.warning(f"FloodWait {e.value}s while approving {user.id} in {chat_id}")
                    await asyncio.sleep(e.value + 1)
                    try:
                        await uc.approve_chat_join_request(chat_id, user.id)
                        approved += 1
                    except UserAlreadyParticipant:
                        approved += 1
                    except Exception as ee:
                        log.warning(f"approve retry failed for {user.id}: {ee}")
                        failed += 1
                        await _safe_decline(user.id)
                except UserAlreadyParticipant:
                    # Already in the chat — count as success.
                    approved += 1
                except ChatAdminRequired:
                    # No point continuing — bail out cleanly.
                    raise
                except RPCError as e:
                    # Examples: INPUT_USER_DEACTIVATED, USER_CHANNELS_TOO_MUCH,
                    # PEER_ID_INVALID, etc. None of those are recoverable for
                    # this user, so clean them out of the pending list.
                    log.warning(f"approve failed for {user.id}: {e}")
                    failed += 1
                    await _safe_decline(user.id)
                except Exception as e:
                    log.warning(f"approve unexpected for {user.id}: {e}")
                    failed += 1
                    await _safe_decline(user.id)

                # Live status update every ~2 seconds (Telegram rate-limits edits).
                now = time.time()
                if now - last_edit > 2:
                    try:
                        await status.edit_text(
                            f"<b>ᴄʜᴀᴛ:</b> <code>{chat_title}</code>\n"
                            f"<b>ᴀᴘᴘʀᴏᴠᴇᴅ:</b> <code>{approved}</code>  "
                            f"<b>ᴅᴇᴄʟɪɴᴇᴅ:</b> <code>{declined}</code>  "
                            f"<b>ғᴀɪʟᴇᴅ:</b> <code>{failed - declined}</code>",
                            parse_mode=HTML,
                        )
                    except Exception:
                        pass
                    last_edit = now
        except ChatAdminRequired:
            return await status.edit_text(
                "<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀᴛ "
                "(ᴏʀ ᴍɪssɪɴɢ \"ᴀᴅᴅ ᴍᴇᴍʙᴇʀs\" ᴘᴇʀᴍɪssɪᴏɴ).</b>",
                parse_mode=HTML,
            )
        except Exception as e:
            log.warning(f"enumerate pending failed for {chat_id}: {e}")

        # Counters
        if approved > 0:
            try:
                await db.increment_counter("approved_total", by=approved)
                await db.increment_counter(f"approved_chat:{chat_id}", by=approved)
            except Exception:
                pass

        if approved == 0 and failed == 0:
            text = (
                f"<b>ᴄʜᴀᴛ:</b> <code>{chat_title}</code>\n"
                f"<b>ɴᴏ ᴘᴇɴᴅɪɴɢ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs.</b>"
            )
        else:
            still_failed = max(0, failed - declined)
            text = (
                f"<b>✅ ᴅᴏɴᴇ</b>\n\n"
                f"<b>ᴄʜᴀᴛ:</b> <code>{chat_title}</code>\n"
                f"<b>ᴀᴘᴘʀᴏᴠᴇᴅ:</b> <code>{approved}</code>\n"
                f"<b>ᴅᴇᴄʟɪɴᴇᴅ (ᴅᴇᴀᴄᴛɪᴠᴀᴛᴇᴅ / ʟɪᴍɪᴛ-ʜɪᴛ):</b> <code>{declined}</code>\n"
                f"<b>sᴛɪʟʟ ғᴀɪʟᴇᴅ:</b> <code>{still_failed}</code>\n"
                f"<b>ᴜsᴇʀs sᴀᴠᴇᴅ ᴛᴏ ᴅʙ:</b> <code>{saved}</code>"
            )

        try:
            await status.edit_text(text, parse_mode=HTML)
        except Exception:
            await message.reply_text(text, parse_mode=HTML)
    finally:
        try:
            await uc.stop()
        except Exception:
            pass
