"""Session store for Discord OAuth — memory + disk so restarts keep you logged in."""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any

from omnibot.config import DATA_DIR

log = logging.getLogger("omnibot.sessions")

_SESSIONS: dict[str, dict[str, Any]] = {}
TTL = 60 * 60 * 24 * 7  # 7 days
GUILDS_CACHE_TTL = 300  # 5 minutes
_STORE = DATA_DIR / "sessions.json"
_guilds_lock = asyncio.Lock()
_dirty = False
_last_save = 0.0


def _load() -> None:
    global _SESSIONS
    if not _STORE.exists():
        return
    try:
        raw = json.loads(_STORE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return
        now = time.time()
        cleaned = {}
        for sid, s in raw.items():
            if not isinstance(s, dict):
                continue
            if float(s.get("expires") or 0) < now:
                continue
            cleaned[sid] = s
        _SESSIONS = cleaned
        log.info("Loaded %s session(s) from disk", len(_SESSIONS))
    except Exception as e:
        log.warning("Could not load sessions: %s", e)


def _save(force: bool = False) -> None:
    global _dirty, _last_save
    now = time.time()
    if not force and not _dirty:
        return
    if not force and (now - _last_save) < 2.0:
        return
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {}
        for sid, s in _SESSIONS.items():
            payload[sid] = {
                "user": s.get("user"),
                "access_token": s.get("access_token"),
                "created": s.get("created"),
                "expires": s.get("expires"),
                "guilds": s.get("guilds"),
                "guilds_fetched_at": s.get("guilds_fetched_at", 0),
            }
        tmp = _STORE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(_STORE)
        _dirty = False
        _last_save = now
    except Exception as e:
        log.warning("Could not save sessions: %s", e)


_load()


def create(user: dict[str, Any], access_token: str) -> str:
    global _dirty
    sid = secrets.token_urlsafe(32)
    _SESSIONS[sid] = {
        "user": user,
        "access_token": access_token,
        "created": time.time(),
        "expires": time.time() + TTL,
        "guilds": None,
        "guilds_fetched_at": 0.0,
    }
    _dirty = True
    _save(force=True)
    return sid


def get(sid: str | None) -> dict[str, Any] | None:
    global _dirty
    if not sid:
        return None
    s = _SESSIONS.get(sid)
    if not s:
        return None
    if time.time() > float(s.get("expires") or 0):
        _SESSIONS.pop(sid, None)
        _dirty = True
        _save(force=True)
        return None
    return s


def destroy(sid: str | None) -> None:
    global _dirty
    if sid and sid in _SESSIONS:
        _SESSIONS.pop(sid, None)
        _dirty = True
        _save(force=True)


def get_cached_guilds(sess: dict[str, Any], *, allow_stale: bool = False) -> list[dict[str, Any]] | None:
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
    global _dirty
    sess["guilds"] = guilds
    sess["guilds_fetched_at"] = time.time()
    _dirty = True
    _save()


def guilds_lock() -> asyncio.Lock:
    return _guilds_lock
