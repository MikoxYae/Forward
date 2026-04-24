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
    "<b>• ᴄʟᴏɴᴇ / ғᴏʀᴡᴀʀᴅ ᴍᴇᴅɪᴀ ʙᴇᴛᴡᴇᴇɴ ᴄʜᴀɴɴᴇʟs — ᴇᴠᴇɴ ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴏɴᴇs.</b>\n"
    "<b>• ᴀᴜᴛᴏ-ᴀᴄᴄᴇᴘᴛ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs ɪɴ ᴀɴʏ ᴄʜᴀɴɴᴇʟ / ɢʀᴏᴜᴘ ᴡʜᴇʀᴇ ɪ ᴀᴍ ᴀᴅᴍɪɴ.</b>\n\n"
    "<b>ʜᴏᴡ ᴛᴏ ғᴏʀᴡᴀʀᴅ</b>\n"
    "<b>1. ᴛᴀᴘ ʟᴏɢɪɴ ʙᴇʟᴏᴡ ᴀɴᴅ sɪɢɴ ɪɴ ᴡɪᴛʜ ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ</b>\n"
    "<b>2. /setsource &lt;ᴄʜᴀɴɴᴇʟ&gt; — sᴇᴛ ᴛʜᴇ sᴏᴜʀᴄᴇ ᴄʜᴀɴɴᴇʟ</b>\n"
    "<b>3. /setdest &lt;ᴄʜᴀɴɴᴇʟ&gt; — sᴇᴛ ᴛʜᴇ ᴅᴇsᴛɪɴᴀᴛɪᴏɴ ᴄʜᴀɴɴᴇʟ</b>\n"
    "<b>4. /forward &lt;ʟɪɴᴋ&gt; — sᴛᴀʀᴛ ғᴏʀᴡᴀʀᴅɪɴɢ</b>\n\n"
    "<b>ʜᴏᴡ ᴛᴏ ᴀᴜᴛᴏ-ᴀᴄᴄᴇᴘᴛ</b>\n"
    "<b>1. ᴇɴᴀʙʟᴇ \"ᴀᴘᴘʀᴏᴠᴇ ɴᴇᴡ ᴍᴇᴍʙᴇʀs\" ɪɴ ʏᴏᴜʀ ᴄʜᴀɴɴᴇʟ / ɢʀᴏᴜᴘ</b>\n"
    "<b>2. ᴀᴅᴅ ᴍᴇ ᴀs ᴀᴅᴍɪɴ ᴡɪᴛʜ \"ᴀᴅᴅ ᴍᴇᴍʙᴇʀs\" ᴘᴇʀᴍɪssɪᴏɴ</b>\n"
    "<b>3. ᴅᴏɴᴇ — ᴀʟʟ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs ᴀʀᴇ ᴀᴜᴛᴏ-ᴀᴄᴄᴇᴘᴛᴇᴅ</b>\n\n"
    "<b>ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅs</b>\n"
    "<b>/login</b> — <b>ʟᴏɢɪɴ ᴡɪᴛʜ ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ</b>\n"
    "<b>/logout</b> — <b>ʀᴇᴍᴏᴠᴇ ʏᴏᴜʀ sᴀᴠᴇᴅ sᴇssɪᴏɴ</b>\n"
    "<b>/setsource</b> — <b>sᴇᴛ sᴏᴜʀᴄᴇ ᴄʜᴀɴɴᴇʟ</b>\n"
    "<b>/setdest</b> — <b>sᴇᴛ ᴅᴇsᴛɪɴᴀᴛɪᴏɴ ᴄʜᴀɴɴᴇʟ</b>\n"
    "<b>/settings</b> — <b>ᴠɪᴇᴡ ʏᴏᴜʀ ᴄᴜʀʀᴇɴᴛ sᴇᴛᴛɪɴɢs</b>\n"
    "<b>/clearsettings</b> — <b>ᴄʟᴇᴀʀ ʏᴏᴜʀ sᴇᴛᴛɪɴɢs</b>\n"
    "<b>/forward</b> — <b>sᴛᴀʀᴛ ғᴏʀᴡᴀʀᴅɪɴɢ</b>\n"
    "<b>/stop</b> — <b>sᴛᴏᴘ ᴀ ʀᴜɴɴɪɴɢ ғᴏʀᴡᴀʀᴅ</b>\n"
    "<b>/cancel</b> — <b>ᴄᴀɴᴄᴇʟ ᴄᴜʀʀᴇɴᴛ ʟᴏɢɪɴ</b>\n"
    "<b>/setwelcome</b> — <b>(ᴄʜᴀᴛ ᴀᴅᴍɪɴ) sᴇᴛ ᴄᴜsᴛᴏᴍ ᴡᴇʟᴄᴏᴍᴇ ᴍᴇssᴀɢᴇ</b>\n"
    "<b>/clearwelcome</b> — <b>(ᴄʜᴀᴛ ᴀᴅᴍɪɴ) ʀᴇsᴇᴛ ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴅᴇғᴀᴜʟᴛ</b>\n"
    "<b>/togglewelcome</b> — <b>(ᴄʜᴀᴛ ᴀᴅᴍɪɴ) ᴛᴜʀɴ ᴡᴇʟᴄᴏᴍᴇ ᴘᴍ ᴏɴ / ᴏғғ</b>\n"
    "<b>/welcome</b> — <b>(ᴄʜᴀᴛ) sʜᴏᴡ ᴄᴜʀʀᴇɴᴛ ᴡᴇʟᴄᴏᴍᴇ ᴛᴇᴍᴘʟᴀᴛᴇ</b>\n"
    "<b>/stats</b> — <b>(ᴏᴡɴᴇʀ) ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs</b>\n"
    "<b>/chats</b> — <b>(ᴏᴡɴᴇʀ) ᴘᴇʀ-ᴄʜᴀᴛ ᴀᴄᴄᴇᴘᴛᴀɴᴄᴇ ᴄᴏᴜɴᴛs</b>\n"
    "<b>/broadcast</b> — <b>(ᴏᴡɴᴇʀ) ʙʀᴏᴀᴅᴄᴀsᴛ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ ᴀʟʟ ᴜsᴇʀs</b>"
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
