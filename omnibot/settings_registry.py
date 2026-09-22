"""Dashboard settings definitions — expanded feature universe."""
from __future__ import annotations

from typing import Any

SETTINGS: list[dict[str, Any]] = [
    # AI
    {"id": "ai.enabled", "path": "dashboard.ai.enabled", "type": "bool", "default": True, "category": "ai"},
    {"id": "ai.naturalInvocation", "path": "dashboard.ai.naturalInvocation", "type": "bool", "default": True, "category": "ai"},
    {"id": "ai.memoryEnabled", "path": "dashboard.ai.memoryEnabled", "type": "bool", "default": True, "category": "ai"},
    {"id": "ai.commandPrefix", "path": "commandSettings.prefix", "type": "text", "default": "!", "category": "ai"},
    {"id": "ai.personality", "path": "persona.instructions", "type": "textarea", "default": "", "category": "ai"},
    # Moderation
    {"id": "moderation.automodEnabled", "path": "automod.enabled", "type": "bool", "default": False, "category": "moderation"},
    {"id": "moderation.antiSpamEnabled", "path": "spamConfig.enabled", "type": "bool", "default": True, "category": "moderation"},
    {"id": "moderation.blockedWords", "path": "automod.blockedWords", "type": "textarea", "default": "", "category": "moderation"},
    {"id": "security.enabled", "path": "security.enabled", "type": "bool", "default": True, "category": "moderation"},
    {"id": "security.mode", "path": "security.mode", "type": "select", "default": "monitor", "options": ["monitor", "alert", "lockdown"], "category": "moderation"},
    {"id": "honeypot.enabled", "path": "honeypot.enabled", "type": "bool", "default": False, "category": "moderation"},
    # Engagement
    {"id": "welcome.enabled", "path": "welcomeSettings.enabled", "type": "bool", "default": False, "category": "engagement"},
    {"id": "welcome.message", "path": "welcomeSettings.message", "type": "textarea", "default": "Welcome {user}!", "category": "engagement"},
    {"id": "goodbye.enabled", "path": "goodbyeSettings.enabled", "type": "bool", "default": False, "category": "engagement"},
    {"id": "deadchat.enabled", "path": "deadChat.enabled", "type": "bool", "default": False, "category": "engagement"},
    {"id": "deadchat.minutes", "path": "deadChat.minutes", "type": "number", "default": 60, "category": "engagement"},
    {"id": "leveling.enabled", "path": "levelSettings.enabled", "type": "bool", "default": True, "category": "engagement"},
    {"id": "autorole.enabled", "path": "autorole.enabled", "type": "bool", "default": False, "category": "engagement"},
    {"id": "suggestions.enabled", "path": "suggestions.enabled", "type": "bool", "default": True, "category": "engagement"},
    {"id": "starboard.enabled", "path": "starboard.enabled", "type": "bool", "default": False, "category": "engagement"},
    {"id": "stickyRoles.enabled", "path": "stickyRoles.enabled", "type": "bool", "default": False, "category": "engagement"},
    {"id": "counting.enabled", "path": "counting.enabled", "type": "bool", "default": False, "category": "engagement"},
    {"id": "wordchain.enabled", "path": "wordchain.enabled", "type": "bool", "default": False, "category": "engagement"},
    {"id": "verification.enabled", "path": "verification.enabled", "type": "bool", "default": False, "category": "engagement"},
    {"id": "booster.enabled", "path": "booster.enabled", "type": "bool", "default": False, "category": "engagement"},
    # Appeals
    {"id": "appeals.enabled", "path": "appeals.enabled", "type": "bool", "default": False, "category": "appeals"},
    {"id": "appeals.cooldownHours", "path": "appeals.cooldownHours", "type": "number", "default": 24, "category": "appeals"},
    {"id": "appeals.acceptMessage", "path": "appeals.acceptMessage", "type": "textarea", "default": "Your appeal was accepted.", "category": "appeals"},
    {"id": "appeals.rejectMessage", "path": "appeals.rejectMessage", "type": "textarea", "default": "Your appeal was rejected.", "category": "appeals"},
    # Music
    {"id": "music.enabled", "path": "music.enabled", "type": "bool", "default": True, "category": "music"},
    {"id": "music.defaultVolume", "path": "music.defaultVolume", "type": "number", "default": 80, "category": "music"},
    # Logging
    {"id": "logging.enabled", "path": "logging.enabled", "type": "bool", "default": True, "category": "logging"},
    {"id": "logging.voice", "path": "logging.voice", "type": "bool", "default": False, "category": "logging"},
    # Tickets
    {"id": "tickets.enabled", "path": "tickets.enabled", "type": "bool", "default": False, "category": "tickets"},
    # Economy
    {"id": "economy.enabled", "path": "economy.enabled", "type": "bool", "default": True, "category": "fun"},
    # Temp voice
    {"id": "tempVoice.enabled", "path": "tempVoice.enabled", "type": "bool", "default": False, "category": "voice"},
]


def get_setting_by_id(sid: str) -> dict[str, Any] | None:
    for s in SETTINGS:
        if s["id"] == sid:
            return s
    return None


def validate_setting(defn: dict[str, Any], val: Any) -> tuple[bool, Any, str | None]:
    t = defn.get("type")
    if t == "bool":
        if isinstance(val, bool):
            return True, val, None
        if str(val).lower() in {"1", "true", "yes", "on"}:
            return True, True, None
        if str(val).lower() in {"0", "false", "no", "off"}:
            return True, False, None
        return False, None, "Expected boolean"
    if t == "number":
        try:
            return True, float(val) if "." in str(val) else int(val), None
        except (TypeError, ValueError):
            return False, None, "Expected number"
    if t == "select":
        opts = defn.get("options") or []
        if val not in opts:
            return False, None, f"Must be one of {opts}"
        return True, val, None
    if t in {"text", "textarea"}:
        return True, str(val) if val is not None else "", None
    return True, val, None


def get_defaults_flat() -> dict[str, Any]:
    return {s["id"]: s["default"] for s in SETTINGS}


def get_defaults_nested() -> dict[str, Any]:
    """Build nested default guild data from SETTINGS paths."""
    root: dict[str, Any] = {}
    for s in SETTINGS:
        parts = s["path"].split(".")
        cur = root
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = s["default"]
    root.setdefault("levels", {})
    root.setdefault("invites", {})
    root.setdefault("starboardPosts", {})
    root.setdefault("triggers", {})
    root.setdefault("customCommands", {})
    root.setdefault("birthdays", {})
    root.setdefault("stickyRoles", {"enabled": False, "saved": {}})
    root.setdefault("verification", {"enabled": False})
    root.setdefault("honeypot", {"enabled": False})
    root.setdefault("booster", {"enabled": False})
    root.setdefault("counting", {"enabled": False, "next": 1})
    root.setdefault("wordchain", {"enabled": False})
    root.setdefault("starboard", {"enabled": False})
    return root
