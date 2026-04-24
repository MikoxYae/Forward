from pyrogram import Client, filters, enums
from pyrogram.types import Message

from config import OWNER_ID
from database.db import db


HTML = enums.ParseMode.HTML


@Client.on_message(filters.command("stats") & filters.private)
async def stats_cmd(bot: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text(
            "<b>ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴛʜᴇ ᴏᴡɴᴇʀ.</b>",
            parse_mode=HTML,
        )

    total_users = await db.total_users()
    total_chats = await db.total_chats()
    approved_total = await db.get_counter("approved_total")

    await message.reply_text(
        "<b>ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs</b>\n\n"
        f"<b>ᴜsᴇʀs:</b> <code>{total_users}</code>\n"
        f"<b>ᴄʜᴀᴛs:</b> <code>{total_chats}</code>\n"
        f"<b>ᴛᴏᴛᴀʟ ʀᴇǫᴜᴇsᴛs ᴀᴄᴄᴇᴘᴛᴇᴅ:</b> <code>{approved_total}</code>",
        parse_mode=HTML,
    )


@Client.on_message(filters.command("chats") & filters.private)
async def chats_cmd(bot: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text(
            "<b>ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴛʜᴇ ᴏᴡɴᴇʀ.</b>",
            parse_mode=HTML,
        )

    lines = ["<b>ᴄʜᴀᴛs ᴡʜᴇʀᴇ ʙᴏᴛ ʜᴀs sᴇᴇɴ ᴀ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ:</b>", ""]
    count = 0
    async for c in db.all_chats():
        title = c.get("title") or "ᴜɴᴋɴᴏᴡɴ"
        username = c.get("username")
        approved = await db.get_counter(f"approved_chat:{c['_id']}")
        suffix = f" (@{username})" if username else ""
        lines.append(
            f"• <code>{c['_id']}</code> — <b>{title}</b>{suffix} — "
            f"<code>{approved}</code> ᴀᴄᴄᴇᴘᴛᴇᴅ"
        )
        count += 1
        if count >= 50:
            lines.append("<b>… ᴛʀᴜɴᴄᴀᴛᴇᴅ ᴀᴛ 50 ᴄʜᴀᴛs.</b>")
            break

    if count == 0:
        lines.append("<b>ɴᴏ ᴄʜᴀᴛs ʏᴇᴛ.</b>")

    await message.reply_text("\n".join(lines), parse_mode=HTML)
