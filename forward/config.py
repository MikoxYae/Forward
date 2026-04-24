import os

MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb+srv://Payal:Aloksingh@payal.jv2kwch.mongodb.net/?appName=Payal",
)
DB_NAME = os.environ.get("DATABASE_NAME", "Anything")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

APP_ID = int(os.environ.get("APP_ID", "28614709"))
API_HASH = os.environ.get("API_HASH", "f36fd2ee6e3d3a17c4d244ff6dc1bac8")

OWNER = os.environ.get("OWNER", "Anythingbutnew56")
OWNER_ID = int(os.environ.get("OWNER_ID", "8229041976"))

START_PIC = os.environ.get(
    "START_PIC",
    "https://graph.org/file/b4864a63946e9b1e84238-ccb51f7ec7e7c11458.jpg",
)
