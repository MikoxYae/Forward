"""GUI settings panel — /settings.

A single message that the user navigates with inline buttons. Each action
edits the same message in place. When the panel is awaiting a value (like
a target chat or a new interval), the user's reply is captured, processed,
and (best-effort) deleted so the chat stays clean.
"""

import asyncio
from datetime import datetime

from pyrogram import Client, filters, enums, StopPropagation
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import OWNER_ID, START_PIC
from database.db import db
from plugins.promo import (
    promo_set_state,
    PROMO_PER_USER_LIMIT,
    _parse_chat,
    _validate_target_for_user,
    _check_promo_limit,
    _get_user_promo,
    _post_cycle,
    _spawn_task,
    _kill_task,
    _is_running,
)


HTML = enums.ParseMode.HTML


# user_id -> {
#   "panel_chat_id": int,
#   "panel_msg_id": int,
#   "screen": str,            # "main" | "promos" | f"promo:{id}"
#   "awaiting": str | None,   # "promo_target" | "promo_content"
#                             # | f"promo_time:{id}" | f"promo_edit:{id}"
#                             # | "set_source" | "set_dest"
#   "ctx": dict,              # context for the current awaiting flow
# }
settings_state: dict[int, dict] = {}


# ------------------------------------------------------------------
# Rendering helpers
# ------------------------------------------------------------------
async def _safe_delete(bot: Client, chat_id: int, message_id: int):
    try:
        await bot.delete_messages(chat_id, message_id)
    except Exception:
        pass


async def _edit_panel(bot: Client, user_id: int, caption: str,
                      keyboard: InlineKeyboardMarkup):
    """Edit the user's panel message in place, falling back gracefully."""
    state = settings_state.get(user_id)
    if not state:
        return
    chat_id = state["panel_chat_id"]
    msg_id = state["panel_msg_id"]

    # 1) Try editing the photo's caption (panel was sent as photo).
    try:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=msg_id,
            caption=caption,
            parse_mode=HTML,
            reply_markup=keyboard,
        )
        return
    except Exception:
        pass

    # 2) Try editing as plain text (panel may have been re-sent as text).
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=caption,
            parse_mode=HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        return
    except Exception:
        pass

    # 3) Last resort: delete the old panel and send a fresh photo panel.
    await _safe_delete(bot, chat_id, msg_id)
    try:
        new = await bot.send_photo(
            chat_id=chat_id,
            photo=START_PIC,
            caption=caption,
            parse_mode=HTML,
            reply_markup=keyboard,
        )
        state["panel_msg_id"] = new.id
    except Exception:
        try:
            new = await bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode=HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            state["panel_msg_id"] = new.id
        except Exception:
            pass


def _back_kb(extra: list = None) -> InlineKeyboardMarkup:
    rows = []
    if extra:
        rows.extend(extra)
    rows.append([InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="set:main")])
    return InlineKeyboardMarkup(rows)


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✖ ᴄᴀɴᴄᴇʟ", callback_data="set:cancel")]]
    )


# ---------------- main screen ----------------
async def _render_main(bot: Client, user_id: int):
    n_promos = await db.count_user_promos(user_id)
    session = await db.get_session(user_id)
    src = await db.get_user_setting(user_id, "source")
    dst = await db.get_user_setting(user_id, "destination")

    limit = "∞" if int(user_id) == int(OWNER_ID) else str(PROMO_PER_USER_LIMIT)
    try:
        u = await bot.get_users(user_id)
        mention = u.mention
    except Exception:
        mention = f"<code>{user_id}</code>"

    caption = (
        f"<b>🛠 sᴇᴛᴛɪɴɢs</b> · {mention}\n\n"
        f"<b>📣 ᴀᴜᴛᴏ-ᴘʀᴏᴍᴏ</b>\n"
        f"   ᴀᴄᴛɪᴠᴇ: <code>{n_promos}/{limit}</code>\n\n"
        f"<b>📤 ғᴏʀᴡᴀʀᴅ</b>\n"
        f"   ʟᴏɢɪɴ: <code>{'yes' if session else 'no'}</code>\n"
        f"   sᴏᴜʀᴄᴇ: <code>{src or '—'}</code>\n"
        f"   ᴅᴇsᴛ: <code>{dst or '—'}</code>\n\n"
        f"<b>📥 ᴡᴇʟᴄᴏᴍᴇ ᴘᴍ</b>\n"
        f"   sᴇᴛ ᴘᴇʀ ᴄʜᴀɴɴᴇʟ ᴡɪᴛʜ /setwelcome ɪɴ ᴛʜᴀᴛ ᴄʜᴀᴛ.\n\n"
        f"<b>ᴜsᴇ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ.</b>"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ ɴᴇᴡ ᴘʀᴏᴍᴏ", callback_data="set:promo_new"),
            InlineKeyboardButton("📋 ᴍʏ ᴘʀᴏᴍᴏs", callback_data="set:promos"),
        ],
        [
            InlineKeyboardButton("📤 sᴇᴛ sᴏᴜʀᴄᴇ", callback_data="set:src"),
            InlineKeyboardButton("📥 sᴇᴛ ᴅᴇsᴛ", callback_data="set:dst"),
        ],
        [
            InlineKeyboardButton("🧹 ᴄʟᴇᴀʀ ғᴡᴅ", callback_data="set:fwd_clear"),
            InlineKeyboardButton("🚪 ʟᴏɢᴏᴜᴛ", callback_data="set:logout"),
        ],
        [
            InlineKeyboardButton("🔑 ʟᴏɢɪɴ ʜᴇʟᴘ", callback_data="set:login_help"),
            InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="set:close"),
        ],
    ])

    state = settings_state.setdefault(user_id, {})
    state["screen"] = "main"
    state["awaiting"] = None
    state["ctx"] = {}
    await _edit_panel(bot, user_id, caption, kb)


# ---------------- promo list ----------------
async def _render_promos(bot: Client, user_id: int):
    promos = []
    async for p in db.user_promos(user_id):
        promos.append(p)

    limit = "∞" if int(user_id) == int(OWNER_ID) else str(PROMO_PER_USER_LIMIT)
    if not promos:
        caption = (
            f"<b>📋 ʏᴏᴜʀ ᴘʀᴏᴍᴏs</b> (<code>0/{limit}</code>)\n\n"
            "<b>ɴᴏ ᴘʀᴏᴍᴏs ʏᴇᴛ.</b>\n"
            "<b>ᴛᴀᴘ ➕ ɴᴇᴡ ᴘʀᴏᴍᴏ ᴛᴏ ᴄʀᴇᴀᴛᴇ ᴏɴᴇ.</b>"
        )
    else:
        lines = [f"<b>📋 ʏᴏᴜʀ ᴘʀᴏᴍᴏs</b> (<code>{len(promos)}/{limit}</code>)\n"]
        for i, p in enumerate(promos, 1):
            state = "🟢" if p.get("enabled") else "🔴"
            lines.append(
                f"{i}. <code>#{p['_id']}</code> · "
                f"<code>{p['target_chat']}</code> · "
                f"<code>{p.get('interval_minutes', 20)}m</code> · {state}"
            )
        lines.append("\n<b>ᴛᴀᴘ ᴀ ᴘʀᴏᴍᴏ ʙᴇʟᴏᴡ ᴛᴏ ᴍᴀɴᴀɢᴇ ɪᴛ.</b>")
        caption = "\n".join(lines)

    rows = []
    for i, p in enumerate(promos, 1):
        state_dot = "🟢" if p.get("enabled") else "🔴"
        rows.append([
            InlineKeyboardButton(
                f"{state_dot} #{p['_id']} · {str(p['target_chat'])[:18]}",
                callback_data=f"set:promo:{p['_id']}",
            )
        ])
    rows.append([
        InlineKeyboardButton("➕ ɴᴇᴡ", callback_data="set:promo_new"),
        InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="set:main"),
    ])

    state = settings_state.setdefault(user_id, {})
    state["screen"] = "promos"
    state["awaiting"] = None
    state["ctx"] = {}
    await _edit_panel(bot, user_id, caption, InlineKeyboardMarkup(rows))


# ---------------- promo detail ----------------
async def _render_promo_detail(bot: Client, user_id: int, promo_id: int,
                               note: str | None = None):
    p, err = await _get_user_promo(promo_id, user_id)
    if err:
        await _edit_panel(
            bot, user_id, err,
            _back_kb([[InlineKeyboardButton("📋 ᴍʏ ᴘʀᴏᴍᴏs", callback_data="set:promos")]]),
        )
        return

    state_str = "🟢 ᴏɴ" if p.get("enabled") else "🔴 ᴏғғ"
    running = "ʀᴜɴɴɪɴɢ" if _is_running(promo_id) else "sᴛᴏᴘᴘᴇᴅ"
    last = p.get("last_post_at")
    last_str = last.strftime("%Y-%m-%d %H:%M UTC") if last else "—"
    created = p.get("created_at")
    created_str = created.strftime("%Y-%m-%d %H:%M UTC") if created else "—"

    caption = (
        f"<b>📣 ᴘʀᴏᴍᴏ #{promo_id}</b>\n\n"
        f"<b>🎯 ᴛᴀʀɢᴇᴛ:</b> <code>{p['target_chat']}</code>\n"
        f"<b>⏱ ɪɴᴛᴇʀᴠᴀʟ:</b> <code>{p.get('interval_minutes', 20)} min</code>\n"
        f"<b>🔘 sᴛᴀᴛᴜs:</b> {state_str}\n"
        f"<b>🔁 ʟᴏᴏᴘ:</b> <code>{running}</code>\n"
        f"<b>📤 ʟᴀsᴛ ᴘᴏsᴛ ɪᴅ:</b> <code>{p.get('last_post_id') or '—'}</code>\n"
        f"<b>🕒 ʟᴀsᴛ ᴘᴏsᴛ:</b> <code>{last_str}</code>\n"
        f"<b>🗓 ᴄʀᴇᴀᴛᴇᴅ:</b> <code>{created_str}</code>\n"
    )
    if note:
        caption += f"\n{note}"

    toggle_label = "🔴 ᴛᴜʀɴ ᴏғғ" if p.get("enabled") else "🟢 ᴛᴜʀɴ ᴏɴ"
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏱ ᴛɪᴍᴇ", callback_data=f"set:promo_time:{promo_id}"),
            InlineKeyboardButton("▶️ ᴘᴏsᴛ ɴᴏᴡ", callback_data=f"set:promo_now:{promo_id}"),
        ],
        [
            InlineKeyboardButton("✏️ ᴇᴅɪᴛ", callback_data=f"set:promo_edit:{promo_id}"),
            InlineKeyboardButton("👁 ᴘʀᴇᴠɪᴇᴡ", callback_data=f"set:promo_preview:{promo_id}"),
        ],
        [
            InlineKeyboardButton(toggle_label, callback_data=f"set:promo_toggle:{promo_id}"),
            InlineKeyboardButton("🗑 ᴅᴇʟᴇᴛᴇ", callback_data=f"set:promo_del:{promo_id}"),
        ],
        [
            InlineKeyboardButton("📋 ʟɪsᴛ", callback_data="set:promos"),
            InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="set:main"),
        ],
    ])

    state = settings_state.setdefault(user_id, {})
    state["screen"] = f"promo:{promo_id}"
    state["awaiting"] = None
    state["ctx"] = {}
    await _edit_panel(bot, user_id, caption, kb)


# ---------------- prompt screens ----------------
async def _prompt(bot: Client, user_id: int, caption: str, awaiting: str,
                  ctx: dict | None = None,
                  extra_buttons: list | None = None):
    state = settings_state.setdefault(user_id, {})
    state["awaiting"] = awaiting
    state["ctx"] = ctx or {}
    rows = []
    if extra_buttons:
        rows.extend(extra_buttons)
    rows.append([InlineKeyboardButton("✖ ᴄᴀɴᴄᴇʟ", callback_data="set:cancel")])
    await _edit_panel(bot, user_id, caption, InlineKeyboardMarkup(rows))


# ------------------------------------------------------------------
# /settings command  +  ⚙ button on /start
# ------------------------------------------------------------------
async def _open_panel_new_message(bot: Client, message: Message):
    """Sends a fresh panel as a photo and stores its msg id in state."""
    user_id = message.from_user.id
    settings_state[user_id] = {
        "panel_chat_id": message.chat.id,
        "panel_msg_id": 0,           # filled below
        "screen": "main",
        "awaiting": None,
        "ctx": {},
    }
    try:
        sent = await bot.send_photo(
            chat_id=message.chat.id,
            photo=START_PIC,
            caption="<b>🛠 ᴏᴘᴇɴɪɴɢ sᴇᴛᴛɪɴɢs...</b>",
            parse_mode=HTML,
        )
    except Exception:
        sent = await message.reply_text(
            "<b>🛠 ᴏᴘᴇɴɪɴɢ sᴇᴛᴛɪɴɢs...</b>",
            parse_mode=HTML,
        )
    settings_state[user_id]["panel_msg_id"] = sent.id
    await _render_main(bot, user_id)


@Client.on_message(filters.command("settings") & filters.private)
async def settings_cmd(bot: Client, message: Message):
    await _open_panel_new_message(bot, message)


@Client.on_callback_query(filters.regex(r"^set:open$"))
async def settings_open_from_start(bot: Client, query: CallbackQuery):
    """Promote the existing /start photo into the settings panel."""
    user_id = query.from_user.id
    settings_state[user_id] = {
        "panel_chat_id": query.message.chat.id,
        "panel_msg_id": query.message.id,
        "screen": "main",
        "awaiting": None,
        "ctx": {},
    }
    await query.answer()
    await _render_main(bot, user_id)


# ------------------------------------------------------------------
# Main panel callbacks
# ------------------------------------------------------------------
@Client.on_callback_query(filters.regex(r"^set:main$"))
async def cb_main(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if user_id not in settings_state:
        # User clicked an old panel — bootstrap state from this message.
        settings_state[user_id] = {
            "panel_chat_id": query.message.chat.id,
            "panel_msg_id": query.message.id,
            "screen": "main",
            "awaiting": None,
            "ctx": {},
        }
    else:
        settings_state[user_id]["panel_chat_id"] = query.message.chat.id
        settings_state[user_id]["panel_msg_id"] = query.message.id
    await query.answer()
    # Clear any in-progress promo command flow too.
    promo_set_state.pop(user_id, None)
    await _render_main(bot, user_id)


@Client.on_callback_query(filters.regex(r"^set:cancel$"))
async def cb_cancel(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if user_id in settings_state:
        settings_state[user_id]["awaiting"] = None
        settings_state[user_id]["ctx"] = {}
    promo_set_state.pop(user_id, None)
    await query.answer("ᴄᴀɴᴄᴇʟʟᴇᴅ")
    await _render_main(bot, user_id)


@Client.on_callback_query(filters.regex(r"^set:close$"))
async def cb_close(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    settings_state.pop(user_id, None)
    promo_set_state.pop(user_id, None)
    try:
        await query.message.delete()
    except Exception:
        pass
    await query.answer("ᴄʟᴏsᴇᴅ")


@Client.on_callback_query(filters.regex(r"^set:promos$"))
async def cb_promos(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    settings_state.setdefault(user_id, {})
    settings_state[user_id]["panel_chat_id"] = query.message.chat.id
    settings_state[user_id]["panel_msg_id"] = query.message.id
    await query.answer()
    await _render_promos(bot, user_id)


@Client.on_callback_query(filters.regex(r"^set:promo:(\d+)$"))
async def cb_promo_detail(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    promo_id = int(query.matches[0].group(1))
    settings_state.setdefault(user_id, {})
    settings_state[user_id]["panel_chat_id"] = query.message.chat.id
    settings_state[user_id]["panel_msg_id"] = query.message.id
    await query.answer()
    await _render_promo_detail(bot, user_id, promo_id)


# ---------------- new promo flow ----------------
@Client.on_callback_query(filters.regex(r"^set:promo_new$"))
async def cb_promo_new(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    settings_state.setdefault(user_id, {})
    settings_state[user_id]["panel_chat_id"] = query.message.chat.id
    settings_state[user_id]["panel_msg_id"] = query.message.id

    err = await _check_promo_limit(user_id)
    if err:
        await query.answer()
        await _edit_panel(
            bot, user_id, err,
            _back_kb([[InlineKeyboardButton("📋 ᴍʏ ᴘʀᴏᴍᴏs", callback_data="set:promos")]]),
        )
        return

    await query.answer()
    await _prompt(
        bot, user_id,
        "<b>➕ ɴᴇᴡ ᴘʀᴏᴍᴏ — sᴛᴇᴘ 1/2</b>\n\n"
        "<b>sᴇɴᴅ ᴛʜᴇ ᴛᴀʀɢᴇᴛ ᴄʜᴀᴛ ɪᴅ ᴏʀ @ᴜsᴇʀɴᴀᴍᴇ.</b>\n\n"
        "<b>ʀᴇǫᴜɪʀᴇᴍᴇɴᴛs:</b>\n"
        "• ʙᴏᴛ ᴍᴜsᴛ ʙᴇ ᴀᴅᴍɪɴ ᴛʜᴇʀᴇ ᴡɪᴛʜ <b>ᴘᴏsᴛ</b> + <b>ᴅᴇʟᴇᴛᴇ</b> ᴘᴇʀᴍs\n"
        "• <b>ʏᴏᴜ</b> ᴍᴜsᴛ ʙᴇ ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀᴛ ᴀs ᴡᴇʟʟ\n\n"
        "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>@mychannel</code> ᴏʀ <code>-1001234567890</code>",
        awaiting="promo_target",
    )


# ---------------- promo: time ----------------
@Client.on_callback_query(filters.regex(r"^set:promo_time:(\d+)$"))
async def cb_promo_time(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    promo_id = int(query.matches[0].group(1))
    p, err = await _get_user_promo(promo_id, user_id)
    if err:
        await query.answer(err.replace("<b>", "").replace("</b>", "")[:200], show_alert=True)
        return
    settings_state.setdefault(user_id, {})
    settings_state[user_id]["panel_chat_id"] = query.message.chat.id
    settings_state[user_id]["panel_msg_id"] = query.message.id
    await query.answer()
    await _prompt(
        bot, user_id,
        f"<b>⏱ ᴄʜᴀɴɢᴇ ɪɴᴛᴇʀᴠᴀʟ — ᴘʀᴏᴍᴏ #{promo_id}</b>\n\n"
        f"<b>ᴄᴜʀʀᴇɴᴛ:</b> <code>{p.get('interval_minutes', 20)}</code> <b>ᴍɪɴᴜᴛᴇs</b>\n\n"
        "<b>sᴇɴᴅ ᴛʜᴇ ɴᴇᴡ ɪɴᴛᴇʀᴠᴀʟ ɪɴ ᴍɪɴᴜᴛᴇs (ᴍɪɴɪᴍᴜᴍ 1).</b>",
        awaiting=f"promo_time:{promo_id}",
    )


# ---------------- promo: edit content ----------------
@Client.on_callback_query(filters.regex(r"^set:promo_edit:(\d+)$"))
async def cb_promo_edit(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    promo_id = int(query.matches[0].group(1))
    p, err = await _get_user_promo(promo_id, user_id)
    if err:
        await query.answer(err.replace("<b>", "").replace("</b>", "")[:200], show_alert=True)
        return
    settings_state.setdefault(user_id, {})
    settings_state[user_id]["panel_chat_id"] = query.message.chat.id
    settings_state[user_id]["panel_msg_id"] = query.message.id
    await query.answer()
    await _prompt(
        bot, user_id,
        f"<b>✏️ ᴇᴅɪᴛ ᴄᴏɴᴛᴇɴᴛ — ᴘʀᴏᴍᴏ #{promo_id}</b>\n\n"
        "<b>sᴇɴᴅ ᴛʜᴇ ɴᴇᴡ ᴘʀᴏᴍᴏ ᴄᴏɴᴛᴇɴᴛ.</b>\n"
        "<b>ᴀʟʟᴏᴡᴇᴅ:</b> ᴛᴇxᴛ, ᴘʜᴏᴛᴏ, ᴠɪᴅᴇᴏ, ᴀᴜᴅɪᴏ, ᴀɴɪᴍᴀᴛɪᴏɴ, sᴛɪᴄᴋᴇʀ, "
        "ᴅᴏᴄᴜᴍᴇɴᴛ — ᴀɴʏ ᴄᴏᴍʙᴏ. <b>ᴀʟʟ ғᴏʀᴍᴀᴛᴛɪɴɢ ɪs ᴋᴇᴘᴛ.</b>",
        awaiting=f"promo_edit:{promo_id}",
    )


# ---------------- promo: post now ----------------
@Client.on_callback_query(filters.regex(r"^set:promo_now:(\d+)$"))
async def cb_promo_now(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    promo_id = int(query.matches[0].group(1))
    p, err = await _get_user_promo(promo_id, user_id)
    if err:
        await query.answer(err.replace("<b>", "").replace("</b>", "")[:200], show_alert=True)
        return
    settings_state.setdefault(user_id, {})
    settings_state[user_id]["panel_chat_id"] = query.message.chat.id
    settings_state[user_id]["panel_msg_id"] = query.message.id
    await query.answer("ᴘᴏsᴛɪɴɢ...")
    new_id = await _post_cycle(bot, promo_id)
    note = (
        f"<b>✅ ᴘᴏsᴛᴇᴅ — ᴍsɢ ɪᴅ <code>{new_id}</code></b>"
        if new_id
        else "<b>❌ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴘᴏsᴛ — ᴄʜᴇᴄᴋ ʙᴏᴛ ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴs.</b>"
    )
    await _render_promo_detail(bot, user_id, promo_id, note=note)


# ---------------- promo: preview ----------------
@Client.on_callback_query(filters.regex(r"^set:promo_preview:(\d+)$"))
async def cb_promo_preview(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    promo_id = int(query.matches[0].group(1))
    p, err = await _get_user_promo(promo_id, user_id)
    if err:
        await query.answer(err.replace("<b>", "").replace("</b>", "")[:200], show_alert=True)
        return
    await query.answer("sᴇɴᴅɪɴɢ ᴘʀᴇᴠɪᴇᴡ ʙᴇʟᴏᴡ...")
    try:
        await bot.copy_message(
            chat_id=query.message.chat.id,
            from_chat_id=p["source_chat_id"],
            message_id=p["source_msg_id"],
        )
    except Exception as e:
        await bot.send_message(
            chat_id=query.message.chat.id,
            text=f"<b>❌ ᴄᴏᴜʟᴅ ɴᴏᴛ ʟᴏᴀᴅ ᴘʀᴏᴍᴏ ᴄᴏɴᴛᴇɴᴛ:</b> <code>{e}</code>",
            parse_mode=HTML,
        )


# ---------------- promo: toggle on/off ----------------
@Client.on_callback_query(filters.regex(r"^set:promo_toggle:(\d+)$"))
async def cb_promo_toggle(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    promo_id = int(query.matches[0].group(1))
    p, err = await _get_user_promo(promo_id, user_id)
    if err:
        await query.answer(err.replace("<b>", "").replace("</b>", "")[:200], show_alert=True)
        return
    settings_state.setdefault(user_id, {})
    settings_state[user_id]["panel_chat_id"] = query.message.chat.id
    settings_state[user_id]["panel_msg_id"] = query.message.id
    new_state = not bool(p.get("enabled"))
    await db.update_promo(promo_id, enabled=new_state)
    if new_state:
        _spawn_task(bot, promo_id)
    else:
        _kill_task(promo_id)
    await query.answer("ᴏɴ" if new_state else "ᴏғғ")
    await _render_promo_detail(bot, user_id, promo_id)


# ---------------- promo: delete (confirm) ----------------
@Client.on_callback_query(filters.regex(r"^set:promo_del:(\d+)$"))
async def cb_promo_del_confirm(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    promo_id = int(query.matches[0].group(1))
    p, err = await _get_user_promo(promo_id, user_id)
    if err:
        await query.answer(err.replace("<b>", "").replace("</b>", "")[:200], show_alert=True)
        return
    settings_state.setdefault(user_id, {})
    settings_state[user_id]["panel_chat_id"] = query.message.chat.id
    settings_state[user_id]["panel_msg_id"] = query.message.id
    await query.answer()
    caption = (
        f"<b>🗑 ᴅᴇʟᴇᴛᴇ ᴘʀᴏᴍᴏ #{promo_id}?</b>\n\n"
        f"<b>ᴛᴀʀɢᴇᴛ:</b> <code>{p['target_chat']}</code>\n"
        "<b>ᴛʜɪs ᴀʟsᴏ ᴅᴇʟᴇᴛᴇs ᴛʜᴇ ʟᴀsᴛ ᴘᴏsᴛ ɪɴ ᴛʜᴇ ᴄʜᴀᴛ.</b>"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ ʏᴇs ᴅᴇʟᴇᴛᴇ", callback_data=f"set:promo_del_yes:{promo_id}"),
            InlineKeyboardButton("✖ ᴄᴀɴᴄᴇʟ", callback_data=f"set:promo:{promo_id}"),
        ]
    ])
    await _edit_panel(bot, user_id, caption, kb)


@Client.on_callback_query(filters.regex(r"^set:promo_del_yes:(\d+)$"))
async def cb_promo_del_yes(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    promo_id = int(query.matches[0].group(1))
    p, err = await _get_user_promo(promo_id, user_id)
    if err:
        await query.answer(err.replace("<b>", "").replace("</b>", "")[:200], show_alert=True)
        return
    _kill_task(promo_id)
    last_id = p.get("last_post_id")
    if last_id:
        try:
            await bot.delete_messages(p["target_chat"], last_id)
        except Exception:
            pass
    await db.delete_promo(promo_id)
    await query.answer("ᴅᴇʟᴇᴛᴇᴅ")
    await _render_promos(bot, user_id)


# ---------------- forward: set source / dest ----------------
@Client.on_callback_query(filters.regex(r"^set:src$"))
async def cb_set_src(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    settings_state.setdefault(user_id, {})
    settings_state[user_id]["panel_chat_id"] = query.message.chat.id
    settings_state[user_id]["panel_msg_id"] = query.message.id
    await query.answer()
    await _prompt(
        bot, user_id,
        "<b>📤 sᴇᴛ sᴏᴜʀᴄᴇ ᴄʜᴀɴɴᴇʟ</b>\n\n"
        "<b>sᴇɴᴅ ᴛʜᴇ sᴏᴜʀᴄᴇ ᴄʜᴀɴɴᴇʟ ɪᴅ ᴏʀ @ᴜsᴇʀɴᴀᴍᴇ.</b>\n\n"
        "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>@mychannel</code> ᴏʀ <code>-1001234567890</code>",
        awaiting="set_source",
    )


@Client.on_callback_query(filters.regex(r"^set:dst$"))
async def cb_set_dst(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    settings_state.setdefault(user_id, {})
    settings_state[user_id]["panel_chat_id"] = query.message.chat.id
    settings_state[user_id]["panel_msg_id"] = query.message.id
    await query.answer()
    await _prompt(
        bot, user_id,
        "<b>📥 sᴇᴛ ᴅᴇsᴛɪɴᴀᴛɪᴏɴ ᴄʜᴀɴɴᴇʟ</b>\n\n"
        "<b>sᴇɴᴅ ᴛʜᴇ ᴅᴇsᴛɪɴᴀᴛɪᴏɴ ᴄʜᴀɴɴᴇʟ ɪᴅ ᴏʀ @ᴜsᴇʀɴᴀᴍᴇ.</b>\n\n"
        "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>@mychannel</code> ᴏʀ <code>-1001234567890</code>",
        awaiting="set_dest",
    )


# ---------------- forward: clear settings ----------------
@Client.on_callback_query(filters.regex(r"^set:fwd_clear$"))
async def cb_fwd_clear_confirm(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    settings_state.setdefault(user_id, {})
    settings_state[user_id]["panel_chat_id"] = query.message.chat.id
    settings_state[user_id]["panel_msg_id"] = query.message.id
    await query.answer()
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ ʏᴇs ᴄʟᴇᴀʀ", callback_data="set:fwd_clear_yes"),
            InlineKeyboardButton("✖ ᴄᴀɴᴄᴇʟ", callback_data="set:main"),
        ]
    ])
    await _edit_panel(
        bot, user_id,
        "<b>🧹 ᴄʟᴇᴀʀ ғᴏʀᴡᴀʀᴅ sᴇᴛᴛɪɴɢs?</b>\n\n"
        "<b>ᴛʜɪs ʀᴇᴍᴏᴠᴇs ʏᴏᴜʀ sᴀᴠᴇᴅ sᴏᴜʀᴄᴇ ᴀɴᴅ ᴅᴇsᴛɪɴᴀᴛɪᴏɴ.</b>\n"
        "<b>(ʟᴏɢɪɴ sᴇssɪᴏɴ ɪs ɴᴏᴛ ᴀғғᴇᴄᴛᴇᴅ.)</b>",
        kb,
    )


@Client.on_callback_query(filters.regex(r"^set:fwd_clear_yes$"))
async def cb_fwd_clear_yes(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    await db.clear_user_setting(user_id, "source")
    await db.clear_user_setting(user_id, "destination")
    await query.answer("ᴄʟᴇᴀʀᴇᴅ")
    await _render_main(bot, user_id)


# ---------------- logout ----------------
@Client.on_callback_query(filters.regex(r"^set:logout$"))
async def cb_logout_confirm(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    session = await db.get_session(user_id)
    settings_state.setdefault(user_id, {})
    settings_state[user_id]["panel_chat_id"] = query.message.chat.id
    settings_state[user_id]["panel_msg_id"] = query.message.id
    await query.answer()
    if not session:
        await _edit_panel(
            bot, user_id,
            "<b>🚪 ʟᴏɢᴏᴜᴛ</b>\n\n<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ʟᴏɢɢᴇᴅ ɪɴ.</b>",
            _back_kb(),
        )
        return
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ ʏᴇs ʟᴏɢ ᴍᴇ ᴏᴜᴛ", callback_data="set:logout_yes"),
            InlineKeyboardButton("✖ ᴄᴀɴᴄᴇʟ", callback_data="set:main"),
        ]
    ])
    await _edit_panel(
        bot, user_id,
        "<b>🚪 ʟᴏɢᴏᴜᴛ?</b>\n\n"
        "<b>ᴛʜɪs ʀᴇᴍᴏᴠᴇs ʏᴏᴜʀ sᴀᴠᴇᴅ ᴛᴇʟᴇɢʀᴀᴍ sᴇssɪᴏɴ. ʏᴏᴜ'ʟʟ ɴᴇᴇᴅ ᴛᴏ "
        "/login ᴀɢᴀɪɴ ʙᴇғᴏʀᴇ ʏᴏᴜ ᴄᴀɴ /forward.</b>",
        kb,
    )


@Client.on_callback_query(filters.regex(r"^set:logout_yes$"))
async def cb_logout_yes(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    await db.delete_session(user_id)
    await query.answer("ʟᴏɢɢᴇᴅ ᴏᴜᴛ")
    await _render_main(bot, user_id)


# ---------------- login help ----------------
@Client.on_callback_query(filters.regex(r"^set:login_help$"))
async def cb_login_help(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    settings_state.setdefault(user_id, {})
    settings_state[user_id]["panel_chat_id"] = query.message.chat.id
    settings_state[user_id]["panel_msg_id"] = query.message.id
    await query.answer()
    await _edit_panel(
        bot, user_id,
        "<b>🔑 ʟᴏɢɪɴ — ɪɴᴛᴇʀᴀᴄᴛɪᴠᴇ</b>\n\n"
        "<b>ᴛʜᴇ ʟᴏɢɪɴ ғʟᴏᴡ ᴀsᴋs ғᴏʀ ʏᴏᴜʀ ᴘʜᴏɴᴇ, ᴄᴏᴅᴇ, ᴀɴᴅ 2ғᴀ ᴘᴀssᴡᴏʀᴅ "
        "(ɪғ sᴇᴛ). ʀᴜɴ ɪᴛ ᴀs ᴀ ᴄᴏᴍᴍᴀɴᴅ:</b>\n\n"
        "<b>1.</b> sᴇɴᴅ <code>/login</code>\n"
        "<b>2.</b> ғᴏʟʟᴏᴡ ᴛʜᴇ ᴘʀᴏᴍᴘᴛs\n"
        "<b>3.</b> ᴡʜᴇɴ ᴛᴇʟᴇɢʀᴀᴍ sᴇɴᴅs ᴛʜᴇ ᴄᴏᴅᴇ, ᴛʏᴘᴇ ɪᴛ ᴡɪᴛʜ sᴘᴀᴄᴇs (e.g. <code>1 2 3 4 5</code>) "
        "ᴏᴛʜᴇʀᴡɪsᴇ ᴛᴇʟᴇɢʀᴀᴍ ᴍᴀʏ ɪɴᴠᴀʟɪᴅᴀᴛᴇ ɪᴛ\n"
        "<b>4.</b> sᴇɴᴅ <code>/cancel</code> ᴀᴛ ᴀɴʏ ᴛɪᴍᴇ ᴛᴏ ᴀʙᴏʀᴛ\n\n"
        "<b>ᴀғᴛᴇʀ ʟᴏɢɪɴ:</b> ᴜsᴇ <code>/setsource</code>, <code>/setdest</code>, "
        "<code>/forward &lt;link&gt;</code> — ᴏʀ ᴜsᴇ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ɪɴ ᴛʜɪs ᴘᴀɴᴇʟ.",
        _back_kb(),
    )


# ------------------------------------------------------------------
# Capture user input while the panel is awaiting something.
# Runs at group=-2 so it fires *before* promo's capture (-1) and
# logins.py's catch-all (group 0).
# ------------------------------------------------------------------
async def _settings_capture_filter(_, __, message: Message) -> bool:
    if not message.from_user:
        return False
    if message.chat.type != enums.ChatType.PRIVATE:
        return False
    state = settings_state.get(message.from_user.id)
    if not state or not state.get("awaiting"):
        return False
    if message.text and message.text.startswith("/"):
        return False
    return True


@Client.on_message(
    filters.private & filters.create(_settings_capture_filter),
    group=-2,
)
async def settings_capture(bot: Client, message: Message):
    user_id = message.from_user.id
    state = settings_state.get(user_id)
    if not state:
        return
    awaiting = state.get("awaiting")

    # Best-effort: delete the user's input message so the chat stays clean.
    # Bots can delete incoming messages in private chats.
    asyncio.create_task(_safe_delete(bot, message.chat.id, message.id))

    try:
        if awaiting == "promo_target":
            await _handle_promo_target(bot, user_id, message)
        elif awaiting == "promo_content":
            await _handle_promo_content(bot, user_id, message)
        elif awaiting and awaiting.startswith("promo_time:"):
            promo_id = int(awaiting.split(":", 1)[1])
            await _handle_promo_time(bot, user_id, promo_id, message)
        elif awaiting and awaiting.startswith("promo_edit:"):
            promo_id = int(awaiting.split(":", 1)[1])
            await _handle_promo_edit(bot, user_id, promo_id, message)
        elif awaiting == "set_source":
            await _handle_set_fwd(bot, user_id, message, "source")
        elif awaiting == "set_dest":
            await _handle_set_fwd(bot, user_id, message, "destination")
    finally:
        raise StopPropagation


async def _handle_promo_target(bot: Client, user_id: int, message: Message):
    text = (message.text or "").strip()
    if not text:
        await _prompt(
            bot, user_id,
            "<b>❌ sᴇɴᴅ ᴀ ᴄʜᴀᴛ ɪᴅ ᴏʀ @ᴜsᴇʀɴᴀᴍᴇ ᴀs ᴛᴇxᴛ.</b>",
            awaiting="promo_target",
        )
        return

    err = await _check_promo_limit(user_id)
    if err:
        await _edit_panel(
            bot, user_id, err,
            _back_kb([[InlineKeyboardButton("📋 ᴍʏ ᴘʀᴏᴍᴏs", callback_data="set:promos")]]),
        )
        return

    target = _parse_chat(text)
    chat, err = await _validate_target_for_user(bot, target, user_id)
    if err:
        await _prompt(
            bot, user_id,
            f"{err}\n\n<b>sᴇɴᴅ ᴀɴᴏᴛʜᴇʀ ᴄʜᴀᴛ ɪᴅ / @ᴜsᴇʀɴᴀᴍᴇ ᴏʀ ᴄᴀɴᴄᴇʟ.</b>",
            awaiting="promo_target",
        )
        return

    await _prompt(
        bot, user_id,
        f"<b>✅ ᴛᴀʀɢᴇᴛ ᴏᴋ:</b> <code>{chat.title or chat.id}</code>\n\n"
        f"<b>➕ ɴᴇᴡ ᴘʀᴏᴍᴏ — sᴛᴇᴘ 2/2</b>\n\n"
        "<b>ɴᴏᴡ sᴇɴᴅ ᴛʜᴇ ᴘʀᴏᴍᴏ ᴄᴏɴᴛᴇɴᴛ.</b>\n"
        "<b>ᴀʟʟᴏᴡᴇᴅ:</b> ᴛᴇxᴛ, ᴘʜᴏᴛᴏ, ᴠɪᴅᴇᴏ, ᴀᴜᴅɪᴏ, ᴀɴɪᴍᴀᴛɪᴏɴ, sᴛɪᴄᴋᴇʀ, "
        "ᴅᴏᴄᴜᴍᴇɴᴛ — ᴀɴʏ ᴄᴏᴍʙᴏ. <b>ᴀʟʟ ғᴏʀᴍᴀᴛᴛɪɴɢ ᴋᴇᴘᴛ.</b>",
        awaiting="promo_content",
        ctx={
            "target_chat": chat.id,
            "target_title": chat.title or str(chat.id),
        },
    )


async def _handle_promo_content(bot: Client, user_id: int, message: Message):
    state = settings_state.get(user_id, {})
    ctx = state.get("ctx") or {}
    target_chat = ctx.get("target_chat")
    target_title = ctx.get("target_title", str(target_chat))

    if not target_chat:
        await _render_main(bot, user_id)
        return

    err = await _check_promo_limit(user_id)
    if err:
        await _edit_panel(
            bot, user_id, err,
            _back_kb([[InlineKeyboardButton("📋 ᴍʏ ᴘʀᴏᴍᴏs", callback_data="set:promos")]]),
        )
        return

    promo_id = await db.add_promo(
        owner_id=user_id,
        target_chat=target_chat,
        source_chat_id=message.chat.id,
        source_msg_id=message.id,
        interval_minutes=20,
    )
    _spawn_task(bot, promo_id)
    await _render_promo_detail(
        bot, user_id, promo_id,
        note=f"<b>✅ ᴄʀᴇᴀᴛᴇᴅ ᴀs ᴘʀᴏᴍᴏ #{promo_id} — ʟᴏᴏᴘ sᴛᴀʀᴛᴇᴅ.</b>",
    )


async def _handle_promo_time(bot: Client, user_id: int, promo_id: int,
                             message: Message):
    text = (message.text or "").strip()
    try:
        minutes = int(text)
        assert minutes >= 1
    except Exception:
        await _prompt(
            bot, user_id,
            "<b>❌ sᴇɴᴅ ᴀ ᴡʜᴏʟᴇ ɴᴜᴍʙᴇʀ ≥ 1.</b>",
            awaiting=f"promo_time:{promo_id}",
        )
        return
    p, err = await _get_user_promo(promo_id, user_id)
    if err:
        await _edit_panel(bot, user_id, err, _back_kb())
        return
    await db.update_promo(promo_id, interval_minutes=minutes)
    if p.get("enabled"):
        _spawn_task(bot, promo_id)
    await _render_promo_detail(
        bot, user_id, promo_id,
        note=f"<b>✅ ɪɴᴛᴇʀᴠᴀʟ sᴇᴛ ᴛᴏ {minutes} ᴍɪɴ.</b>",
    )


async def _handle_promo_edit(bot: Client, user_id: int, promo_id: int,
                             message: Message):
    p, err = await _get_user_promo(promo_id, user_id)
    if err:
        await _edit_panel(bot, user_id, err, _back_kb())
        return
    await db.update_promo(
        promo_id,
        source_chat_id=message.chat.id,
        source_msg_id=message.id,
    )
    if p.get("enabled"):
        _spawn_task(bot, promo_id)
    await _render_promo_detail(
        bot, user_id, promo_id,
        note="<b>✅ ᴄᴏɴᴛᴇɴᴛ ᴜᴘᴅᴀᴛᴇᴅ — ʟᴏᴏᴘ ʀᴇsᴛᴀʀᴛᴇᴅ.</b>",
    )


async def _handle_set_fwd(bot: Client, user_id: int, message: Message,
                          key: str):
    text = (message.text or "").strip()
    if not text:
        await _prompt(
            bot, user_id,
            "<b>❌ sᴇɴᴅ ᴀ ᴄʜᴀɴɴᴇʟ ɪᴅ ᴏʀ @ᴜsᴇʀɴᴀᴍᴇ ᴀs ᴛᴇxᴛ.</b>",
            awaiting=f"set_{'source' if key == 'source' else 'dest'}",
        )
        return
    await db.set_user_setting(user_id, key, text)
    await _render_main(bot, user_id)
