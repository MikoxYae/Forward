import asyncio
import logging
import re

from pyrogram import Client, filters, enums
from pyrogram import Client as PyroClient
from pyrogram.errors import FloodWait, ChatAdminRequired, RPCError
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


async def _count_pending(uc: PyroClient, chat_id: int, hard_cap: int = 50000) -> int:
    n = 0
    try:
        async for _ in uc.get_chat_join_requests(chat_id):
            n += 1
            if n >= hard_cap:
                break
    except Exception as e:
        log.warning(f"_count_pending failed for {chat_id}: {e}")
    return n


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
            f"<b>ғᴇᴛᴄʜɪɴɢ + sᴀᴠɪɴɢ ᴘᴇɴᴅɪɴɢ ʀᴇǫᴜᴇsᴛs…</b>",
            parse_mode=HTML,
        )

        # Stage 1: enumerate pending requests, save each user to DB
        saved = 0
        try:
            async for req in uc.get_chat_join_requests(chat_id):
                user = req.user
                try:
                    await db.add_user(user.id, user.username, user.first_name)
                    saved += 1
                except Exception:
                    pass
                if saved % 200 == 0:
                    try:
                        await status.edit_text(
                            f"<b>ᴄʜᴀᴛ:</b> <code>{chat_title}</code>\n"
                            f"<b>sᴀᴠᴇᴅ ᴛᴏ ᴅʙ:</b> <code>{saved}</code>",
                            parse_mode=HTML,
                        )
                    except Exception:
                        pass
        except ChatAdminRequired:
            return await status.edit_text(
                "<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀᴛ "
                "(ᴏʀ ᴍɪssɪɴɢ \"ᴀᴅᴅ ᴍᴇᴍʙᴇʀs\" ᴘᴇʀᴍɪssɪᴏɴ).</b>",
                parse_mode=HTML,
            )
        except Exception as e:
            log.warning(f"fetch pending failed for {chat_id}: {e}")

        if saved == 0:
            return await status.edit_text(
                f"<b>ᴄʜᴀᴛ:</b> <code>{chat_title}</code>\n"
                f"<b>ɴᴏ ᴘᴇɴᴅɪɴɢ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs.</b>",
                parse_mode=HTML,
            )

        await status.edit_text(
            f"<b>ᴄʜᴀᴛ:</b> <code>{chat_title}</code>\n"
            f"<b>sᴀᴠᴇᴅ ᴛᴏ ᴅʙ:</b> <code>{saved}</code>\n"
            f"<b>ʙᴜʟᴋ-ᴀᴘᴘʀᴏᴠɪɴɢ…</b>",
            parse_mode=HTML,
        )

        # Stage 2: bulk approve in batches (each call approves up to ~100)
        # Loop a generous number of times with short sleeps; FloodWait safe.
        batches_needed = max(2, (saved // 100) + 3)
        for i in range(batches_needed):
            try:
                await uc.approve_all_chat_join_requests(chat_id)
            except FloodWait as e:
                log.warning(f"FloodWait {e.value}s during bulk approve batch {i}")
                await asyncio.sleep(e.value)
                try:
                    await uc.approve_all_chat_join_requests(chat_id)
                except Exception as ee:
                    log.warning(f"retry batch {i} failed: {ee}")
            except ChatAdminRequired:
                return await status.edit_text(
                    "<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ ᴡɪᴛʜ \"ᴀᴅᴅ ᴍᴇᴍʙᴇʀs\" ᴘᴇʀᴍɪssɪᴏɴ "
                    "ɪɴ ᴛʜᴀᴛ ᴄʜᴀᴛ.</b>",
                    parse_mode=HTML,
                )
            except RPCError as e:
                log.warning(f"bulk approve batch {i}: {e}")
                break

            if i % 3 == 0 and i > 0:
                try:
                    await status.edit_text(
                        f"<b>ᴄʜᴀᴛ:</b> <code>{chat_title}</code>\n"
                        f"<b>sᴀᴠᴇᴅ ᴛᴏ ᴅʙ:</b> <code>{saved}</code>\n"
                        f"<b>ʙᴜʟᴋ-ᴀᴘᴘʀᴏᴠɪɴɢ… ʙᴀᴛᴄʜ:</b> <code>{i + 1}/{batches_needed}</code>",
                        parse_mode=HTML,
                    )
                except Exception:
                    pass
            await asyncio.sleep(0.4)

        # Stage 3: verify how many actually remain
        await asyncio.sleep(1.5)
        remaining = await _count_pending(uc, chat_id, hard_cap=200)
        approved = max(0, saved - remaining)

        # Update counters
        if approved > 0:
            try:
                await db.increment_counter("approved_total", by=approved)
                await db.increment_counter(f"approved_chat:{chat_id}", by=approved)
            except Exception:
                pass

        await status.edit_text(
            f"<b>✅ ᴅᴏɴᴇ</b>\n\n"
            f"<b>ᴄʜᴀᴛ:</b> <code>{chat_title}</code>\n"
            f"<b>ʀᴇǫᴜᴇsᴛs ᴀᴘᴘʀᴏᴠᴇᴅ:</b> <code>{approved}</code>\n"
            f"<b>ʀᴇᴍᴀɪɴɪɴɢ ᴘᴇɴᴅɪɴɢ:</b> <code>{remaining}</code>\n"
            f"<b>ᴜsᴇʀs sᴀᴠᴇᴅ ᴛᴏ ᴅʙ:</b> <code>{saved}</code>\n\n"
            f"<b>ɴᴏᴛᴇ:</b> <b>ɴᴏ ᴡᴇʟᴄᴏᴍᴇ ᴘᴍ ɪs sᴇɴᴛ ʙʏ /approve. ᴛᴇʟᴇɢʀᴀᴍ ᴏɴʟʏ ʟᴇᴛs ᴛʜᴇ "
            f"ʙᴏᴛ ᴘᴍ ᴜsᴇʀs ᴡʜᴏ ʜᴀᴠᴇ /sᴛᴀʀᴛᴇᴅ ɪᴛ. ᴀʟʟ ᴀᴘᴘʀᴏᴠᴇᴅ ᴜsᴇʀs ᴀʀᴇ sᴀᴠᴇᴅ — ɪғ "
            f"ᴛʜᴇʏ /sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ʟᴀᴛᴇʀ, ғᴜᴛᴜʀᴇ /broadcast ʀᴇᴀᴄʜᴇs ᴛʜᴇᴍ.</b>",
            parse_mode=HTML,
        )
    finally:
        try:
            await uc.stop()
        except Exception:
            pass
