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
GAMEVOX_GATEWAY = "wss://gateway.gamevox.com/?v=10&encoding=json"

# Official Discord defaults (for restore / logging)
DISCORD_REST_BASE = "https://discord.com/api/v10"
DISCORD_GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"


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
    from discord.gateway import DiscordWebSocket
    from discord.http import Route

    plat = (platform or resolve_platform()).strip().lower()
    if plat in ("gamevox", "gv", "game-vox"):
        Route.BASE = GAMEVOX_REST_BASE
        DiscordWebSocket.DEFAULT_GATEWAY = GAMEVOX_GATEWAY
        # Some discord.py builds also read Client.http.api / connector paths later;
        # Route.BASE is what official GameVox docs set.
        log.info(
            "Platform=GameVox · REST=%s · gateway=%s",
            GAMEVOX_REST_BASE,
            GAMEVOX_GATEWAY,
        )
        return PLATFORM_GAMEVOX

    # Explicit Discord (or unknown → Discord)
    Route.BASE = DISCORD_REST_BASE
    # DEFAULT_GATEWAY may be a yarl.URL in some versions — only set string form
    try:
        DiscordWebSocket.DEFAULT_GATEWAY = DISCORD_GATEWAY
    except Exception:
        _log.debug("Ignored error", exc_info=True)
    log.info("Platform=Discord · REST=%s", getattr(Route, "BASE", DISCORD_REST_BASE))
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
