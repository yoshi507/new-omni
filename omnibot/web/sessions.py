"""In-memory session store for Discord OAuth."""
from __future__ import annotations

import secrets
import time
from typing import Any

_SESSIONS: dict[str, dict[str, Any]] = {}
TTL = 60 * 60 * 24 * 7  # 7 days
GUILDS_CACHE_TTL = 60  # seconds — avoid Discord rate limits on parallel requests


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


def get_cached_guilds(sess: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Return cached user guilds if still fresh."""
    guilds = sess.get("guilds")
    fetched = float(sess.get("guilds_fetched_at") or 0)
    if guilds is not None and (time.time() - fetched) < GUILDS_CACHE_TTL:
        return guilds
    return None


def set_cached_guilds(sess: dict[str, Any], guilds: list[dict[str, Any]]) -> None:
    sess["guilds"] = guilds
    sess["guilds_fetched_at"] = time.time()
