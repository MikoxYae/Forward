from pyrogram import Client, filters, enums
from pyrogram.types import Message

from config import DEFAULT_WELCOME, OWNER_ID
from database.db import db


HTML = enums.ParseMode.HTML


async def _is_chat_admin(bot: Client, chat_id: int, user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (
            enums.ChatMemberStatus.OWNER,
            enums.ChatMemberStatus.ADMINISTRATOR,
        )
    except Exception:
        return False


@Client.on_message(filters.command("setwelcome") & ~filters.private)
async def set_welcome(bot: Client, message: Message):
    if not await _is_chat_admin(bot, message.chat.id, message.from_user.id):
        return await message.reply_text(
            "<b>ᴏɴʟʏ ᴄʜᴀᴛ ᴀᴅᴍɪɴs ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.</b>",
            parse_mode=HTML,
        )

    text = None
    if message.reply_to_message and (
        message.reply_to_message.text or message.reply_to_message.caption
    ):
        text = message.reply_to_message.text or message.reply_to_message.caption
        if hasattr(text, "html"):
            text = text.html
    elif len(message.command) > 1:
        text = message.text.split(None, 1)[1]

    if not text:
        return await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/setwelcome &lt;ᴛᴇxᴛ&gt;</code> "
            "<b>ᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴡɪᴛʜ</b> <code>/setwelcome</code>\n\n"
            "<b>ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀs:</b>\n"
            "<code>{mention}</code>, <code>{first_name}</code>, <code>{username}</code>, "
            "<code>{user_id}</code>, <code>{chat_title}</code>, <code>{chat_link}</code>",
            parse_mode=HTML,
        )

    await db.set_chat_setting(message.chat.id, "welcome_text", text)
    await message.reply_text(
        "<b>ᴡᴇʟᴄᴏᴍᴇ ᴍᴇssᴀɢᴇ ᴜᴘᴅᴀᴛᴇᴅ ғᴏʀ ᴛʜɪs ᴄʜᴀᴛ.</b>",
        parse_mode=HTML,
    )


@Client.on_message(filters.command("clearwelcome") & ~filters.private)
async def clear_welcome(bot: Client, message: Message):
    if not await _is_chat_admin(bot, message.chat.id, message.from_user.id):
        return await message.reply_text(
            "<b>ᴏɴʟʏ ᴄʜᴀᴛ ᴀᴅᴍɪɴs ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.</b>",
            parse_mode=HTML,
        )
    await db.set_chat_setting(message.chat.id, "welcome_text", None)
    await message.reply_text(
        "<b>ᴡᴇʟᴄᴏᴍᴇ ᴍᴇssᴀɢᴇ ʀᴇsᴇᴛ ᴛᴏ ᴅᴇғᴀᴜʟᴛ.</b>",
        parse_mode=HTML,
    )


@Client.on_message(filters.command("togglewelcome") & ~filters.private)
async def toggle_welcome(bot: Client, message: Message):
    if not await _is_chat_admin(bot, message.chat.id, message.from_user.id):
        return await message.reply_text(
            "<b>ᴏɴʟʏ ᴄʜᴀᴛ ᴀᴅᴍɪɴs ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.</b>",
            parse_mode=HTML,
        )
    current = await db.get_chat_setting(message.chat.id, "welcome_enabled", True)
    new_value = not bool(current)
    await db.set_chat_setting(message.chat.id, "welcome_enabled", new_value)
    state = "ᴏɴ" if new_value else "ᴏғғ"
    await message.reply_text(
        f"<b>ᴡᴇʟᴄᴏᴍᴇ ᴘᴍ ɪs ɴᴏᴡ {state} ғᴏʀ ᴛʜɪs ᴄʜᴀᴛ.</b>",
        parse_mode=HTML,
    )


@Client.on_message(filters.command("welcome") & ~filters.private)
async def show_welcome(bot: Client, message: Message):
    enabled = await db.get_chat_setting(message.chat.id, "welcome_enabled", True)
    text = await db.get_chat_setting(message.chat.id, "welcome_text", None) or DEFAULT_WELCOME
    state = "ᴏɴ" if enabled else "ᴏғғ"
    await message.reply_text(
        f"<b>ᴡᴇʟᴄᴏᴍᴇ ᴘᴍ:</b> <code>{state}</code>\n\n"
        f"<b>ᴄᴜʀʀᴇɴᴛ ᴛᴇᴍᴘʟᴀᴛᴇ:</b>\n{text}",
        parse_mode=HTML,
        disable_web_page_preview=True,
    )
