import os
import sys


def _require(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(f"[ERROR] Required environment variable '{key}' is not set.", file=sys.stderr)
        sys.exit(1)
    return val


MONGO_URI  = _require("MONGO_URI")
BOT_TOKEN  = _require("BOT_TOKEN")
API_HASH   = _require("API_HASH")
APP_ID     = int(_require("APP_ID"))
OWNER_ID   = int(_require("OWNER_ID"))
OWNER      = _require("OWNER")

DB_NAME    = os.environ.get("DATABASE_NAME", "Forward")

START_PIC  = os.environ.get(
    "START_PIC",
    "https://graph.org/file/b4864a63946e9b1e84238-ccb51f7ec7e7c11458.jpg",
)

ACCEPT_DELAY = float(os.environ.get("ACCEPT_DELAY", "0"))

DEFAULT_WELCOME = os.environ.get(
    "DEFAULT_WELCOME",
    (
        "<b>ʜᴇʟʟᴏ {mention} 👋</b>\n\n"
        "<b>ʏᴏᴜʀ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ ғᴏʀ <a href=\"{chat_link}\">{chat_title}</a> ʜᴀs ʙᴇᴇɴ ᴀᴄᴄᴇᴘᴛᴇᴅ.</b>\n"
        "<b>ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ!</b>"
    ),
)
