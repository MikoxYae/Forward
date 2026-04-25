import asyncio
import logging
import os
import signal

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

        # Start the promo scheduler so any enabled promos resume on restart.
        try:
            from plugins.promo import start_promo_scheduler
            await start_promo_scheduler(self)
        except Exception as e:
            log.error(f"Failed to start promo scheduler: {e}")

    async def stop(self, *args):
        # Cancel every promo background task BEFORE we tear pyrogram down,
        # otherwise super().stop() can hang indefinitely waiting on them.
        try:
            from plugins.promo import _running_tasks
            for _pid, task in list(_running_tasks.items()):
                if task and not task.done():
                    task.cancel()
            _running_tasks.clear()
            await asyncio.sleep(0.3)
        except Exception as e:
            log.info(f"promo cleanup skipped: {e}")

        await super().stop()
        log.info("Bot stopped.")


async def _amain():
    """Custom main loop with proper signal handling.

    Pyrogram's built-in Client.run() uses an idle() that swallows
    repeated Ctrl+C presses — if anything hangs during shutdown the
    process never actually exits and the user sees the same
    'Stop signal received' line over and over. Here we:
      * shut down gracefully on the first SIGINT/SIGTERM
      * give the shutdown 10 seconds, then force exit
      * force exit immediately on the SECOND Ctrl+C
    """
    bot = Miko()
    await bot.start()

    stop_event = asyncio.Event()
    presses = 0
    loop = asyncio.get_running_loop()

    def _on_signal():
        nonlocal presses
        presses += 1
        if presses == 1:
            log.info(
                "Stop signal received — shutting down "
                "(press Ctrl+C again to force exit)..."
            )
            stop_event.set()
        else:
            log.warning("Second stop signal — forcing exit.")
            os._exit(1)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            # Windows / restricted env — fall back to default handler.
            pass

    try:
        await stop_event.wait()
    finally:
        try:
            await asyncio.wait_for(bot.stop(), timeout=10)
        except asyncio.TimeoutError:
            log.error("Graceful stop timed out after 10s — forcing exit.")
            os._exit(1)
        except Exception as e:
            log.error(f"shutdown error: {e}")
            os._exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        # asyncio.run already cleaned up; just exit quietly.
        pass
