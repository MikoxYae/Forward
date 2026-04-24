from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import (
    SessionPasswordNeeded,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    PasswordHashInvalid,
    PhoneNumberInvalid,
)

from config import APP_ID, API_HASH
from database.db import db


# In-memory state per user during login
login_state: dict[int, dict] = {}


@Client.on_message(filters.command("login") & filters.private)
async def login_cmd(client, message: Message):
    user_id = message.from_user.id

    existing = await db.get_session(user_id)
    if existing:
        return await message.reply_text(
            "You are already logged in.\nUse /logout first if you want to login again."
        )

    login_state[user_id] = {"step": "phone"}
    await message.reply_text(
        "Send me your phone number with country code.\n"
        "Example: `+919876543210`\n\n"
        "Send /cancel anytime to abort."
    )


@Client.on_message(filters.command("logout") & filters.private)
async def logout_cmd(client, message: Message):
    user_id = message.from_user.id
    sess = await db.get_session(user_id)
    if not sess:
        return await message.reply_text("You are not logged in.")
    await db.delete_session(user_id)
    login_state.pop(user_id, None)
    await message.reply_text("Logged out successfully. Your session has been removed.")


@Client.on_message(filters.command("cancel") & filters.private)
async def cancel_cmd(client, message: Message):
    user_id = message.from_user.id
    state = login_state.pop(user_id, None)
    if state and "client" in state:
        try:
            await state["client"].disconnect()
        except Exception:
            pass
    if state:
        await message.reply_text("Login cancelled.")
    else:
        await message.reply_text("Nothing to cancel.")


@Client.on_message(
    filters.private
    & filters.text
    & ~filters.command(
        ["start", "help", "login", "logout", "cancel", "settings",
         "setsource", "setdest", "clearsettings", "forward", "stop", "status"]
    )
)
async def login_flow(client, message: Message):
    user_id = message.from_user.id
    if user_id not in login_state:
        return  # not in a login flow, ignore

    state = login_state[user_id]
    text = (message.text or "").strip()

    # ---------- Step 1: phone ----------
    if state["step"] == "phone":
        from pyrogram import Client as PyroClient
        phone = text
        try:
            user_client = PyroClient(
                name=f"user_{user_id}",
                api_id=APP_ID,
                api_hash=API_HASH,
                in_memory=True,
            )
            await user_client.connect()
            sent = await user_client.send_code(phone)
            state.update(
                step="code",
                phone=phone,
                phone_code_hash=sent.phone_code_hash,
                client=user_client,
            )
            await message.reply_text(
                "OTP sent to your Telegram app.\n"
                "Send the code here with **spaces between digits** "
                "(e.g. `1 2 3 4 5`) so Telegram does not invalidate it."
            )
        except PhoneNumberInvalid:
            login_state.pop(user_id, None)
            await message.reply_text("Invalid phone number. Use /login to try again.")
        except Exception as e:
            login_state.pop(user_id, None)
            await message.reply_text(f"Failed to send code: `{e}`")
        return

    # ---------- Step 2: code ----------
    if state["step"] == "code":
        code = text.replace(" ", "").replace("-", "")
        user_client = state["client"]
        try:
            await user_client.sign_in(state["phone"], state["phone_code_hash"], code)
            session_string = await user_client.export_session_string()
            await user_client.disconnect()
            await db.save_session(user_id, session_string)
            login_state.pop(user_id, None)
            await message.reply_text(
                "Login successful! Your session has been saved securely."
            )
        except SessionPasswordNeeded:
            state["step"] = "password"
            await message.reply_text(
                "Your account has 2-step verification enabled.\nSend your password."
            )
        except (PhoneCodeInvalid, PhoneCodeExpired) as e:
            login_state.pop(user_id, None)
            try:
                await user_client.disconnect()
            except Exception:
                pass
            await message.reply_text(f"Invalid / expired code: `{e}`. Use /login again.")
        except Exception as e:
            login_state.pop(user_id, None)
            try:
                await user_client.disconnect()
            except Exception:
                pass
            await message.reply_text(f"Login failed: `{e}`")
        return

    # ---------- Step 3: 2FA password ----------
    if state["step"] == "password":
        password = text
        user_client = state["client"]
        try:
            await user_client.check_password(password)
            session_string = await user_client.export_session_string()
            await user_client.disconnect()
            await db.save_session(user_id, session_string)
            login_state.pop(user_id, None)
            await message.reply_text(
                "Login successful! Your session has been saved securely."
            )
        except PasswordHashInvalid:
            await message.reply_text("Wrong password. Try again.")
        except Exception as e:
            login_state.pop(user_id, None)
            try:
                await user_client.disconnect()
            except Exception:
                pass
            await message.reply_text(f"Login failed: `{e}`")
        return
