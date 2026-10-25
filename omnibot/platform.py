"""Platform targets: Discord (default) and GameVox.

GameVox is Discord-API compatible. Official docs:
https://developers.gamevox.com/docs/migrating/

  REST:    https://app-api.gamevox.com/api/v10
  Gateway: wss://gateway.gamevox.com/

Call `configure_platform()` once at process start, before creating the bot.
discord.py stores these as module globals, so one process = one platform.
To run on both Discord and GameVox at once, run two processes
(PLATFORM=discord and PLATFORM=gamevox) with separate tokens.
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("omnibot.platform")

PLATFORM_DISCORD = "discord"
PLATFORM_GAMEVOX = "gamevox"

GAMEVOX_REST_BASE = "https://app-api.gamevox.com/api/v10"
# Base URL only — discord.py adds ?v=10&encoding=json itself via yarl.URL.with_query().
GAMEVOX_GATEWAY = "wss://gateway.gamevox.com/"

DISCORD_REST_BASE = "https://discord.com/api/v10"
DISCORD_GATEWAY = "wss://gateway.discord.gg/"

_patched_channels = False


def resolve_platform() -> str:
    raw = (os.getenv("PLATFORM") or os.getenv("BOT_PLATFORM") or "discord").strip().lower()
    if raw in ("gamevox", "gv", "game-vox"):
        return PLATFORM_GAMEVOX
    return PLATFORM_DISCORD


def _fill_voice_channel_defaults(data: dict[str, Any]) -> dict[str, Any]:
    """GameVox omits several Discord voice-channel fields; discord.py KeyErrors without them."""
    d = dict(data)
    # VoiceChannel._update in discord.py requires these
    d.setdefault("bitrate", 64000)
    d.setdefault("user_limit", 0)
    d.setdefault("rtc_region", None)
    # video_quality_mode: 1 = auto
    d.setdefault("video_quality_mode", 1)
    d.setdefault("status", None)
    d.setdefault("flags", 0)
    # Common channel fields some platforms under-send
    d.setdefault("position", 0)
    d.setdefault("permission_overwrites", d.get("permission_overwrites") or [])
    d.setdefault("nsfw", False)
    d.setdefault("rate_limit_per_user", 0)
    return d


def _patch_discord_for_gamevox() -> None:
    """Monkey-patch discord.py so GUILD_CREATE with incomplete voice channels doesn't crash."""
    global _patched_channels
    if _patched_channels:
        return

    import discord.channel as channel_mod

    # VoiceChannel
    _orig_vc_update = channel_mod.VoiceChannel._update

    def _vc_update(self, guild, data):  # type: ignore[no-untyped-def]
        return _orig_vc_update(self, guild, _fill_voice_channel_defaults(data))

    channel_mod.VoiceChannel._update = _vc_update  # type: ignore[method-assign]

    # StageChannel (same required fields in discord.py)
    if hasattr(channel_mod, "StageChannel"):
        _orig_sc_update = channel_mod.StageChannel._update

        def _sc_update(self, guild, data):  # type: ignore[no-untyped-def]
            return _orig_sc_update(self, guild, _fill_voice_channel_defaults(data))

        channel_mod.StageChannel._update = _sc_update  # type: ignore[method-assign]

    # Forum / media channels sometimes miss default_reaction_emoji etc. — soft-fill if present
    for cls_name in ("ForumChannel", "MediaChannel"):
        cls = getattr(channel_mod, cls_name, None)
        if cls is None or not hasattr(cls, "_update"):
            continue
        _orig = cls._update

        def _make_soft(orig):
            def _soft(self, guild, data):
                d = dict(data)
                d.setdefault("available_tags", d.get("available_tags") or [])
                d.setdefault("default_reaction_emoji", None)
                d.setdefault("default_sort_order", None)
                d.setdefault("default_forum_layout", 0)
                d.setdefault("flags", 0)
                d.setdefault("permission_overwrites", d.get("permission_overwrites") or [])
                d.setdefault("position", 0)
                d.setdefault("nsfw", False)
                d.setdefault("rate_limit_per_user", 0)
                return orig(self, guild, d)

            return _soft

        cls._update = _make_soft(_orig)  # type: ignore[method-assign]

    _patched_channels = True
    log.info("GameVox compatibility patches applied (voice bitrate / channel defaults)")


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
        DiscordWebSocket.DEFAULT_GATEWAY = yarl.URL(GAMEVOX_GATEWAY)
        _patch_discord_for_gamevox()
        log.info("Platform=GameVox · REST=%s · gateway=%s", GAMEVOX_REST_BASE, GAMEVOX_GATEWAY)
        return PLATFORM_GAMEVOX

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
