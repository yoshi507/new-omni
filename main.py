"""OmniBot entrypoint — Discord or GameVox bot + dashboard API on one process.

Works even if the GitHub zip left files under new-omni-main/ or similar:
we locate the directory that contains both this file and the omnibot package.

Platform:
  PLATFORM=discord   (default) — normal Discord
  PLATFORM=gamevox   — GameVox (Discord-compatible API)
Set GAMEVOX_BOT_TOKEN when using GameVox. One process = one platform
(discord.py uses global REST/gateway URLs). Run two servers to be on both.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path


def _bootstrap_path() -> Path:
    """Ensure the project root (folder with omnibot/) is on sys.path and cwd."""
    here = Path(__file__).resolve().parent
    candidates = [
        here,
        Path.cwd(),
        *here.parents[:3],
        *Path.cwd().parents[:3],
    ]
    # Also scan one level of subdirs (GitHub zip: new-omni-main/)
    for base in (here, Path.cwd()):
        try:
            for child in base.iterdir():
                if child.is_dir():
                    candidates.append(child)
        except OSError:
            pass

    seen: set[Path] = set()
    for root in candidates:
        try:
            root = root.resolve()
        except OSError:
            continue
        if root in seen:
            continue
        seen.add(root)
        if (root / "omnibot" / "__init__.py").is_file() or (root / "omnibot" / "config.py").is_file():
            root_s = str(root)
            if root_s not in sys.path:
                sys.path.insert(0, root_s)
            try:
                import os

                os.chdir(root)
            except OSError:
                pass
            return root

    # Last resort: keep current dir on path
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    return Path.cwd()


_PROJECT_ROOT = _bootstrap_path()

import uvicorn

from omnibot import DEPLOY_MARKER
from omnibot.bot import OmniBot
from omnibot.config import settings
from omnibot.platform import PLATFORM_GAMEVOX, configure_platform, resolve_bot_token
from omnibot.web.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("omnibot")


async def run() -> None:
    # Must patch discord.py endpoints BEFORE the bot connects
    platform = configure_platform(settings.platform)
    token = resolve_bot_token(platform)

    if not token:
        if platform == PLATFORM_GAMEVOX:
            log.error(
                "GAMEVOX_BOT_TOKEN is missing. Create a bot at https://developers.gamevox.com "
                "and set GAMEVOX_BOT_TOKEN (and PLATFORM=gamevox)."
            )
        else:
            log.error("DISCORD_TOKEN is missing. Set it in .env or panel env vars and restart.")
        sys.exit(1)

    log.info("[Startup] projectRoot=%s platform=%s", _PROJECT_ROOT, platform)

    bot = OmniBot()
    bot.platform = platform  # type: ignore[attr-defined]
    app = create_app(bot=bot, deploy_marker=DEPLOY_MARKER)

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=settings.port,
        log_level="info",
        access_log=False,
        ssl_keyfile=settings.ssl_key_path or None,
        ssl_certfile=settings.ssl_cert_path or None,
    )
    server = uvicorn.Server(config)

    log.info("[Startup] deployMarker=%s", DEPLOY_MARKER)
    log.info("[Startup] PORT=%s PUBLIC_BASE_URL=%s", settings.port, settings.public_base_url)
    log.info(
        "[Startup] groq=%s model=%s",
        "ready" if settings.groq_api_key else "not-configured",
        settings.groq_model,
    )
    log.info("[Startup] image=%s", "ready" if settings.home_mode_api_url else "not-configured")

    async def start_bot() -> None:
        async with bot:
            await bot.start(token)

    bot_task = asyncio.create_task(start_bot(), name=f"{platform}-bot")
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
