from pyrogram import Client, filters
from pyrogram.types import Message

from database.db import db


@Client.on_message(filters.command("settings") & filters.private)
async def settings_cmd(client, message: Message):
    user_id = message.from_user.id
    source = await db.get_user_setting(user_id, "source")
    dest = await db.get_user_setting(user_id, "destination")
    text = (
        "**Your Settings**\n\n"
        f"**Source:** `{source or 'Not set'}`\n"
        f"**Destination:** `{dest or 'Not set'}`\n\n"
        "**Commands**\n"
        "/setsource <channel_id_or_username>\n"
        "/setdest <channel_id_or_username>\n"
        "/clearsettings"
    )
    await message.reply_text(text)


@Client.on_message(filters.command("setsource") & filters.private)
async def set_source_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "Usage: `/setsource <channel_id_or_username>`\n"
            "Example: `/setsource @mychannel` or `/setsource -1001234567890`"
        )
    val = message.command[1]
    await db.set_user_setting(message.from_user.id, "source", val)
    await message.reply_text(f"Source channel set to: `{val}`")


@Client.on_message(filters.command("setdest") & filters.private)
async def set_dest_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "Usage: `/setdest <channel_id_or_username>`\n"
            "Example: `/setdest @mychannel` or `/setdest -1001234567890`"
        )
    val = message.command[1]
    await db.set_user_setting(message.from_user.id, "destination", val)
    await message.reply_text(f"Destination channel set to: `{val}`")


@Client.on_message(filters.command("clearsettings") & filters.private)
async def clear_settings_cmd(client, message: Message):
    user_id = message.from_user.id
    await db.clear_user_setting(user_id, "source")
    await db.clear_user_setting(user_id, "destination")
    await message.reply_text("Your settings have been cleared.")
