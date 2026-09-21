"""Home Mode / PixelForge image generation (single job at a time)."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from omnibot.config import settings
from omnibot.services import ai_limits

log = logging.getLogger("omnibot.image")
_lock = asyncio.Lock()


def configured() -> bool:
    return bool(settings.home_mode_api_url)


async def generate(guild_id: int | str, prompt: str) -> tuple[bool, bytes | str]:
    if not configured():
        return False, "Image generation is not configured (set HOME_MODE_API_URL)."
    ok, msg = ai_limits.can_use(guild_id)
    if not ok:
        return False, msg or "AI limit reached."

    async with _lock:
        url = settings.home_mode_api_url.rstrip("/") + settings.home_mode_api_path
        headers = {"Content-Type": "application/json"}
        if settings.home_mode_api_key:
            headers["Authorization"] = f"Bearer {settings.home_mode_api_key}"
            headers["X-API-Key"] = settings.home_mode_api_key
        payload = {"prompt": prompt, "width": 512, "height": 512}
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(url, headers=headers, json=payload)
            if r.status_code >= 400:
                log.error("Image API %s: %s", r.status_code, r.text[:400])
                return False, f"Image API error ({r.status_code}). Check HOME_MODE_API_URL/KEY."
            ct = r.headers.get("content-type", "")
            if "image" in ct:
                ai_limits.consume(guild_id)
                return True, r.content
            # JSON with url
            try:
                data = r.json()
                img_url = data.get("url") or data.get("image_url") or data.get("result")
                if isinstance(img_url, str) and img_url.startswith("http"):
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        ir = await client.get(img_url)
                    if ir.status_code == 200:
                        ai_limits.consume(guild_id)
                        return True, ir.content
            except Exception:
                pass
            return False, "Image API returned an unexpected response."
        except httpx.RequestError as e:
            log.error("Image API unreachable: %s", e)
            return False, "Could not reach the Home Mode image API. Check HOME_MODE_API_URL."
