"""Removed. OmniBot is Discord-only again. This file is a no-op stub."""
from __future__ import annotations

PLATFORM_DISCORD = "discord"
PLATFORM_GAMEVOX = "discord"  # legacy alias — ignored


def resolve_platform() -> str:
    return PLATFORM_DISCORD


def configure_platform(platform: str | None = None) -> str:
    return PLATFORM_DISCORD


def resolve_bot_token(platform: str = "discord") -> str:
    import os

    return (os.getenv("DISCORD_TOKEN") or "").strip()
