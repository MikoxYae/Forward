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
from pyrogram.raw import functions as raw_fn, types as raw_types
from pyrogram.types import Message

from config import APP_ID, API_HASH
from database.db import db
from plugins.accept import _send_welcome


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
        # ── PEER RESOLVE ────────────────────────────────────────────────────────
        # In-memory sessions have zero peer cache. get_chat() alone raises
        # PeerIdInvalid for numeric IDs. Use a 3-step fallback to populate
        # the cache before we touch the chat.
        chat = None
        resolve_err: str | None = None

        # Step 1: direct get_chat (works for usernames and cached peers)
        try:
            chat = await uc.get_chat(chat_ref)
        except Exception as e:
            resolve_err = str(e)

        # Step 2: raw GetChannels with access_hash=0 (numeric IDs only)
        if chat is None and isinstance(chat_ref, int):
            raw_ch_id = abs(chat_ref) - 10 ** 12
            try:
                await uc.invoke(
                    raw_fn.channels.GetChannels(
                        id=[raw_types.InputChannel(
                            channel_id=raw_ch_id,
                            access_hash=0,
                        )]
                    )
                )
                chat = await uc.get_chat(chat_ref)
            except Exception as e:
                resolve_err = str(e)

        # Step 3: walk dialogs — caches all peers the user is a member of
        if chat is None and isinstance(chat_ref, int):
            raw_ch_id = abs(chat_ref) - 10 ** 12
            try:
                async for dialog in uc.iter_dialogs():
                    cid = dialog.chat.id
                    if cid == chat_ref or abs(cid) - 10 ** 12 == raw_ch_id:
                        chat = dialog.chat
                        break
            except Exception as e:
                resolve_err = str(e)

        if chat is None:
            return await status.edit_text(
                f"<b>ᴄʜᴀᴛ ɴᴏᴛ ғᴏᴜɴᴅ ᴏʀ ɪɴᴀᴄᴄᴇssɪʙʟᴇ</b>\n\n"
                f"<code>{resolve_err}</code>\n\n"
                "<b>ᴍᴀᴋᴇ sᴜʀᴇ ʏᴏᴜʀ ʟᴏɢɢᴇᴅ-ɪɴ ᴀᴄᴄᴏᴜɴᴛ ɪs ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀᴛ.</b>",
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
        # NOTE: any user we cannot approve is simply LEFT in the pending
        # queue and logged. We never decline / remove anyone — the
        # decision is reversible (the user might leave a channel and
        # become approvable later, or it might be a transient API hiccup).
        approved = 0
        failed = 0
        saved = 0
        welcomed = 0
        last_edit = 0.0

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
                _approved_this_user = False
                try:
                    await uc.approve_chat_join_request(chat_id, user.id)
                    approved += 1
                    _approved_this_user = True
                except FloodWait as e:
                    log.warning(f"FloodWait {e.value}s while approving {user.id} in {chat_id}")
                    await asyncio.sleep(e.value + 1)
                    try:
                        await uc.approve_chat_join_request(chat_id, user.id)
                        approved += 1
                        _approved_this_user = True
                    except UserAlreadyParticipant:
                        approved += 1
                        _approved_this_user = True
                    except Exception as ee:
                        log.warning(f"approve retry failed for {user.id}: {ee}")
                        failed += 1
                except UserAlreadyParticipant:
                    # Already in the chat — count as success.
                    approved += 1
                    _approved_this_user = True
                except ChatAdminRequired:
                    # No point continuing — bail out cleanly.
                    raise
                except RPCError as e:
                    log.warning(f"approve failed for {user.id}: {e}")
                    failed += 1
                except Exception as e:
                    log.warning(f"approve unexpected for {user.id}: {e}")
                    failed += 1

                # Send welcome PM via bot (same message as auto_accept).
                # For pending/old requests the bot has never seen these users
                # in any update, so their access_hash is NOT in its peer cache.
                # Fix: call bot.get_chat_member() first — user is now in the
                # chat and bot is admin, so this always resolves the peer and
                # populates the cache. Then _send_welcome works normally.
                if _approved_this_user:
                    try:
                        try:
                            cm = await bot.get_chat_member(chat_id, user.id)
                            send_user = cm.user if cm.user else user
                        except Exception:
                            send_user = user
                        await _send_welcome(bot, chat, send_user)
                        welcomed += 1
                    except Exception as e:
                        log.debug(f"welcome skipped for {user.id}: {e}")

                # Live status update every ~2 seconds (Telegram rate-limits edits).
                now = time.time()
                if now - last_edit > 2:
                    try:
                        await status.edit_text(
                            f"<b>ᴄʜᴀᴛ:</b> <code>{chat_title}</code>\n"
                            f"<b>ᴀᴘᴘʀᴏᴠᴇᴅ:</b> <code>{approved}</code>  "
                            f"<b>ᴡᴇʟᴄᴏᴍᴇᴅ:</b> <code>{welcomed}</code>  "
                            f"<b>ғᴀɪʟᴇᴅ:</b> <code>{failed}</code>",
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
            text = (
                f"<b>✅ ᴅᴏɴᴇ</b>\n\n"
                f"<b>ᴄʜᴀᴛ:</b> <code>{chat_title}</code>\n"
                f"<b>ᴀᴘᴘʀᴏᴠᴇᴅ:</b> <code>{approved}</code>\n"
                f"<b>ᴡᴇʟᴄᴏᴍᴇ ᴘᴍ sᴇɴᴛ:</b> <code>{welcomed}</code>\n"
                f"<b>ғᴀɪʟᴇᴅ (ᴋᴇᴘᴛ ɪɴ ǫᴜᴇᴜᴇ):</b> <code>{failed}</code>\n"
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
