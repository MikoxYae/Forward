from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import OWNER
from database.db import db


START_TEXT = (
    "**Hello {mention}!**\n\n"
    "I am a **Forward Bot**. I can clone/forward media from one channel to another, "
    "even if the source channel has restricted/protected content.\n\n"
    "**How it works**\n"
    "1. Login with your Telegram account using /login\n"
    "2. Owner sets the source & destination channels using /settings\n"
    "3. Use /forward to start cloning\n\n"
    "**Commands**\n"
    "/login - Login with your Telegram account\n"
    "/logout - Remove your saved session\n"
    "/settings - (Owner only) Configure source & destination\n"
    "/forward - Start the forwarding\n"
    "/cancel - Cancel current login / operation\n"
    "/help - Show this help"
)


def _start_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Owner", url=f"https://t.me/{OWNER}")],
            [
                InlineKeyboardButton("Login", callback_data="help_login"),
                InlineKeyboardButton("Help", callback_data="help_main"),
            ],
        ]
    )


@Client.on_message(filters.command(["start", "help"]) & filters.private)
async def start_cmd(client, message: Message):
    await db.add_user(message.from_user.id, message.from_user.username)
    await message.reply_text(
        START_TEXT.format(mention=message.from_user.mention),
        reply_markup=_start_buttons(),
        disable_web_page_preview=True,
    )


@Client.on_callback_query(filters.regex("^help_main$"))
async def help_main_cb(client, query):
    await query.message.edit_text(
        START_TEXT.format(mention=query.from_user.mention),
        reply_markup=_start_buttons(),
        disable_web_page_preview=True,
    )
    await query.answer()


@Client.on_callback_query(filters.regex("^help_login$"))
async def help_login_cb(client, query):
    text = (
        "**How to login**\n\n"
        "1. Send /login\n"
        "2. Send your phone number with country code (e.g. `+919876543210`)\n"
        "3. Telegram will send an OTP to your account. Send it here with spaces\n"
        "    between digits (e.g. `1 2 3 4 5`) so Telegram does not invalidate it.\n"
        "4. If 2FA is enabled, send your password.\n\n"
        "Your session is stored securely so you don't need to login again.\n"
        "Use /logout anytime to remove it."
    )
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Back", callback_data="help_main")]]
        ),
    )
    await query.answer()
