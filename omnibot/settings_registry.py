"""Dashboard settings definitions (parity with Node settingsRegistry)."""
from __future__ import annotations

from typing import Any

SETTINGS: list[dict[str, Any]] = [
    {"id": "ai.enabled", "type": "boolean", "default": True, "path": "dashboard.ai.enabled"},
    {"id": "ai.memoryEnabled", "type": "boolean", "default": True, "path": "dashboard.ai.memoryEnabled"},
    {"id": "ai.memoryMaxMessages", "type": "number", "default": 12, "min": 2, "max": 40, "path": "dashboard.ai.memoryMaxMessages"},
    {"id": "ai.naturalInvocation", "type": "boolean", "default": True, "path": "dashboard.ai.naturalInvocation"},
    {"id": "ai.commandPrefix", "type": "string", "default": "!", "maxLength": 5, "path": "commandSettings.prefix"},
    {"id": "ai.personality", "type": "string", "default": "", "maxLength": 4000, "path": "persona.instructions"},
    {"id": "security.enabled", "type": "boolean", "default": False, "path": "security.enabled"},
    {"id": "security.mode", "type": "select", "default": "monitor", "options": ["monitor", "alert", "lockdown"], "path": "security.mode"},
    {"id": "security.autoTimeoutExecutor", "type": "boolean", "default": False, "path": "security.antiNuke.autoTimeoutExecutor"},
    {"id": "security.autoTimeoutMinutes", "type": "number", "default": 10, "min": 1, "max": 60, "path": "security.antiNuke.autoTimeoutMinutes"},
    {"id": "security.thresholdChannelDelete", "type": "number", "default": 3, "min": 1, "max": 20, "path": "security.antiNuke.thresholds.channelDelete"},
    {"id": "security.thresholdRoleDelete", "type": "number", "default": 3, "min": 1, "max": 20, "path": "security.antiNuke.thresholds.roleDelete"},
    {"id": "security.windowSeconds", "type": "number", "default": 30, "min": 5, "max": 300, "path": "security.antiNuke.windowMs"},
    {"id": "moderation.automodEnabled", "type": "boolean", "default": False, "path": "automod.enabled"},
    {"id": "moderation.blockedWords", "type": "string", "default": "", "maxLength": 2000, "path": "automod.blockedWords"},
    {"id": "moderation.modLogChannel", "type": "channel", "default": None, "path": "settings.modLogChannel"},
    {"id": "moderation.antiSpamEnabled", "type": "boolean", "default": True, "path": "spamConfig.enabled"},
    {"id": "leveling.enabled", "type": "boolean", "default": True, "path": "levelSettings.enabled"},
    {"id": "leveling.xpMin", "type": "number", "default": 15, "min": 1, "max": 100, "path": "levelSettings.xpMin"},
    {"id": "leveling.xpMax", "type": "number", "default": 25, "min": 1, "max": 200, "path": "levelSettings.xpMax"},
    {"id": "leveling.cooldownSeconds", "type": "number", "default": 60, "min": 0, "max": 600, "path": "levelSettings.cooldown"},
    {"id": "leveling.announceLevelUp", "type": "boolean", "default": True, "path": "levelSettings.announce"},
    {"id": "welcome.enabled", "type": "boolean", "default": False, "path": "welcomeSettings.enabled"},
    {"id": "welcome.channel", "type": "channel", "default": None, "path": "welcomeSettings.channelId"},
    {"id": "welcome.message", "type": "string", "default": "Welcome {user} to {server}!", "maxLength": 1500, "path": "welcomeSettings.message"},
    {"id": "goodbye.enabled", "type": "boolean", "default": False, "path": "goodbyeSettings.enabled"},
    {"id": "goodbye.channel", "type": "channel", "default": None, "path": "goodbyeSettings.channelId"},
    {"id": "goodbye.message", "type": "string", "default": "{username} left {server}.", "maxLength": 1500, "path": "goodbyeSettings.message"},
    {"id": "autorole.enabled", "type": "boolean", "default": False, "path": "autorole.enabled"},
    {"id": "autorole.role", "type": "role", "default": None, "path": "autorole.roleId"},
    {"id": "logging.enabled", "type": "boolean", "default": False, "path": "logging.enabled"},
    {"id": "logging.channel", "type": "channel", "default": None, "path": "logging.channelId"},
    {"id": "tickets.enabled", "type": "boolean", "default": False, "path": "ticketSettings.enabled"},
    {"id": "tickets.panelChannel", "type": "channel", "default": None, "path": "ticketSettings.panelChannelId"},
    {"id": "music.enabled", "type": "boolean", "default": True, "path": "music.enabled"},
    {"id": "music.defaultVolume", "type": "number", "default": 80, "min": 0, "max": 100, "path": "music.defaultVolume"},
    {"id": "deadchat.enabled", "type": "boolean", "default": False, "path": "deadChat.enabled"},
    {"id": "deadchat.minutes", "type": "number", "default": 30, "min": 5, "max": 1440, "path": "deadChat.minutes"},
    {"id": "deadchat.channel", "type": "channel", "default": None, "path": "deadChat.channelId"},
    {"id": "appeals.enabled", "type": "boolean", "default": False, "path": "appeals.enabled"},
    {"id": "appeals.channel", "type": "channel", "default": None, "path": "appeals.channelId"},
    {"id": "appeals.cooldownHours", "type": "number", "default": 72, "min": 1, "max": 720, "path": "appeals.cooldownHours"},
    {"id": "appeals.acceptMessage", "type": "string", "default": "Your appeal has been accepted.", "maxLength": 1500, "path": "appeals.acceptMessage"},
    {"id": "appeals.rejectMessage", "type": "string", "default": "Your appeal has been rejected.", "maxLength": 1500, "path": "appeals.rejectMessage"},
    {"id": "quiz.enabled", "type": "boolean", "default": True, "path": "quiz.enabled"},
    {"id": "quiz.questionCount", "type": "number", "default": 5, "min": 1, "max": 20, "path": "quiz.questionCount"},
    {"id": "quiz.timeLimitSeconds", "type": "number", "default": 20, "min": 5, "max": 120, "path": "quiz.timeLimitSeconds"},
]


def get_setting_by_id(sid: str) -> dict | None:
    return next((s for s in SETTINGS if s["id"] == sid), None)


def get_defaults_flat() -> dict[str, Any]:
    return {s["id"]: s["default"] for s in SETTINGS}


def get_defaults_nested() -> dict[str, Any]:
    """Build nested dict matching path structure."""
    root: dict[str, Any] = {
        "economy": {},
        "warnings": {},
        "levels": {},
        "appealsRecords": {},
        "giveaways": {},
        "reactionRoles": {},
        "aiUsage": {"date": "", "count": 0},
        "memory": {},
        "persona": {"instructions": ""},
        "security": {"enabled": False, "mode": "monitor", "antiNuke": {"thresholds": {}, "autoTimeoutExecutor": False, "autoTimeoutMinutes": 10, "windowMs": 30}},
        "automod": {"enabled": False, "blockedWords": ""},
        "spamConfig": {"enabled": True},
        "levelSettings": {"enabled": True, "xpMin": 15, "xpMax": 25, "cooldown": 60, "announce": True},
        "welcomeSettings": {"enabled": False, "channelId": None, "message": "Welcome {user} to {server}!"},
        "goodbyeSettings": {"enabled": False, "channelId": None, "message": "{username} left {server}."},
        "autorole": {"enabled": False, "roleId": None},
        "logging": {"enabled": False, "channelId": None},
        "ticketSettings": {"enabled": False, "panelChannelId": None, "staffRoleIds": []},
        "music": {"enabled": True, "defaultVolume": 80},
        "deadChat": {"enabled": False, "minutes": 30, "channelId": None, "lastMessageAt": {}},
        "appeals": {"enabled": False, "channelId": None, "staffRoleIds": [], "cooldownHours": 72,
                    "acceptMessage": "Your appeal has been accepted.",
                    "rejectMessage": "Your appeal has been rejected.",
                    "pendingMessage": "Your appeal was submitted and is awaiting review."},
        "quiz": {"enabled": True, "channelId": None, "questionCount": 5, "timeLimitSeconds": 20,
                 "pointsCorrect": 10, "streakBonus": 2, "cooldownSeconds": 30},
        "commandSettings": {"prefix": "!"},
        "dashboard": {"ai": {"enabled": True, "memoryEnabled": True, "memoryMaxMessages": 12, "naturalInvocation": True}},
        "settings": {"modLogChannel": None, "suggestionsChannel": None},
        "partner": {},
        "advertise": {},
        "captcha": {"enabled": False},
        "automations": [],
        "swearJar": {"enabled": False, "words": [], "fine": 50},
    }
    return root


def validate_setting(defn: dict, value: Any) -> tuple[bool, Any, str | None]:
    if defn is None:
        return False, None, "Unknown setting"
    t = defn["type"]
    if value is None and t in ("channel", "role"):
        return True, None, None
    if t == "boolean":
        if not isinstance(value, bool):
            return False, None, "Must be boolean"
        return True, value, None
    if t == "number":
        try:
            n = float(value)
        except (TypeError, ValueError):
            return False, None, "Must be a number"
        if defn.get("min") is not None and n < defn["min"]:
            return False, None, f"Min {defn['min']}"
        if defn.get("max") is not None and n > defn["max"]:
            return False, None, f"Max {defn['max']}"
        return True, n, None
    if t == "string":
        if not isinstance(value, str):
            return False, None, "Must be a string"
        if defn.get("maxLength") and len(value) > defn["maxLength"]:
            return False, None, f"Max length {defn['maxLength']}"
        return True, value, None
    if t == "select":
        if value not in defn.get("options", []):
            return False, None, "Invalid option"
        return True, value, None
    if t in ("channel", "role"):
        if value in (None, ""):
            return True, None, None
        if not isinstance(value, str) or not value.isdigit() or not (16 <= len(value) <= 20):
            return False, None, "Invalid Discord snowflake"
        return True, value, None
    if t == "multiselect":
        if not isinstance(value, list):
            return False, None, "Must be an array"
        return True, list(dict.fromkeys(value)), None
    return False, None, "Unsupported type"
