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


async def _try_send_with_hash(bot: Client, user_id: int, user_doc: dict,
                               message: Message) -> bool:
    """Restore access_hash from DB into Pyrogram storage and retry copy."""
    access_hash = user_doc.get("access_hash") if user_doc else None
    if not access_hash:
        return False
    try:
        await bot.storage.update_peers([
            (
                user_id,
                access_hash,
                "user",
                user_doc.get("username"),
                None,
            )
        ])
        await message.copy(chat_id=user_id)
        return True
    except Exception as e:
        log.info(f"broadcast hash-retry failed for {user_id}: {e}")
        return False


@Client.on_message(filters.command("broadcast") & filters.private)
async def broadcast_cmd(bot: Client, message: Message):
    user_id = message.from_user.id
    if int(user_id) != int(OWNER_ID) and not await db.is_admin(user_id):
        return await message.reply_text(
            "<b>ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴛʜᴇ ᴏᴡɴᴇʀ ᴀɴᴅ ᴀᴅᴍɪɴs.</b>",
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

    sent = failed = skipped = removed = 0
    total = await db.total_users()
    last_edit = 0
    fwd = message.reply_to_message

    async for user_doc in db.all_users():
        uid = user_doc["_id"]
        try:
            await fwd.copy(chat_id=uid)
            sent += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await fwd.copy(chat_id=uid)
                sent += 1
            except Exception:
                failed += 1
        except (InputUserDeactivated, UserIsBlocked):
            # Truly unreachable — account deleted or bot blocked.
            await db.remove_user(uid)
            removed += 1
        except PeerIdInvalid:
            # Peer cache expired. Try restoring access_hash from DB.
            ok = await _try_send_with_hash(bot, uid, user_doc, fwd)
            if ok:
                sent += 1
            else:
                skipped += 1
                log.info(f"broadcast skip (no resolvable peer): {uid}")
        except Exception as e:
            log.warning(f"broadcast to {uid} failed: {e}")
            failed += 1

        done = sent + failed + skipped + removed
        if done - last_edit >= 25 or done == total:
            last_edit = done
            try:
                await status.edit_text(
                    f"<b>ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ…</b>\n\n"
                    f"<b>ᴘʀᴏɢʀᴇss:</b> <code>{done}/{total}</code>\n"
                    f"<b>sᴇɴᴛ:</b> <code>{sent}</code>\n"
                    f"<b>sᴋɪᴘᴘᴇᴅ:</b> <code>{skipped}</code>\n"
                    f"<b>ғᴀɪʟᴇᴅ:</b> <code>{failed}</code>\n"
                    f"<b>ʀᴇᴍᴏᴠᴇᴅ:</b> <code>{removed}</code>",
                    parse_mode=HTML,
                )
            except Exception:
                pass

    await status.edit_text(
        f"<b>ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇ.</b>\n\n"
        f"<b>sᴇɴᴛ:</b> <code>{sent}</code>\n"
        f"<b>sᴋɪᴘᴘᴇᴅ (ɴᴏ ᴘᴇᴇʀ):</b> <code>{skipped}</code>\n"
        f"<b>ғᴀɪʟᴇᴅ:</b> <code>{failed}</code>\n"
        f"<b>ʀᴇᴍᴏᴠᴇᴅ ᴅᴇᴀᴅ ᴜsᴇʀs:</b> <code>{removed}</code>",
        parse_mode=HTML,
    )
