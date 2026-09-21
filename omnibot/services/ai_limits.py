"""Centralized 20 AI requests per guild per day."""
from __future__ import annotations

from datetime import date

from omnibot.config import settings
from omnibot import storage


def _today() -> str:
    return date.today().isoformat()


def usage(guild_id: int | str) -> dict:
    data = storage.load_guild(guild_id)
    u = data.get("aiUsage") or {}
    if u.get("date") != _today():
        return {"date": _today(), "count": 0, "limit": settings.ai_daily_limit}
    return {
        "date": u.get("date"),
        "count": int(u.get("count") or 0),
        "limit": settings.ai_daily_limit,
    }


def can_use(guild_id: int | str) -> tuple[bool, str | None]:
    u = usage(guild_id)
    if u["count"] >= u["limit"]:
        return False, (
            f"This server has reached its daily AI allowance ({u['limit']} requests). "
            f"It resets at midnight UTC. Try again tomorrow!"
        )
    return True, None


def consume(guild_id: int | str) -> dict:
    def mut(data):
        u = data.setdefault("aiUsage", {})
        if u.get("date") != _today():
            u["date"] = _today()
            u["count"] = 0
        u["count"] = int(u.get("count") or 0) + 1

    storage.update_guild(guild_id, mut)
    return usage(guild_id)


def friendly_limit_message(guild_id: int | str) -> str:
    ok, msg = can_use(guild_id)
    if ok:
        u = usage(guild_id)
        return f"AI usage: {u['count']}/{u['limit']} today."
    return msg or "AI limit reached."
