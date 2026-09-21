"""In-memory session store for Discord OAuth."""
from __future__ import annotations

import secrets
import time
from typing import Any

_SESSIONS: dict[str, dict[str, Any]] = {}
TTL = 60 * 60 * 24 * 7  # 7 days


def create(user: dict[str, Any], access_token: str) -> str:
    sid = secrets.token_urlsafe(32)
    _SESSIONS[sid] = {
        "user": user,
        "access_token": access_token,
        "created": time.time(),
        "expires": time.time() + TTL,
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
