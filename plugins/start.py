from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import OWNER, START_PIC
from database.db import db


HTML = enums.ParseMode.HTML


START_TEXT = (
    "<b>ʜᴇʟʟᴏ</b> {mention}\n\n"
    "<b>ɪ ᴀᴍ ᴀ ᴍᴜʟᴛɪ-ᴘᴜʀᴘᴏsᴇ ʙᴏᴛ.</b>\n"
    "<b>• ᴄʟᴏɴᴇ / ғᴏʀᴡᴀʀᴅ ᴍᴇᴅɪᴀ ʙᴇᴛᴡᴇᴇɴ ᴄʜᴀɴɴᴇʟs (ᴇᴠᴇɴ ʀᴇsᴛʀɪᴄᴛᴇᴅ).</b>\n"
    "<b>• ᴀᴜᴛᴏ-ᴀᴄᴄᴇᴘᴛ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs ᴡʜᴇʀᴇ ɪ ᴀᴍ ᴀᴅᴍɪɴ.</b>\n\n"
    "<b>ᴛᴀᴘ ᴄᴏᴍᴍᴀɴᴅs ʙᴇʟᴏᴡ ᴛᴏ sᴇᴇ ʜᴏᴡ ᴛᴏ ᴜsᴇ ᴇᴀᴄʜ ғᴇᴀᴛᴜʀᴇ.</b>"
)


COMMANDS_MENU_TEXT = (
    "<b>ᴄʜᴏᴏsᴇ ᴀ ғᴇᴀᴛᴜʀᴇ ᴛᴏ sᴇᴇ ɪᴛs ᴄᴏᴍᴍᴀɴᴅs ᴀɴᴅ ɪɴsᴛʀᴜᴄᴛɪᴏɴs.</b>"
)


ACCEPT_TEXT = (
    "<b>🛡 Auto-Accept Join Requests</b>\n\n"
    "<b>How it works</b>\n"
    "The bot auto-approves every join request in any channel/group where it is admin.\n\n"
    "<b>Setup</b>\n"
    "1. Enable \"Approve New Members\" in chat settings\n"
    "2. Add the bot as admin with \"Add Members\" permission\n"
    "3. Done — new join requests are auto-accepted\n\n"
    "<b>Old pending requests</b> (login required)\n"
    "<code>/approve &lt;chat_id|@username&gt;</code> — bulk-approve all pending requests using your logged-in account\n\n"
    "<b>Welcome PM</b> (chat admins)\n"
    "<code>/setwelcome &lt;text&gt;</code> — set custom welcome\n"
    "<code>/clearwelcome</code> — reset to default\n"
    "<code>/togglewelcome</code> — on/off\n"
    "<code>/welcome</code> — show current template\n"
    "Placeholders: <code>{mention}</code> <code>{first_name}</code> <code>{username}</code> <code>{chat_title}</code> <code>{chat_link}</code> <code>{user_id}</code>\n\n"
    "<b>Owner only</b>\n"
    "<code>/stats</code> — totals\n"
    "<code>/chats</code> — per-chat counts\n"
    "<code>/broadcast</code> — reply to a message + /broadcast to send to all users"
)


FORWARD_TEXT = (
    "<b>📤 Forward / Clone Media</b>\n\n"
    "<b>How it works</b>\n"
    "Logs into your Telegram account and clones media (incl. restricted) from one channel to another.\n\n"
    "<b>Setup</b>\n"
    "1. Tap Login (or send /login) and sign in with your account\n"
    "2. <code>/setsource &lt;channel_id|@username&gt;</code>\n"
    "3. <code>/setdest &lt;channel_id|@username&gt;</code>\n"
    "4. <code>/forward &lt;message_link&gt;</code>\n\n"
    "<b>Account</b>\n"
    "<code>/login</code> — sign in\n"
    "<code>/logout</code> — remove saved session\n"
    "<code>/cancel</code> — cancel current login\n\n"
    "<b>Config</b>\n"
    "<code>/settings</code> — view current source &amp; dest\n"
    "<code>/setsource &lt;id&gt;</code> — set source\n"
    "<code>/setdest &lt;id&gt;</code> — set destination\n"
    "<code>/clearsettings</code> — clear\n\n"
    "<b>Forwarding</b>\n"
    "<code>/forward &lt;link&gt;</code> — start from that message\n"
    "<code>/stop</code> — stop the running forward\n\n"
    "<b>Tip:</b> send the OTP with spaces (e.g. 1 2 3 4 5) so Telegram does not invalidate it."
)


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("ʟᴏɢɪɴ", callback_data="login_start"),
                InlineKeyboardButton("ʟᴏɢᴏᴜᴛ", callback_data="logout_start"),
            ],
            [InlineKeyboardButton("ᴄᴏᴍᴍᴀɴᴅs", callback_data="show_commands")],
            [InlineKeyboardButton("ᴏᴡɴᴇʀ", url=f"https://t.me/{OWNER}")],
        ]
    )


def commands_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("ᴀᴜᴛᴏ ᴀᴄᴄᴇᴘᴛ", callback_data="show_accept"),
                InlineKeyboardButton("ғᴏʀᴡᴀʀᴅ", callback_data="show_forward"),
            ],
            [InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="back_start")],
        ]
    )


def back_to_commands_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="show_commands")]]
    )


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="back_start")]]
    )


async def _edit_screen(query: CallbackQuery, caption: str, keyboard: InlineKeyboardMarkup):
    try:
        await query.message.edit_caption(
            caption=caption,
            parse_mode=HTML,
            reply_markup=keyboard,
        )
    except Exception:
        try:
            await query.message.edit_text(
                text=caption,
                parse_mode=HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Exception:
            pass
    await query.answer()


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
        parse_mode=HTML,
        reply_markup=start_keyboard(),
    )


@Client.on_callback_query(filters.regex("^back_start$"))
async def back_to_start(client: Client, query: CallbackQuery):
    await _edit_screen(
        query,
        START_TEXT.format(mention=query.from_user.mention),
        start_keyboard(),
    )


@Client.on_callback_query(filters.regex("^show_commands$"))
async def show_commands(client: Client, query: CallbackQuery):
    await _edit_screen(query, COMMANDS_MENU_TEXT, commands_keyboard())


@Client.on_callback_query(filters.regex("^show_accept$"))
async def show_accept(client: Client, query: CallbackQuery):
    await _edit_screen(query, ACCEPT_TEXT, back_to_commands_keyboard())


@Client.on_callback_query(filters.regex("^show_forward$"))
async def show_forward(client: Client, query: CallbackQuery):
    await _edit_screen(query, FORWARD_TEXT, back_to_commands_keyboard())
