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
        # Failure handling:
        #   * INPUT_USER_DEACTIVATED  -> account is permanently gone, decline.
        #   * USER_ID_INVALID         -> Telegram cannot resolve this user
        #                                via our session, decline.
        #   * PEER_ID_INVALID         -> same as above, decline.
        #   * USER_CHANNELS_TOO_MUCH  -> user is in too many channels right
        #                                now, but they might leave some
        #                                later. Leave them in the queue.
        #   * any other RPCError      -> log and skip (do NOT decline) so
        #                                we never silently throw away a
        #                                real user just because of a
        #                                transient API hiccup.
        approved = 0
        skipped_full = 0   # USER_CHANNELS_TOO_MUCH — kept in queue
        declined = 0       # auto-removed from queue (dead / invalid)
        other_failed = 0   # logged only, kept in queue
        saved = 0
        last_edit = 0.0

        # Errors that mean "this user can never be approved by anyone, ever".
        DEAD_ERRORS = (
            "USER_DEACTIVATED",
            "INPUT_USER_DEACTIVATED",
            "USER_ID_INVALID",
            "PEER_ID_INVALID",
        )

        def _is_dead(err: Exception) -> bool:
            s = str(err).upper()
            return any(code in s for code in DEAD_ERRORS)

        def _is_full(err: Exception) -> bool:
            return "USER_CHANNELS_TOO_MUCH" in str(err).upper()

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

        async def _handle_failure(uid: int, err: Exception):
            """Decide what to do with a user that couldn't be approved."""
            nonlocal skipped_full, other_failed
            if _is_full(err):
                # Don't kick them out — they might join after leaving
                # some other channel.
                skipped_full += 1
            elif _is_dead(err):
                # Truly broken account — clean it out of the queue.
                await _safe_decline(uid)
            else:
                # Unknown/transient error — keep them, log it, retry later.
                other_failed += 1

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
                        await _handle_failure(user.id, ee)
                except UserAlreadyParticipant:
                    # Already in the chat — count as success.
                    approved += 1
                except ChatAdminRequired:
                    # No point continuing — bail out cleanly.
                    raise
                except RPCError as e:
                    log.warning(f"approve failed for {user.id}: {e}")
                    await _handle_failure(user.id, e)
                except Exception as e:
                    log.warning(f"approve unexpected for {user.id}: {e}")
                    await _handle_failure(user.id, e)

                # Live status update every ~2 seconds (Telegram rate-limits edits).
                now = time.time()
                if now - last_edit > 2:
                    try:
                        await status.edit_text(
                            f"<b>ᴄʜᴀᴛ:</b> <code>{chat_title}</code>\n"
                            f"<b>ᴀᴘᴘʀᴏᴠᴇᴅ:</b> <code>{approved}</code>  "
                            f"<b>sᴋɪᴘᴘᴇᴅ (ғᴜʟʟ):</b> <code>{skipped_full}</code>  "
                            f"<b>ᴅᴇᴄʟɪɴᴇᴅ (ᴅᴇᴀᴅ):</b> <code>{declined}</code>",
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

        # Total failures = everything we didn't approve.
        failed = skipped_full + declined + other_failed

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
            text = (
                f"<b>✅ ᴅᴏɴᴇ</b>\n\n"
                f"<b>ᴄʜᴀᴛ:</b> <code>{chat_title}</code>\n"
                f"<b>ᴀᴘᴘʀᴏᴠᴇᴅ:</b> <code>{approved}</code>\n"
                f"<b>sᴋɪᴘᴘᴇᴅ (ᴜsᴇʀ ɪɴ ᴛᴏᴏ ᴍᴀɴʏ ᴄʜᴀɴɴᴇʟs — ᴋᴇᴘᴛ ɪɴ ǫᴜᴇᴜᴇ):</b> <code>{skipped_full}</code>\n"
                f"<b>ᴅᴇᴄʟɪɴᴇᴅ (ᴅᴇᴀᴅ / ɪɴᴠᴀʟɪᴅ ᴀᴄᴄᴏᴜɴᴛs):</b> <code>{declined}</code>\n"
                f"<b>ᴏᴛʜᴇʀ ғᴀɪʟᴜʀᴇs (ᴋᴇᴘᴛ ɪɴ ǫᴜᴇᴜᴇ):</b> <code>{other_failed}</code>\n"
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
