import asyncio
import logging

from pyrogram import Client, filters, enums
from pyrogram.errors import (
    FloodWait,
    InputUserDeactivated,
    UserIsBlocked,
    PeerIdInvalid,
)
from pyrogram.raw import functions as raw_fn, types as raw_types
from pyrogram.types import Message

from config import OWNER_ID
from database.db import db


HTML = enums.ParseMode.HTML
log = logging.getLogger("miko.broadcast")


async def _resolve_hash_from_channels(bot: Client, user_id: int) -> int | None:
    """Try every known channel to fetch the user's access_hash via GetParticipant."""
    async for chat_doc in db.all_chats():
        chat_id = chat_doc["_id"]
        try:
            chat_peer = await bot.resolve_peer(chat_id)
            r = await bot.invoke(
                raw_fn.channels.GetParticipant(
                    channel=chat_peer,
                    participant=raw_types.InputUser(user_id=user_id, access_hash=0),
                )
            )
            raw_user = next((u for u in r.users if u.id == user_id), None)
            if raw_user and getattr(raw_user, "access_hash", None):
                return raw_user.access_hash
        except Exception:
            continue
    return None


async def _restore_peer_and_send(bot: Client, uid: int, user_doc: dict,
                                  fwd: Message) -> bool:
    """
    Two-step peer recovery:
    1. Try stored access_hash from DB.
    2. If missing, scan known channels via GetParticipant to fetch it live,
       then save it to DB so future broadcasts work without scanning.
    Returns True if message was sent.
    """
    access_hash = user_doc.get("access_hash") if user_doc else None

    # Step 2: no stored hash — try resolving from channels
    if not access_hash:
        access_hash = await _resolve_hash_from_channels(bot, uid)
        if access_hash:
            # Persist so we don't need to scan again next time
            await db.add_user(
                uid,
                user_doc.get("username") if user_doc else None,
                user_doc.get("first_name") if user_doc else None,
                access_hash=access_hash,
            )
            log.info(f"resolved and saved access_hash for {uid} via channel scan")

    if not access_hash:
        return False

    try:
        await bot.storage.update_peers([
            (
                uid,
                access_hash,
                "user",
                user_doc.get("username") if user_doc else None,
                None,
            )
        ])
        await fwd.copy(chat_id=uid)
        return True
    except Exception as e:
        log.info(f"broadcast peer-restore send failed for {uid}: {e}")
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
            # Peer cache expired — try DB hash then channel scan.
            ok = await _restore_peer_and_send(bot, uid, user_doc, fwd)
            if ok:
                sent += 1
            else:
                skipped += 1
                log.info(f"broadcast skip (peer unresolvable): {uid}")
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
        f"<b>sᴋɪᴘᴘᴇᴅ:</b> <code>{skipped}</code>\n"
        f"<b>ғᴀɪʟᴇᴅ:</b> <code>{failed}</code>\n"
        f"<b>ʀᴇᴍᴏᴠᴇᴅ ᴅᴇᴀᴅ ᴜsᴇʀs:</b> <code>{removed}</code>",
        parse_mode=HTML,
    )
