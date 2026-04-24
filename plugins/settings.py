from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import OWNER_ID
from database.db import db


# In-memory state for owner waiting for input
settings_state: dict[int, str] = {}


def _settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Set Source", callback_data="set_source"),
                InlineKeyboardButton("Set Destination", callback_data="set_dest"),
            ],
            [
                InlineKeyboardButton("Clear Source", callback_data="clear_source"),
                InlineKeyboardButton("Clear Destination", callback_data="clear_dest"),
            ],
            [InlineKeyboardButton("Refresh", callback_data="refresh_settings")],
            [InlineKeyboardButton("Close", callback_data="close_settings")],
        ]
    )


async def _render_settings_text() -> str:
    source = await db.get_setting("source")
    dest = await db.get_setting("destination")
    return (
        "**Bot Settings (Owner only)**\n\n"
        f"**Source:** `{source or 'Not set'}`\n"
        f"**Destination:** `{dest or 'Not set'}`\n\n"
        "Use the buttons below or:\n"
        "/setsource <channel_id_or_username>\n"
        "/setdest <channel_id_or_username>\n"
        "/clearsettings"
    )


@Client.on_message(filters.command("settings") & filters.private)
async def settings_cmd(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("This command is for the owner only.")
    text = await _render_settings_text()
    await message.reply_text(text, reply_markup=_settings_kb())


@Client.on_message(filters.command("setsource") & filters.private)
async def set_source_cmd(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    if len(message.command) < 2:
        return await message.reply_text(
            "Usage: `/setsource <channel_id_or_username>`\n"
            "Example: `/setsource @mychannel` or `/setsource -1001234567890`"
        )
    val = message.command[1]
    await db.set_setting("source", val)
    await message.reply_text(f"Source channel set to: `{val}`")


@Client.on_message(filters.command("setdest") & filters.private)
async def set_dest_cmd(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    if len(message.command) < 2:
        return await message.reply_text(
            "Usage: `/setdest <channel_id_or_username>`\n"
            "Example: `/setdest @mychannel` or `/setdest -1001234567890`"
        )
    val = message.command[1]
    await db.set_setting("destination", val)
    await message.reply_text(f"Destination channel set to: `{val}`")


@Client.on_message(filters.command("clearsettings") & filters.private)
async def clear_settings_cmd(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    await db.clear_setting("source")
    await db.clear_setting("destination")
    await message.reply_text("All settings cleared.")


# ---------- Callback Buttons ----------
@Client.on_callback_query(filters.regex("^(set_source|set_dest)$"))
async def cb_set_value(client, query):
    if query.from_user.id != OWNER_ID:
        return await query.answer("Owner only.", show_alert=True)
    key = "source" if query.data == "set_source" else "destination"
    settings_state[query.from_user.id] = key
    await query.message.reply_text(
        f"Send the **{key}** channel id or username (e.g. `@mychannel` or `-1001234567890`)."
    )
    await query.answer()


@Client.on_callback_query(filters.regex("^(clear_source|clear_dest)$"))
async def cb_clear_value(client, query):
    if query.from_user.id != OWNER_ID:
        return await query.answer("Owner only.", show_alert=True)
    key = "source" if query.data == "clear_source" else "destination"
    await db.clear_setting(key)
    text = await _render_settings_text()
    await query.message.edit_text(text, reply_markup=_settings_kb())
    await query.answer(f"{key.capitalize()} cleared.")


@Client.on_callback_query(filters.regex("^refresh_settings$"))
async def cb_refresh(client, query):
    if query.from_user.id != OWNER_ID:
        return await query.answer("Owner only.", show_alert=True)
    text = await _render_settings_text()
    await query.message.edit_text(text, reply_markup=_settings_kb())
    await query.answer("Refreshed.")


@Client.on_callback_query(filters.regex("^close_settings$"))
async def cb_close(client, query):
    if query.from_user.id != OWNER_ID:
        return await query.answer("Owner only.", show_alert=True)
    await query.message.delete()
    await query.answer()


# Listen for owner's reply when waiting for source/dest input
@Client.on_message(
    filters.private
    & filters.user(OWNER_ID)
    & filters.text
    & ~filters.command(
        ["start", "help", "login", "logout", "cancel", "settings",
         "setsource", "setdest", "clearsettings", "forward", "stop", "status"]
    )
)
async def settings_input(client, message: Message):
    user_id = message.from_user.id
    key = settings_state.get(user_id)
    if not key:
        return  # not waiting for settings input
    val = (message.text or "").strip()
    if not val:
        return await message.reply_text("Empty value, try again.")
    await db.set_setting(key, val)
    settings_state.pop(user_id, None)
    await message.reply_text(f"{key.capitalize()} set to: `{val}`")
