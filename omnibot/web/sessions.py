"""Session store for Discord OAuth — memory + disk so restarts keep you logged in.

Security notes:
- Session IDs are only stored as SHA-256 hashes, so reading sessions.json
  does not let anyone hijack a dashboard login.
- Discord access tokens are encrypted at rest with a key derived from
  SESSION_SECRET (Fernet / AES-128-CBC + HMAC).
- Expired sessions are pruned on load and on every save.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import time
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from omnibot.config import DATA_DIR, settings

log = logging.getLogger("omnibot.sessions")

_SESSIONS: dict[str, dict[str, Any]] = {}  # key = sha256(sid)
TTL = 60 * 60 * 24 * 7  # 7 days
GUILDS_CACHE_TTL = 300  # 5 minutes
# How long a cached guild list may still be trusted if Discord is unreachable.
GUILDS_STALE_MAX = 60 * 60  # 1 hour
OAUTH_STATE_TTL = 600  # 10 minutes
_STORE = DATA_DIR / "sessions.json"
_guilds_lock = asyncio.Lock()
_dirty = False
_last_save = 0.0
_OAUTH_STATES: dict[str, float] = {}


def _fernet() -> Fernet:
    key = hashlib.sha256(("omnibot-session:" + settings.session_secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


_FERNET = _fernet()


def _hash_sid(sid: str) -> str:
    return hashlib.sha256(sid.encode()).hexdigest()


def _encrypt(token: str) -> str:
    return _FERNET.encrypt(token.encode()).decode()


def _decrypt(blob: str) -> str | None:
    try:
        return _FERNET.decrypt(blob.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def _prune(now: float | None = None) -> int:
    now = now or time.time()
    dead = [k for k, s in _SESSIONS.items() if float(s.get("expires") or 0) < now]
    for k in dead:
        _SESSIONS.pop(k, None)
    for st, exp in list(_OAUTH_STATES.items()):
        if exp < now:
            _OAUTH_STATES.pop(st, None)
    return len(dead)


def _load() -> None:
    global _SESSIONS, _dirty
    if not _STORE.exists():
        return
    try:
        raw = json.loads(_STORE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return
        now = time.time()
        cleaned: dict[str, dict[str, Any]] = {}
        for key, s in raw.items():
            if not isinstance(s, dict) or float(s.get("expires") or 0) < now:
                continue
            # Legacy format (plaintext sid + plaintext token): drop it — users log in again.
            if "access_token_enc" not in s:
                _dirty = True
                continue
            token = _decrypt(s["access_token_enc"])
            if token is None:  # SESSION_SECRET changed
                _dirty = True
                continue
            cleaned[key] = {**s, "access_token": token}
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
    _prune(now)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {}
        for key, s in _SESSIONS.items():
            payload[key] = {
                "user": s.get("user"),
                "access_token_enc": _encrypt(s.get("access_token") or ""),
                "created": s.get("created"),
                "expires": s.get("expires"),
                "guilds": s.get("guilds"),
                "guilds_fetched_at": s.get("guilds_fetched_at", 0),
            }
        tmp = _STORE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        tmp.replace(_STORE)
        _dirty = False
        _last_save = now
    except Exception as e:
        log.warning("Could not save sessions: %s", e)


_load()
if _dirty:
    _save(force=True)


# ---- OAuth state (CSRF protection for the login flow) ----

def new_oauth_state() -> str:
    _prune()
    state = secrets.token_urlsafe(24)
    _OAUTH_STATES[state] = time.time() + OAUTH_STATE_TTL
    return state


def consume_oauth_state(state: str | None, cookie_state: str | None) -> bool:
    """Valid only if it matches the browser's cookie, was issued by us, and is unused."""
    if not state or not cookie_state or not secrets.compare_digest(state, cookie_state):
        return False
    exp = _OAUTH_STATES.pop(state, None)
    return exp is not None and exp >= time.time()


# ---- Sessions ----

def create(user: dict[str, Any], access_token: str) -> str:
    global _dirty
    sid = secrets.token_urlsafe(32)
    _SESSIONS[_hash_sid(sid)] = {
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
    key = _hash_sid(sid)
    s = _SESSIONS.get(key)
    if not s:
        return None
    if time.time() > float(s.get("expires") or 0):
        _SESSIONS.pop(key, None)
        _dirty = True
        _save(force=True)
        return None
    return s


def destroy(sid: str | None) -> None:
    global _dirty
    if not sid:
        return
    if _SESSIONS.pop(_hash_sid(sid), None) is not None:
        _dirty = True
        _save(force=True)


def get_cached_guilds(sess: dict[str, Any], *, allow_stale: bool = False) -> list[dict[str, Any]] | None:
    guilds = sess.get("guilds")
    if guilds is None:
        return None
    age = time.time() - float(sess.get("guilds_fetched_at") or 0)
    if age < GUILDS_CACHE_TTL:
        return guilds
    # Stale fallback is capped so a revoked admin can't keep access indefinitely.
    if allow_stale and age < GUILDS_STALE_MAX:
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
