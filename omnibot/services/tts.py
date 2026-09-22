"""Character-aware TTS via edge-tts (free Microsoft Edge voices)."""
from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from omnibot import storage

log = logging.getLogger("omnibot.tts")

VOICE_RULES: list[tuple[list[str], str, str]] = [
    (["pikachu", "pokemon", "eevee", "kawaii", "anime girl", "waifu", "cute girl"], "en-US-AnaNeural", "cute/high"),
    (["light yagami", "yagami", "death note", "kira", "lelouch", "anime boy", "shonen"], "en-US-AndrewNeural", "young male"),
    (["goku", "naruto", "luffy", "energetic", "hyper"], "en-US-ChristopherNeural", "energetic male"),
    (["villain", "evil", "dark", "sinister", "demon"], "en-GB-RyanNeural", "deep/dark"),
    (["robot", "ai", "machine", "synthetic"], "en-US-JasonNeural", "robotic"),
    (["british", "butler", "formal", "posh"], "en-GB-SoniaNeural", "british"),
    (["child", "kid", "little"], "en-US-AnaNeural", "child"),
    (["woman", "female", "girl", "lady", "she/her"], "en-US-JennyNeural", "female"),
    (["man", "male", "guy", "he/him", "deep voice"], "en-US-GuyNeural", "male"),
    (["soft", "calm", "gentle", "whisper"], "en-US-AriaNeural", "soft"),
]

DEFAULT_VOICE = "en-US-JennyNeural"


def voice_for_persona(persona_text: str) -> tuple[str, str]:
    text = (persona_text or "").lower()
    for keys, voice, label in VOICE_RULES:
        for k in keys:
            if k in text:
                return voice, label
    return DEFAULT_VOICE, "default"


def voice_for_guild(guild_id: int | str) -> tuple[str, str]:
    data = storage.load_guild(guild_id)
    persona = (data.get("persona") or {}).get("instructions") or ""
    return voice_for_persona(str(persona))


async def synthesize(text: str, voice: str | None = None, guild_id: int | str | None = None) -> Path:
    try:
        import edge_tts
    except ImportError as e:
        raise RuntimeError("edge-tts is not installed. Add edge-tts to requirements.") from e

    text = (text or "").strip()
    if not text:
        raise ValueError("Empty text")
    text = text[:800]
    if not voice and guild_id is not None:
        voice, _ = voice_for_guild(guild_id)
    voice = voice or DEFAULT_VOICE

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(tmp_path))
    if not tmp_path.exists() or tmp_path.stat().st_size < 100:
        raise RuntimeError("TTS produced empty audio")
    return tmp_path


def clean_for_speech(text: str) -> str:
    t = text
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"`[^`]+`", " ", t)
    t = re.sub(r"\*+([^*]+)\*+", r"\1", t)
    t = re.sub(r"_+([^_]+)_+", r"\1", t)
    t = re.sub(r"~~([^~]+)~~", r"\1", t)
    t = re.sub(r"<@!?\d+>", " someone ", t)
    t = re.sub(r"<#[\d]+>", " a channel ", t)
    t = re.sub(r"https?://\S+", " link ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t
