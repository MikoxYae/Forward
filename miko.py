import logging
from pyrogram import Client
from config import APP_ID, API_HASH, BOT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

log = logging.getLogger("miko")


class Miko(Client):
    def __init__(self):
        super().__init__(
            name="miko",
            api_id=APP_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="plugins"),
            workers=50,
            sleep_threshold=10,
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        log.info(f"Bot started as @{me.username} ({me.id})")

    async def stop(self, *args):
        await super().stop()
        log.info("Bot stopped.")


if __name__ == "__main__":
    Miko().run()
