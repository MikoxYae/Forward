import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
APP_ID = int(os.environ.get("APP_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")

MONGO_URI = os.environ.get("MONGO_URI", "")
DB_NAME = os.environ.get("DATABASE_NAME", "AutoAccept")

OWNER = os.environ.get("OWNER", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

START_PIC = os.environ.get(
    "START_PIC",
    "https://graph.org/file/b4864a63946e9b1e84238-ccb51f7ec7e7c11458.jpg",
)

ACCEPT_DELAY = float(os.environ.get("ACCEPT_DELAY", "0"))

DEFAULT_WELCOME = (
    "<b>ʜᴇʟʟᴏ {mention} 👋</b>\n\n"
    "<b>ʏᴏᴜʀ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ ғᴏʀ <a href=\"{chat_link}\">{chat_title}</a> ʜᴀs ʙᴇᴇɴ ᴀᴄᴄᴇᴘᴛᴇᴅ.</b>\n"
    "<b>ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ!</b>"
)
