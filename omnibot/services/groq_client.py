"""Groq chat completions with persona + friendly errors."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from omnibot.config import settings
from omnibot import storage
from omnibot.services import ai_limits

log = logging.getLogger("omnibot.groq")

DEFAULT_SYSTEM = (
    "You are OmniBot, a helpful Discord community assistant. "
    "Be clear, friendly, and concise. Use Discord-friendly formatting. "
    "Do not claim to be human. Do not invent moderation actions."
)


def _persona_system(guild_id: int | str | None) -> str:
    base = DEFAULT_SYSTEM
    if not guild_id:
        return base
    data = storage.load_guild(guild_id)
    custom = (data.get("persona") or {}).get("instructions") or ""
    custom = str(custom).strip()
    if not custom:
        return base
    # Custom personalities: do not force apologies unless asked
    return (
        f"{base}\n\n"
        f"SERVER PERSONALITY INSTRUCTIONS (follow these closely; do not be apologetic "
        f"unless the user asks or the instructions require it):\n{custom}"
    )


async def chat(
    guild_id: int | str | None,
    user_message: str,
    *,
    history: list[dict[str, str]] | None = None,
    consume_quota: bool = True,
) -> tuple[bool, str]:
    """Returns (ok, text). On limit/config errors, ok=False with friendly message."""
    if not settings.groq_api_key:
        return False, "AI is not configured on this server (missing GROQ_API_KEY)."

    if guild_id is not None and consume_quota:
        ok, msg = ai_limits.can_use(guild_id)
        if not ok:
            return False, msg or "AI limit reached."

    messages: list[dict[str, str]] = [{"role": "system", "content": _persona_system(guild_id)}]
    if history:
        messages.extend(history[-12:])
    messages.append({"role": "user", "content": user_message})

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.groq_model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 1024,
                },
            )
        if r.status_code == 401:
            return False, "AI authentication failed. The server admin needs to check GROQ_API_KEY."
        if r.status_code == 429:
            return False, "Sorry — the global AI provider limit was reached. Try again in a bit."
        if r.status_code >= 400:
            body = r.text[:300]
            log.error("Groq error status=%s body=%s", r.status_code, body)
            if r.status_code == 400 and "model" in body.lower():
                return False, (
                    "The configured AI model is unavailable. "
                    "Try again later or set GROQ_MODEL to a supported Groq model."
                )
            return False, "Something went wrong with AI. Please try again."
        data: dict[str, Any] = r.json()
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not text:
            return False, "AI returned an empty response. Try again."
        if guild_id is not None and consume_quota:
            ai_limits.consume(guild_id)
        return True, text
    except httpx.TimeoutException:
        return False, "The AI service timed out. Try again in a moment."
    except Exception as e:
        log.exception("Groq request failed: %s", e)
        return False, "The AI service is temporarily unavailable. Try again in a moment."
