"""Groq chat completions with persona, model fallbacks, and friendly errors."""
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
    "Do not claim to be human. Do not invent moderation actions."
)

FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama-3.1-70b-versatile",
    "gemma2-9b-it",
    "mixtral-8x7b-32768",
]


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
    history: list[dict[str, str]] | None = None,
    consume_quota: bool = True,
) -> tuple[bool, str]:
    """Returns (ok, text). On limit/config errors, ok=False with friendly message."""
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

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    if history:
        messages.extend(history[-12:])
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
                    return True, text

            return False, last_err
    except Exception as e:
        log.exception("Groq request failed: %s", e)
        return False, "The AI service is temporarily unavailable. Try again in a moment."
