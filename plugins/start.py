from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import OWNER
from database.db import db


START_TEXT = (
    "**Hello {mention}!**\n\n"
    "I am a **Forward Bot**. I can clone media from one channel to another, "
    "even if the source channel has restricted/protected content.\n\n"
    "**How to use**\n"
    "1. /login - login with your Telegram account\n"
    "2. /setsource <channel> - set source channel\n"
    "3. /setdest <channel> - set destination channel\n"
    "4. /forward - start forwarding\n\n"
    "**All commands**\n"
    "/login - Login with your Telegram account\n"
    "/logout - Remove your saved session\n"
    "/setsource <channel> - Set source channel\n"
    "/setdest <channel> - Set destination channel\n"
    "/settings - View your current source & destination\n"
    "/clearsettings - Clear your source & destination\n"
    "/forward - Start the forwarding\n"
    "/cancel - Cancel current login / operation\n"
    "/help - Show this help"
)


@Client.on_message(filters.command(["start", "help"]) & filters.private)
async def start_cmd(client, message: Message):
    await db.add_user(message.from_user.id, message.from_user.username)
    btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Owner", url=f"https://t.me/{OWNER}")]]
    )
    await message.reply_text(
        START_TEXT.format(mention=message.from_user.mention),
        reply_markup=btn,
        disable_web_page_preview=True,
    )
