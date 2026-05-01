from pyrogram import Client, filters, enums
from pyrogram.types import Message, CallbackQuery
from pyrogram.errors import (
    SessionPasswordNeeded,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    PasswordHashInvalid,
    PhoneNumberInvalid,
)

from config import APP_ID, API_HASH
from database.db import db
from plugins.start import START_TEXT, start_keyboard, back_keyboard


# In-memory state per user during login.
# Each entry: { step, phone?, phone_code_hash?, client?, chat_id, msg_id, plain }
login_state: dict[int, dict] = {}


# ---------------- helpers ----------------
def _set_state(user_id: int, **kwargs):
    if user_id not in login_state:
        login_state[user_id] = {}
    login_state[user_id].update(kwargs)


async def _edit_tracked(client: Client, user_id: int, fallback_message: Message,
                        caption: str, with_back: bool = True):
    """Edit the tracked login message (photo caption or text) so login flow stays
    in the same chat bubble. Falls back to a fresh reply if editing fails."""
    state = login_state.get(user_id) or {}
    chat_id = state.get("chat_id")
    msg_id = state.get("msg_id")
    plain = state.get("plain", False)
    rmk = back_keyboard() if with_back else None

    if chat_id and msg_id:
        try:
            if plain:
                await client.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=caption,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=rmk,
                    disable_web_page_preview=True,
                )
            else:
                await client.edit_message_caption(
                    chat_id=chat_id,
                    message_id=msg_id,
                    caption=caption,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=rmk,
                )
            return
        except Exception:
            pass

    try:
        await fallback_message.reply_text(
            caption,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=rmk,
            disable_web_page_preview=True,
        )
    except Exception:
        pass


# ---------------- Login button (from /start photo) ----------------
@Client.on_callback_query(filters.regex("^login_start$"))
async def cb_login_start(client: Client, query: CallbackQuery):
    user_id = query.from_user.id

    if await db.get_session(user_id):
        try:
            await query.message.edit_caption(
                caption="<b>ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ʟᴏɢɢᴇᴅ ɪɴ. ᴜsᴇ ʟᴏɢᴏᴜᴛ ғɪʀsᴛ.</b>",
                parse_mode=enums.ParseMode.HTML,
                reply_markup=back_keyboard(),
            )
        except Exception:
            pass
        return await query.answer()

    _set_state(
        user_id,
        step="phone",
        chat_id=query.message.chat.id,
        msg_id=query.message.id,
        plain=False,
    )
    try:
        await query.message.edit_caption(
            caption=(
                "<b>sᴇɴᴅ ʏᴏᴜʀ ᴘʜᴏɴᴇ ɴᴜᴍʙᴇʀ ᴡɪᴛʜ ᴄᴏᴜɴᴛʀʏ ᴄᴏᴅᴇ.</b>\n"
                "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>+919876543210</code>"
            ),
            parse_mode=enums.ParseMode.HTML,
            reply_markup=back_keyboard(),
        )
    except Exception:
        pass
    await query.answer()


# ---------------- Logout button ----------------
@Client.on_callback_query(filters.regex("^logout_start$"))
async def cb_logout_start(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    sess = await db.get_session(user_id)

    if not sess:
        try:
            await query.message.edit_caption(
                caption="<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ʟᴏɢɢᴇᴅ ɪɴ.</b>",
                parse_mode=enums.ParseMode.HTML,
                reply_markup=back_keyboard(),
            )
        except Exception:
            pass
        return await query.answer()

    await db.delete_session(user_id)
    login_state.pop(user_id, None)
    try:
        await query.message.edit_caption(
            caption="<b>ʟᴏɢɢᴇᴅ ᴏᴜᴛ sᴜᴄᴄᴇssғᴜʟʟʏ. ʏᴏᴜʀ sᴇssɪᴏɴ ʜᴀs ʙᴇᴇɴ ʀᴇᴍᴏᴠᴇᴅ.</b>",
            parse_mode=enums.ParseMode.HTML,
            reply_markup=back_keyboard(),
        )
    except Exception:
        pass
    await query.answer()


# ---------------- Commands (text fallbacks) ----------------
@Client.on_message(filters.command("login") & filters.private)
async def login_cmd(client: Client, message: Message):
    user_id = message.from_user.id

    if await db.get_session(user_id):
        return await message.reply_text(
            "<b>ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ʟᴏɢɢᴇᴅ ɪɴ. ᴜsᴇ /logout ғɪʀsᴛ.</b>",
            parse_mode=enums.ParseMode.HTML,
        )

    sent = await message.reply_text(
        "<b>sᴇɴᴅ ʏᴏᴜʀ ᴘʜᴏɴᴇ ɴᴜᴍʙᴇʀ ᴡɪᴛʜ ᴄᴏᴜɴᴛʀʏ ᴄᴏᴅᴇ.</b>\n"
        "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>+919876543210</code>",
        parse_mode=enums.ParseMode.HTML,
    )
    _set_state(user_id, step="phone", chat_id=sent.chat.id, msg_id=sent.id, plain=True)


@Client.on_message(filters.command("cancel") & filters.private)
async def cancel_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    state = login_state.pop(user_id, None)
    if state and "client" in state:
        try:
            await state["client"].disconnect()
        except Exception:
            pass
    if state:
        await message.reply_text(
            "<b>ʟᴏɢɪɴ ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>",
            parse_mode=enums.ParseMode.HTML,
        )
    else:
        await message.reply_text(
            "<b>ɴᴏᴛʜɪɴɢ ᴛᴏ ᴄᴀɴᴄᴇʟ.</b>",
            parse_mode=enums.ParseMode.HTML,
        )


# ---------------- Login flow (phone / code / 2FA) ----------------
@Client.on_message(
    filters.private
    & filters.text
    & ~filters.command(
        ["start", "help", "login", "cancel", "settings",
         "forward", "batch", "stop", "approve",
         "stats", "chats", "broadcast",
         "setwelcome", "clearwelcome", "togglewelcome", "welcome"]
    )
)
async def login_flow(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in login_state:
        return

    state = login_state[user_id]
    text = (message.text or "").strip()

    # ---- Step 1: phone ----
    if state["step"] == "phone":
        from pyrogram import Client as PyroClient
        phone = text
        try:
            uc = PyroClient(
                name=f"user_{user_id}",
                api_id=APP_ID,
                api_hash=API_HASH,
                in_memory=True,
            )
            await uc.connect()
            sent = await uc.send_code(phone)
            state.update(
                step="code",
                phone=phone,
                phone_code_hash=sent.phone_code_hash,
                client=uc,
            )
            await _edit_tracked(
                client, user_id, message,
                "<b>ᴏᴛᴘ sᴇɴᴛ ᴛᴏ ʏᴏᴜʀ ᴛᴇʟᴇɢʀᴀᴍ ᴀᴘᴘ.</b>\n"
                "<b>sᴇɴᴅ ᴛʜᴇ ᴄᴏᴅᴇ ᴡɪᴛʜ sᴘᴀᴄᴇs ʙᴇᴛᴡᴇᴇɴ ᴅɪɢɪᴛs (ᴇ.ɢ.</b> "
                "<code>1 2 3 4 5</code><b>) sᴏ ᴛᴇʟᴇɢʀᴀᴍ ᴅᴏᴇs ɴᴏᴛ ɪɴᴠᴀʟɪᴅᴀᴛᴇ ɪᴛ.</b>",
            )
        except PhoneNumberInvalid:
            login_state.pop(user_id, None)
            await _edit_tracked(
                client, user_id, message,
                "<b>ɪɴᴠᴀʟɪᴅ ᴘʜᴏɴᴇ ɴᴜᴍʙᴇʀ. ᴛʀʏ ᴀɢᴀɪɴ.</b>",
            )
        except Exception as e:
            login_state.pop(user_id, None)
            await _edit_tracked(
                client, user_id, message,
                f"<b>ғᴀɪʟᴇᴅ ᴛᴏ sᴇɴᴅ ᴄᴏᴅᴇ:</b> <code>{e}</code>",
            )
        return

    # ---- Step 2: OTP code ----
    if state["step"] == "code":
        code = text.replace(" ", "").replace("-", "")
        uc = state["client"]
        try:
            await uc.sign_in(state["phone"], state["phone_code_hash"], code)
            ss = await uc.export_session_string()
            await uc.disconnect()
            await db.save_session(user_id, ss)
            login_state.pop(user_id, None)
            await _edit_tracked(
                client, user_id, message,
                "<b>ʟᴏɢɪɴ sᴜᴄᴄᴇssғᴜʟ. ʏᴏᴜʀ sᴇssɪᴏɴ ʜᴀs ʙᴇᴇɴ sᴀᴠᴇᴅ sᴇᴄᴜʀᴇʟʏ.</b>",
            )
        except SessionPasswordNeeded:
            state["step"] = "password"
            await _edit_tracked(
                client, user_id, message,
                "<b>ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ ʜᴀs ᴛᴡᴏ-sᴛᴇᴘ ᴠᴇʀɪғɪᴄᴀᴛɪᴏɴ. sᴇɴᴅ ʏᴏᴜʀ ᴘᴀssᴡᴏʀᴅ.</b>",
            )
        except (PhoneCodeInvalid, PhoneCodeExpired) as e:
            login_state.pop(user_id, None)
            try:
                await uc.disconnect()
            except Exception:
                pass
            await _edit_tracked(
                client, user_id, message,
                f"<b>ɪɴᴠᴀʟɪᴅ ᴏʀ ᴇxᴘɪʀᴇᴅ ᴄᴏᴅᴇ:</b> <code>{e}</code>",
            )
        except Exception as e:
            login_state.pop(user_id, None)
            try:
                await uc.disconnect()
            except Exception:
                pass
            await _edit_tracked(
                client, user_id, message,
                f"<b>ʟᴏɢɪɴ ғᴀɪʟᴇᴅ:</b> <code>{e}</code>",
            )
        return

    # ---- Step 3: 2FA password ----
    if state["step"] == "password":
        uc = state["client"]
        try:
            await uc.check_password(text)
            ss = await uc.export_session_string()
            await uc.disconnect()
            await db.save_session(user_id, ss)
            login_state.pop(user_id, None)
            await _edit_tracked(
                client, user_id, message,
                "<b>ʟᴏɢɪɴ sᴜᴄᴄᴇssғᴜʟ. ʏᴏᴜʀ sᴇssɪᴏɴ ʜᴀs ʙᴇᴇɴ sᴀᴠᴇᴅ sᴇᴄᴜʀᴇʟʏ.</b>",
            )
        except PasswordHashInvalid:
            await _edit_tracked(
                client, user_id, message,
                "<b>ᴡʀᴏɴɢ ᴘᴀssᴡᴏʀᴅ. ᴛʀʏ ᴀɢᴀɪɴ.</b>",
            )
        except Exception as e:
            login_state.pop(user_id, None)
            try:
                await uc.disconnect()
            except Exception:
                pass
            await _edit_tracked(
                client, user_id, message,
                f"<b>ʟᴏɢɪɴ ғᴀɪʟᴇᴅ:</b> <code>{e}</code>",
            )
        return
