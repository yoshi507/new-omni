"""Discord OAuth2 helpers."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from omnibot.config import settings

log = logging.getLogger("omnibot.oauth")

API = "https://discord.com/api/v10"


def login_url(state: str) -> str:
    redirect = settings.discord_redirect_uri
    cid = settings.discord_client_id
    scope = "identify%20guilds"
    return (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={cid}&redirect_uri={httpx.URL(redirect)}"
        f"&response_type=code&scope={scope}&state={state}&prompt=none"
    )


async def exchange_code(code: str, redirect_uri: str | None = None) -> dict[str, Any]:
    redirect = redirect_uri or settings.discord_redirect_uri
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{API}/oauth2/token",
            data={
                "client_id": settings.discord_client_id,
                "client_secret": settings.discord_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if r.status_code >= 400:
            log.error("OAuth token error %s: %s", r.status_code, r.text[:300])
            raise RuntimeError(f"OAuth token exchange failed ({r.status_code})")
        return r.json()


async def fetch_user(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            f"{API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        return r.json()


async def fetch_user_guilds(access_token: str) -> list[dict[str, Any]]:
    """Fetch guilds with retry on 429 rate limits."""
    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(4):
            try:
                r = await client.get(
                    f"{API}/users/@me/guilds",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if r.status_code == 429:
                    retry = float(r.headers.get("Retry-After") or r.json().get("retry_after") or 1.5)
                    log.warning("Discord guilds rate-limited, sleeping %.1fs", retry)
                    await asyncio.sleep(min(retry, 5.0))
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                await asyncio.sleep(0.4 * (attempt + 1))
        raise RuntimeError(f"fetch_user_guilds failed: {last_err}")


def can_manage(guild: dict[str, Any]) -> bool:
    perms = int(guild.get("permissions", 0) or 0)
    # ADMINISTRATOR or MANAGE_GUILD
    return bool(perms & 0x8) or bool(perms & 0x20)
