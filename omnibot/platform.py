"""Platform targets: Discord (default) and GameVox.

GameVox is Discord-API compatible. Official docs:
https://developers.gamevox.com/docs/migrating/

  REST:    https://app-api.gamevox.com/api/v10
  Gateway: wss://gateway.gamevox.com/?v=10&encoding=json

Call `configure_platform()` once at process start, before creating the bot.
discord.py stores these as module globals, so one process = one platform.
To run on both Discord and GameVox at once, run two processes
(PLATFORM=discord and PLATFORM=gamevox) with separate tokens.
"""
from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)

log = logging.getLogger("omnibot.platform")

PLATFORM_DISCORD = "discord"
PLATFORM_GAMEVOX = "gamevox"

GAMEVOX_REST_BASE = "https://app-api.gamevox.com/api/v10"
# Base URL only — discord.py adds ?v=10&encoding=json itself via yarl.URL.with_query().
GAMEVOX_GATEWAY = "wss://gateway.gamevox.com/"

# Official Discord defaults (for restore / logging)
DISCORD_REST_BASE = "https://discord.com/api/v10"
DISCORD_GATEWAY = "wss://gateway.discord.gg/"


def resolve_platform() -> str:
    raw = (os.getenv("PLATFORM") or os.getenv("BOT_PLATFORM") or "discord").strip().lower()
    if raw in ("gamevox", "gv", "game-vox"):
        return PLATFORM_GAMEVOX
    return PLATFORM_DISCORD


def configure_platform(platform: str | None = None) -> str:
    """Patch discord.py REST + gateway URLs for the chosen platform.

    Must run before OmniBot is constructed / started.
    Returns the resolved platform name.
    """
    import yarl
    from discord.gateway import DiscordWebSocket
    from discord.http import Route

    plat = (platform or resolve_platform()).strip().lower()
    if plat in ("gamevox", "gv", "game-vox"):
        Route.BASE = GAMEVOX_REST_BASE
        # Must be a yarl.URL: discord.py 2.7 calls DEFAULT_GATEWAY.with_query(...).
        # (GameVox's docs show a plain string, which crashes on connect.)
        DiscordWebSocket.DEFAULT_GATEWAY = yarl.URL(GAMEVOX_GATEWAY)
        log.info("Platform=GameVox · REST=%s · gateway=%s", GAMEVOX_REST_BASE, GAMEVOX_GATEWAY)
        return PLATFORM_GAMEVOX

    # Discord: same values as discord.py's own defaults.
    Route.BASE = DISCORD_REST_BASE
    DiscordWebSocket.DEFAULT_GATEWAY = yarl.URL(DISCORD_GATEWAY)
    log.info("Platform=Discord · REST=%s", Route.BASE)
    return PLATFORM_DISCORD


def resolve_bot_token(platform: str) -> str:
    """Pick the right token for the platform."""
    if platform == PLATFORM_GAMEVOX:
        token = (
            os.getenv("GAMEVOX_BOT_TOKEN")
            or os.getenv("GAMEVOX_TOKEN")
            or os.getenv("DISCORD_TOKEN")
            or ""
        ).strip()
        return token
    return (os.getenv("DISCORD_TOKEN") or "").strip()
