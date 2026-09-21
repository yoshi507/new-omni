"""OmniBot entrypoint — Discord bot + dashboard API on one process."""
from __future__ import annotations

import asyncio
import logging
import sys

import uvicorn

from omnibot.config import settings
from omnibot.bot import OmniBot
from omnibot.web.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("omnibot")

DEPLOY_MARKER = "2026-09-21-python-rebuild-v2"


async def run() -> None:
    if not settings.discord_token:
        log.error("DISCORD_TOKEN is missing. Set it in .env and restart.")
        sys.exit(1)

    bot = OmniBot()
    bot.deploy_marker = DEPLOY_MARKER
    app = create_app(bot=bot, deploy_marker=DEPLOY_MARKER)

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=settings.port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    log.info("[Startup] deployMarker=%s", DEPLOY_MARKER)
    log.info("[Startup] PORT=%s PUBLIC_BASE_URL=%s", settings.port, settings.public_base_url)
    log.info("[Startup] groq=%s", "ready" if settings.groq_api_key else "not-configured")
    log.info("[Startup] image=%s", "ready" if settings.home_mode_api_url else "not-configured")

    async def start_bot() -> None:
        async with bot:
            await bot.start(settings.discord_token)

    bot_task = asyncio.create_task(start_bot(), name="discord-bot")
    web_task = asyncio.create_task(server.serve(), name="web-api")

    done, pending = await asyncio.wait(
        {bot_task, web_task}, return_when=asyncio.FIRST_EXCEPTION
    )
    for t in pending:
        t.cancel()
    for t in done:
        if t.exception():
            log.error("Task failed: %s", t.exception())
            raise t.exception()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Shutting down…")
