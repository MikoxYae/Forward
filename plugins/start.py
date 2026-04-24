from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import OWNER, START_PIC
from database.db import db


START_TEXT = (
    "<b>ʜᴇʟʟᴏ</b> {mention}\n\n"
    "<b>ɪ ᴀᴍ ᴀ ᴍᴜʟᴛɪ-ᴘᴜʀᴘᴏsᴇ ʙᴏᴛ.</b>\n"
    "<b>• ᴄʟᴏɴᴇ / ғᴏʀᴡᴀʀᴅ ᴍᴇᴅɪᴀ ʙᴇᴛᴡᴇᴇɴ ᴄʜᴀɴɴᴇʟs (ᴇᴠᴇɴ ʀᴇsᴛʀɪᴄᴛᴇᴅ).</b>\n"
    "<b>• ᴀᴜᴛᴏ-ᴀᴄᴄᴇᴘᴛ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs ᴡʜᴇʀᴇ ɪ ᴀᴍ ᴀᴅᴍɪɴ.</b>\n\n"
    "<b>ᴄᴏᴍᴍᴀɴᴅs</b>\n"
    "<b>/login</b> <b>/logout</b> <b>/cancel</b> — <b>ᴀᴄᴄᴏᴜɴᴛ</b>\n"
    "<b>/setsource</b> <b>/setdest</b> <b>/settings</b> <b>/clearsettings</b> — <b>ᴄᴏɴғɪɢ</b>\n"
    "<b>/forward</b> <b>/stop</b> — <b>ғᴏʀᴡᴀʀᴅɪɴɢ</b>\n"
    "<b>/approve</b> &lt;ᴄʜᴀᴛ&gt; — <b>ʙᴜʟᴋ-ᴀᴘᴘʀᴏᴠᴇ ᴏʟᴅ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs (ɴᴇᴇᴅs ʟᴏɢɪɴ)</b>\n"
    "<b>/setwelcome</b> <b>/clearwelcome</b> <b>/togglewelcome</b> <b>/welcome</b> — <b>ᴡᴇʟᴄᴏᴍᴇ ᴘᴍ</b>\n"
    "<b>/stats</b> <b>/chats</b> <b>/broadcast</b> — <b>ᴏᴡɴᴇʀ ᴏɴʟʏ</b>\n\n"
    "<b>ᴛɪᴘ — ᴀᴜᴛᴏ-ᴀᴄᴄᴇᴘᴛ:</b> <b>ᴀᴅᴅ ᴍᴇ ᴀs ᴀᴅᴍɪɴ ᴡɪᴛʜ \"ᴀᴅᴅ ᴍᴇᴍʙᴇʀs\" "
    "ᴘᴇʀᴍɪssɪᴏɴ ᴀɴᴅ ᴇɴᴀʙʟᴇ \"ᴀᴘᴘʀᴏᴠᴇ ɴᴇᴡ ᴍᴇᴍʙᴇʀs\" ɪɴ ʏᴏᴜʀ ᴄʜᴀɴɴᴇʟ / ɢʀᴏᴜᴘ.</b>\n"
    "<b>ᴛɪᴘ — ғᴏʀᴡᴀʀᴅ:</b> <b>ᴛᴀᴘ ʟᴏɢɪɴ ʙᴇʟᴏᴡ, sɪɢɴ ɪɴ, sᴇᴛ sᴏᴜʀᴄᴇ + ᴅᴇsᴛ, ᴛʜᴇɴ</b> "
    "<code>/forward &lt;ʟɪɴᴋ&gt;</code><b>.</b>"
)


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("ʟᴏɢɪɴ", callback_data="login_start"),
                InlineKeyboardButton("ʟᴏɢᴏᴜᴛ", callback_data="logout_start"),
            ],
            [InlineKeyboardButton("ᴏᴡɴᴇʀ", url=f"https://t.me/{OWNER}")],
        ]
    )


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="back_start")]]
    )


@Client.on_message(filters.command(["start", "help"]) & filters.private)
async def start_cmd(client: Client, message: Message):
    await db.add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )
    await message.reply_photo(
        photo=START_PIC,
        caption=START_TEXT.format(mention=message.from_user.mention),
        parse_mode=enums.ParseMode.HTML,
        reply_markup=start_keyboard(),
    )


@Client.on_callback_query(filters.regex("^back_start$"))
async def back_to_start(client: Client, query: CallbackQuery):
    try:
        await query.message.edit_caption(
            caption=START_TEXT.format(mention=query.from_user.mention),
            parse_mode=enums.ParseMode.HTML,
            reply_markup=start_keyboard(),
        )
    except Exception:
        try:
            await query.message.edit_text(
                text=START_TEXT.format(mention=query.from_user.mention),
                parse_mode=enums.ParseMode.HTML,
                reply_markup=start_keyboard(),
                disable_web_page_preview=True,
            )
        except Exception:
            pass
    await query.answer()
