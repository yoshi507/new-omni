"""Per-guild JSON storage with soft-fail writes (ENOSPC safe)."""
from __future__ import annotations

import json
import logging
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from omnibot.config import DATA_DIR
from omnibot.settings_registry import get_defaults_nested

log = logging.getLogger("omnibot.storage")
_lock = threading.RLock()


def _guild_path(guild_id: int | str) -> Path:
    return DATA_DIR / "guilds" / f"{guild_id}.json"


def _default_guild() -> dict[str, Any]:
    return get_defaults_nested()


def load_guild(guild_id: int | str) -> dict[str, Any]:
    path = _guild_path(guild_id)
    with _lock:
        if not path.exists():
            data = _default_guild()
            _write_unlocked(path, data)
            return deepcopy(data)
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = _default_guild()
            # merge missing defaults shallowly at top keys
            base = _default_guild()
            for k, v in base.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception as e:
            log.warning("Failed to load guild %s: %s", guild_id, e)
            return _default_guild()


def save_guild(guild_id: int | str, data: dict[str, Any]) -> bool:
    path = _guild_path(guild_id)
    with _lock:
        return _write_unlocked(path, data)


def _write_unlocked(path: Path, data: dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
        return True
    except OSError as e:
        log.error("Disk write failed (%s): %s", getattr(e, "errno", "?"), e)
        return False


def update_guild(guild_id: int | str, mutator) -> dict[str, Any]:
    """mutator(data) -> None; saves and returns data."""
    with _lock:
        data = load_guild(guild_id)
        mutator(data)
        save_guild(guild_id, data)
        return data


def get_path(data: dict, dotted: str, default=None):
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def set_path(data: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    cur = data
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value
