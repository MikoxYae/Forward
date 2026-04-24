from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from config import OWNER, START_PIC
from database.db import db


HTML = enums.ParseMode.HTML


START_TEXT = (
    "<b>ʜᴇʟʟᴏ {mention} 👋</b>\n\n"
    "<b>ɪ ᴀᴍ ᴀɴ ᴀᴜᴛᴏ-ᴀᴄᴄᴇᴘᴛ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ ʙᴏᴛ.</b>\n"
    "<b>ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ᴄʜᴀɴɴᴇʟ ᴏʀ ɢʀᴏᴜᴘ ᴀs ᴀᴅᴍɪɴ ᴡɪᴛʜ \"ᴀᴅᴅ ᴍᴇᴍʙᴇʀs\" ᴘᴇʀᴍɪssɪᴏɴ.</b>\n"
    "<b>ᴀʟʟ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴀᴄᴄᴇᴘᴛᴇᴅ.</b>"
)

HELP_TEXT = (
    "<b>ʜᴏᴡ ᴛᴏ ᴜsᴇ:</b>\n\n"
    "<b>1. ᴇɴᴀʙʟᴇ \"ᴀᴘᴘʀᴏᴠᴇ ɴᴇᴡ ᴍᴇᴍʙᴇʀs\" ɪɴ ʏᴏᴜʀ ᴄʜᴀɴɴᴇʟ / ɢʀᴏᴜᴘ.</b>\n"
    "<b>2. ᴀᴅᴅ ᴛʜɪs ʙᴏᴛ ᴀs ᴀɴ ᴀᴅᴍɪɴ ᴡɪᴛʜ \"ᴀᴅᴅ ᴍᴇᴍʙᴇʀs\" ᴘᴇʀᴍɪssɪᴏɴ.</b>\n"
    "<b>3. ᴅᴏɴᴇ — ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏ-ᴀᴄᴄᴇᴘᴛᴇᴅ.</b>\n\n"
    "<b>ᴄᴏᴍᴍᴀɴᴅs:</b>\n"
    "<code>/start</code> — <b>sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ</b>\n"
    "<code>/help</code> — <b>sʜᴏᴡ ᴛʜɪs ʜᴇʟᴘ</b>\n"
    "<code>/setwelcome</code> — <b>(ᴄʜᴀᴛ) sᴇᴛ ᴄᴜsᴛᴏᴍ ᴡᴇʟᴄᴏᴍᴇ ᴍᴇssᴀɢᴇ</b>\n"
    "<code>/clearwelcome</code> — <b>(ᴄʜᴀᴛ) ʀᴇsᴇᴛ ᴛᴏ ᴅᴇғᴀᴜʟᴛ</b>\n"
    "<code>/togglewelcome</code> — <b>(ᴄʜᴀᴛ) ᴛᴜʀɴ ᴡᴇʟᴄᴏᴍᴇ ᴘᴍ ᴏɴ / ᴏғғ</b>\n"
    "<code>/stats</code> — <b>(ᴏᴡɴᴇʀ) ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs</b>\n"
    "<code>/broadcast</code> — <b>(ᴏᴡɴᴇʀ) ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ sᴇɴᴅ ɪᴛ ᴛᴏ ᴀʟʟ ᴜsᴇʀs</b>"
)


def start_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="ᴀᴅᴅ ᴍᴇ ᴛᴏ ᴄʜᴀɴɴᴇʟ",
                url=f"https://t.me/{bot_username}?startchannel=true",
            ),
            InlineKeyboardButton(
                text="ᴀᴅᴅ ᴍᴇ ᴛᴏ ɢʀᴏᴜᴘ",
                url=f"https://t.me/{bot_username}?startgroup=true",
            ),
        ],
        [
            InlineKeyboardButton(text="ʜᴇʟᴘ", callback_data="show_help"),
            InlineKeyboardButton(text="ᴀʙᴏᴜᴛ", callback_data="show_about"),
        ],
    ]
    if OWNER:
        rows.append(
            [InlineKeyboardButton(text="ᴏᴡɴᴇʀ", url=f"https://t.me/{OWNER}")]
        )
    return InlineKeyboardMarkup(rows)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="« ʙᴀᴄᴋ", callback_data="back_home")]]
    )


@Client.on_message(filters.command(["start", "help"]) & filters.private)
async def start_cmd(bot: Client, message: Message):
    user = message.from_user
    if user:
        await db.add_user(user.id, user.username, user.first_name)

    me = await bot.get_me()
    text = START_TEXT.format(mention=user.mention if user else "ᴜsᴇʀ")

    if message.command and message.command[0] == "help":
        text = HELP_TEXT

    try:
        await message.reply_photo(
            photo=START_PIC,
            caption=text,
            parse_mode=HTML,
            reply_markup=start_keyboard(me.username),
        )
    except Exception:
        await message.reply_text(
            text,
            parse_mode=HTML,
            reply_markup=start_keyboard(me.username),
            disable_web_page_preview=True,
        )


@Client.on_callback_query(filters.regex("^show_help$"))
async def cb_help(bot: Client, query: CallbackQuery):
    try:
        await query.message.edit_caption(
            caption=HELP_TEXT,
            parse_mode=HTML,
            reply_markup=back_keyboard(),
        )
    except Exception:
        try:
            await query.message.edit_text(
                text=HELP_TEXT,
                parse_mode=HTML,
                reply_markup=back_keyboard(),
                disable_web_page_preview=True,
            )
        except Exception:
            pass
    await query.answer()


@Client.on_callback_query(filters.regex("^show_about$"))
async def cb_about(bot: Client, query: CallbackQuery):
    me = await bot.get_me()
    about = (
        "<b>ᴀᴜᴛᴏ-ᴀᴄᴄᴇᴘᴛ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ ʙᴏᴛ</b>\n\n"
        f"<b>ʙᴏᴛ:</b> @{me.username}\n"
        f"<b>ᴏᴡɴᴇʀ:</b> @{OWNER if OWNER else 'ɴᴏᴛ sᴇᴛ'}\n"
        "<b>ʟɪʙʀᴀʀʏ:</b> <code>pyrogram</code>\n"
        "<b>ᴅᴀᴛᴀʙᴀsᴇ:</b> <code>mongodb</code>"
    )
    try:
        await query.message.edit_caption(
            caption=about,
            parse_mode=HTML,
            reply_markup=back_keyboard(),
        )
    except Exception:
        try:
            await query.message.edit_text(
                text=about,
                parse_mode=HTML,
                reply_markup=back_keyboard(),
                disable_web_page_preview=True,
            )
        except Exception:
            pass
    await query.answer()


@Client.on_callback_query(filters.regex("^back_home$"))
async def cb_back(bot: Client, query: CallbackQuery):
    me = await bot.get_me()
    user = query.from_user
    text = START_TEXT.format(mention=user.mention if user else "ᴜsᴇʀ")
    try:
        await query.message.edit_caption(
            caption=text,
            parse_mode=HTML,
            reply_markup=start_keyboard(me.username),
        )
    except Exception:
        try:
            await query.message.edit_text(
                text=text,
                parse_mode=HTML,
                reply_markup=start_keyboard(me.username),
                disable_web_page_preview=True,
            )
        except Exception:
            pass
    await query.answer()
