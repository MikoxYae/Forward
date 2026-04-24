from pyrogram import Client, filters, enums
from pyrogram.types import Message

from database.db import db


@Client.on_message(filters.command("settings") & filters.private)
async def settings_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    source = await db.get_user_setting(user_id, "source")
    dest = await db.get_user_setting(user_id, "destination")
    text = (
        "<b>ʏᴏᴜʀ sᴇᴛᴛɪɴɢs</b>\n\n"
        f"<b>sᴏᴜʀᴄᴇ:</b> <code>{source or 'ɴᴏᴛ sᴇᴛ'}</code>\n"
        f"<b>ᴅᴇsᴛɪɴᴀᴛɪᴏɴ:</b> <code>{dest or 'ɴᴏᴛ sᴇᴛ'}</code>\n\n"
        "<b>ᴄᴏᴍᴍᴀɴᴅs</b>\n"
        "<b>/setsource &lt;ᴄʜᴀɴɴᴇʟ_ɪᴅ_ᴏʀ_ᴜsᴇʀɴᴀᴍᴇ&gt;</b>\n"
        "<b>/setdest &lt;ᴄʜᴀɴɴᴇʟ_ɪᴅ_ᴏʀ_ᴜsᴇʀɴᴀᴍᴇ&gt;</b>\n"
        "<b>/clearsettings</b>"
    )
    await message.reply_text(text, parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command("setsource") & filters.private)
async def set_source_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/setsource &lt;channel_id_or_username&gt;</code>\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/setsource @mychannel</code> "
            "<b>ᴏʀ</b> <code>/setsource -1001234567890</code>",
            parse_mode=enums.ParseMode.HTML,
        )
    val = message.command[1]
    await db.set_user_setting(message.from_user.id, "source", val)
    await message.reply_text(
        f"<b>sᴏᴜʀᴄᴇ ᴄʜᴀɴɴᴇʟ sᴇᴛ ᴛᴏ:</b> <code>{val}</code>",
        parse_mode=enums.ParseMode.HTML,
    )


@Client.on_message(filters.command("setdest") & filters.private)
async def set_dest_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/setdest &lt;channel_id_or_username&gt;</code>\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/setdest @mychannel</code> "
            "<b>ᴏʀ</b> <code>/setdest -1001234567890</code>",
            parse_mode=enums.ParseMode.HTML,
        )
    val = message.command[1]
    await db.set_user_setting(message.from_user.id, "destination", val)
    await message.reply_text(
        f"<b>ᴅᴇsᴛɪɴᴀᴛɪᴏɴ ᴄʜᴀɴɴᴇʟ sᴇᴛ ᴛᴏ:</b> <code>{val}</code>",
        parse_mode=enums.ParseMode.HTML,
    )


@Client.on_message(filters.command("clearsettings") & filters.private)
async def clear_settings_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    await db.clear_user_setting(user_id, "source")
    await db.clear_user_setting(user_id, "destination")
    await message.reply_text(
        "<b>ʏᴏᴜʀ sᴇᴛᴛɪɴɢs ʜᴀᴠᴇ ʙᴇᴇɴ ᴄʟᴇᴀʀᴇᴅ.</b>",
        parse_mode=enums.ParseMode.HTML,
    )
