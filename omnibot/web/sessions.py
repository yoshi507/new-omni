"""In-memory session store for Discord OAuth."""
from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

_SESSIONS: dict[str, dict[str, Any]] = {}
TTL = 60 * 60 * 24 * 7  # 7 days
GUILDS_CACHE_TTL = 300  # 5 minutes — stop Discord rate limits

# One in-flight guilds fetch per process
_guilds_lock = asyncio.Lock()


def create(user: dict[str, Any], access_token: str) -> str:
    sid = secrets.token_urlsafe(32)
    _SESSIONS[sid] = {
        "user": user,
        "access_token": access_token,
        "created": time.time(),
        "expires": time.time() + TTL,
        "guilds": None,
        "guilds_fetched_at": 0.0,
    }
    return sid


def get(sid: str | None) -> dict[str, Any] | None:
    if not sid:
        return None
    s = _SESSIONS.get(sid)
    if not s:
        return None
    if time.time() > s["expires"]:
        _SESSIONS.pop(sid, None)
        return None
    return s


def destroy(sid: str | None) -> None:
    if sid:
        _SESSIONS.pop(sid, None)


def get_cached_guilds(sess: dict[str, Any], *, allow_stale: bool = False) -> list[dict[str, Any]] | None:
    """Return cached user guilds. allow_stale=True returns even if TTL expired."""
    guilds = sess.get("guilds")
    if guilds is None:
        return None
    if allow_stale:
        return guilds
    fetched = float(sess.get("guilds_fetched_at") or 0)
    if (time.time() - fetched) < GUILDS_CACHE_TTL:
        return guilds
    return None


def set_cached_guilds(sess: dict[str, Any], guilds: list[dict[str, Any]]) -> None:
    sess["guilds"] = guilds
    sess["guilds_fetched_at"] = time.time()


def guilds_lock() -> asyncio.Lock:
    return _guilds_lock
