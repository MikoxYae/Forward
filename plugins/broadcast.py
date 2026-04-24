import asyncio
import logging

from pyrogram import Client, filters, enums
from pyrogram.errors import (
    FloodWait,
    InputUserDeactivated,
    UserIsBlocked,
    PeerIdInvalid,
)
from pyrogram.types import Message

from config import OWNER_ID
from database.db import db


HTML = enums.ParseMode.HTML
log = logging.getLogger("miko.broadcast")


@Client.on_message(filters.command("broadcast") & filters.private)
async def broadcast_cmd(bot: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text(
            "<b>ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴛʜᴇ ᴏᴡɴᴇʀ.</b>",
            parse_mode=HTML,
        )

    if not message.reply_to_message:
        return await message.reply_text(
            "<b>ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴡɪᴛʜ</b> <code>/broadcast</code> "
            "<b>ᴛᴏ sᴇɴᴅ ɪᴛ ᴛᴏ ᴀʟʟ ᴜsᴇʀs.</b>",
            parse_mode=HTML,
        )

    status = await message.reply_text(
        "<b>sᴛᴀʀᴛɪɴɢ ʙʀᴏᴀᴅᴄᴀsᴛ…</b>", parse_mode=HTML
    )

    sent = failed = removed = 0
    total = await db.total_users()
    last_edit = 0

    async for user_doc in db.all_users():
        user_id = user_doc["_id"]
        try:
            await message.reply_to_message.copy(chat_id=user_id)
            sent += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await message.reply_to_message.copy(chat_id=user_id)
                sent += 1
            except Exception:
                failed += 1
        except (InputUserDeactivated, UserIsBlocked, PeerIdInvalid):
            await db.remove_user(user_id)
            removed += 1
        except Exception as e:
            log.warning(f"broadcast to {user_id} failed: {e}")
            failed += 1

        done = sent + failed + removed
        if done - last_edit >= 25 or done == total:
            last_edit = done
            try:
                await status.edit_text(
                    f"<b>ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ…</b>\n\n"
                    f"<b>ᴘʀᴏɢʀᴇss:</b> <code>{done}/{total}</code>\n"
                    f"<b>sᴇɴᴛ:</b> <code>{sent}</code>\n"
                    f"<b>ғᴀɪʟᴇᴅ:</b> <code>{failed}</code>\n"
                    f"<b>ʀᴇᴍᴏᴠᴇᴅ:</b> <code>{removed}</code>",
                    parse_mode=HTML,
                )
            except Exception:
                pass

    await status.edit_text(
        f"<b>ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇ.</b>\n\n"
        f"<b>sᴇɴᴛ:</b> <code>{sent}</code>\n"
        f"<b>ғᴀɪʟᴇᴅ:</b> <code>{failed}</code>\n"
        f"<b>ʀᴇᴍᴏᴠᴇᴅ ᴅᴇᴀᴅ ᴜsᴇʀs:</b> <code>{removed}</code>",
        parse_mode=HTML,
    )
