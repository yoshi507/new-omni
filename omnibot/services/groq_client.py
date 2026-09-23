"""Groq chat completions with persona, per-user memory, and model fallbacks."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from omnibot.config import settings
from omnibot import storage
from omnibot.services import ai_limits, concurrency

log = logging.getLogger("omnibot.groq")

DEFAULT_SYSTEM = (
    "You are OmniBot, a helpful Discord community assistant. "
    "Be clear, friendly, and concise. Use Discord-friendly formatting. "
    "Do not claim to be human. Do not invent moderation actions. "
    "If conversation history is provided, continue naturally from it — "
    "do not re-introduce yourself or say hello every time unless the user greets you first."
)

FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama-3.1-70b-versatile",
    "gemma2-9b-it",
    "mixtral-8x7b-32768",
]

MAX_HISTORY = 12


def _persona_system(guild_id: int | str | None) -> str:
    base = DEFAULT_SYSTEM
    if not guild_id:
        return base
    data = storage.load_guild(guild_id)
    dash = data.get("dashboard") or {}
    ai_cfg = dash.get("ai") or {}
    if ai_cfg.get("enabled") is False:
        return "__AI_DISABLED__"
    custom = (data.get("persona") or {}).get("instructions") or ""
    custom = str(custom).strip()
    if not custom:
        return base
    return (
        f"{base}\n\n"
        f"SERVER PERSONALITY INSTRUCTIONS (follow these closely; do not be apologetic "
        f"unless the user asks or the instructions require it):\n{custom}"
    )


def _memory_enabled(guild_id: int | str | None) -> bool:
    if guild_id is None:
        return False
    data = storage.load_guild(guild_id)
    dash = data.get("dashboard") or {}
    ai_cfg = dash.get("ai") or {}
    return bool(ai_cfg.get("memoryEnabled", True))


def load_history(guild_id: int | str, user_id: int | str) -> list[dict[str, str]]:
    """Load recent chat turns for this user in this guild."""
    if not _memory_enabled(guild_id):
        return []
    data = storage.load_guild(guild_id)
    mem = (data.get("memory") or {}).get(str(user_id)) or []
    if not isinstance(mem, list):
        return []
    out: list[dict[str, str]] = []
    for m in mem[-MAX_HISTORY:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and content:
            out.append({"role": str(role), "content": str(content)[:4000]})
    return out


def save_turn(guild_id: int | str, user_id: int | str, user_msg: str, assistant_msg: str) -> None:
    """Append a user+assistant turn to memory (if enabled)."""
    if not _memory_enabled(guild_id):
        return
    uid = str(user_id)

    def mut(d: dict) -> None:
        root = d.setdefault("memory", {})
        hist = list(root.get(uid) or [])
        if not isinstance(hist, list):
            hist = []
        hist.append({"role": "user", "content": str(user_msg)[:4000]})
        hist.append({"role": "assistant", "content": str(assistant_msg)[:4000]})
        root[uid] = hist[-MAX_HISTORY:]

    storage.update_guild(guild_id, mut)


def clear_memory(guild_id: int | str, user_id: int | str) -> None:
    def mut(d: dict) -> None:
        (d.get("memory") or {}).pop(str(user_id), None)

    storage.update_guild(guild_id, mut)


def _models_to_try() -> list[str]:
    primary = (settings.groq_model or "").strip()
    out: list[str] = []
    if primary:
        out.append(primary)
    for m in FALLBACK_MODELS:
        if m not in out:
            out.append(m)
    return out


async def chat(
    guild_id: int | str | None,
    user_message: str,
    *,
    user_id: int | str | None = None,
    history: list[dict[str, str]] | None = None,
    consume_quota: bool = True,
    remember: bool = True,
) -> tuple[bool, str]:
    """Returns (ok, text). Loads/saves per-user memory when user_id is set and remember=True."""
    key = (settings.groq_api_key or "").strip().strip('"').strip("'")
    if not key:
        return False, (
            "AI is not configured. Set **GROQ_API_KEY** on the server and restart OmniBot."
        )

    system = _persona_system(guild_id)
    if system == "__AI_DISABLED__":
        return False, "AI is disabled for this server in the dashboard."

    if guild_id is not None and consume_quota:
        ok, msg = ai_limits.can_use(guild_id)
        if not ok:
            return False, msg or "AI limit reached."

    hist: list[dict[str, str]] = list(history) if history is not None else []
    if history is None and guild_id is not None and user_id is not None and remember:
        hist = load_history(guild_id, user_id)

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    if hist:
        messages.extend(hist[-MAX_HISTORY:])
    messages.append({"role": "user", "content": user_message[:8000]})

    last_err = "Something went wrong with AI. Please try again."

    try:
        async with concurrency.guild_slot(guild_id):
            async with httpx.AsyncClient(timeout=90.0) as client:
                for model in _models_to_try():
                    try:
                        r = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": model,
                                "messages": messages,
                                "temperature": 0.7,
                                "max_tokens": 1024,
                            },
                        )
                    except httpx.TimeoutException:
                        last_err = "The AI service timed out. Try again in a moment."
                        continue
                    except httpx.RequestError as e:
                        log.error("Groq network error: %s", e)
                        last_err = "Could not reach Groq. Check the server network connection."
                        continue

                    if r.status_code == 401:
                        log.error("Groq 401 — invalid API key")
                        return False, (
                            "AI authentication failed. Check that **GROQ_API_KEY** is valid "
                            "in the server environment and restart."
                        )
                    if r.status_code == 429:
                        return False, (
                            "Sorry — the global AI provider limit was reached. "
                            "Wait a minute and try again."
                        )
                    if r.status_code >= 400:
                        body = r.text[:400]
                        log.error("Groq error model=%s status=%s body=%s", model, r.status_code, body)
                        if r.status_code in (400, 404) and (
                            "model" in body.lower() or "not found" in body.lower()
                        ):
                            last_err = (
                                f"Model `{model}` unavailable; trying fallback…"
                                if model != _models_to_try()[-1]
                                else (
                                    "No working Groq model found. Set **GROQ_MODEL** to a "
                                    "supported model (e.g. llama-3.1-8b-instant)."
                                )
                            )
                            continue
                        last_err = "Something went wrong with AI. Please try again."
                        continue

                    data: dict[str, Any] = r.json()
                    text = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        or ""
                    ).strip()
                    if not text:
                        last_err = "AI returned an empty response. Try again."
                        continue

                    if guild_id is not None and consume_quota:
                        ai_limits.consume(guild_id)
                    if model != (settings.groq_model or "").strip():
                        log.info("Groq succeeded with fallback model=%s", model)

                    if remember and guild_id is not None and user_id is not None:
                        try:
                            save_turn(guild_id, user_id, user_message, text)
                        except Exception as e:
                            log.warning("Failed to save AI memory: %s", e)

                    return True, text

            return False, last_err
    except Exception as e:
        log.exception("Groq request failed: %s", e)
        return False, "The AI service is temporarily unavailable. Try again in a moment."
