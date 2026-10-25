from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data")))


def _bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _load_or_create_secret() -> str:
    """Use a random secret persisted in DATA_DIR when SESSION_SECRET isn't set."""
    import secrets as _secrets

    path = DATA_DIR / ".session_secret"
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
    except OSError:
        pass
    value = _secrets.token_urlsafe(48)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        os.chmod(path, 0o600)
    except OSError:
        pass  # in-memory only: sessions won't survive a restart
    return value


@dataclass
class Settings:
    discord_token: str = field(default_factory=lambda: os.getenv("DISCORD_TOKEN", "").strip())
    gamevox_bot_token: str = field(
        default_factory=lambda: (
            os.getenv("GAMEVOX_BOT_TOKEN") or os.getenv("GAMEVOX_TOKEN") or ""
        ).strip()
    )
    platform: str = field(
        default_factory=lambda: (os.getenv("PLATFORM") or os.getenv("BOT_PLATFORM") or "discord")
        .strip()
        .lower()
    )
    discord_client_id: str = field(default_factory=lambda: os.getenv("DISCORD_CLIENT_ID", "").strip())
    discord_client_secret: str = field(
        default_factory=lambda: os.getenv("DISCORD_CLIENT_SECRET", "").strip()
    )
    public_base_url: str = field(
        default_factory=lambda: os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:13893").rstrip("/")
    )
    discord_redirect_uri: str = field(default_factory=lambda: os.getenv("DISCORD_REDIRECT_URI", "").strip())
    port: int = field(default_factory=lambda: _int("PORT", _int("SERVER_PORT", 13893)))
    session_secret: str = field(default_factory=lambda: os.getenv("SESSION_SECRET", "").strip())
    groq_api_key: str = field(
        default_factory=lambda: (
            os.getenv("GROQ_API_KEY") or os.getenv("GROQ_KEY") or os.getenv("GROQ_TOKEN") or ""
        ).strip()
    )
    groq_model: str = field(
        default_factory=lambda: os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    )
    home_mode_api_url: str = field(default_factory=lambda: os.getenv("HOME_MODE_API_URL", "").rstrip("/"))
    home_mode_api_key: str = field(default_factory=lambda: os.getenv("HOME_MODE_API_KEY", "").strip())
    home_mode_api_path: str = field(
        default_factory=lambda: os.getenv("HOME_MODE_API_PATH", "/api/v1/generate")
    )
    tenor_api_key: str = field(default_factory=lambda: os.getenv("TENOR_API_KEY", "").strip())
    giphy_api_key: str = field(default_factory=lambda: os.getenv("GIPHY_API_KEY", "").strip())
    spotify_client_id: str = field(default_factory=lambda: os.getenv("SPOTIFY_CLIENT_ID", "").strip())
    spotify_client_secret: str = field(
        default_factory=lambda: os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    )
    spotify_market: str = field(default_factory=lambda: os.getenv("SPOTIFY_MARKET", "US").strip())
    soundcloud_client_id: str = field(
        default_factory=lambda: os.getenv("SOUNDCLOUD_CLIENT_ID", "").strip()
    )
    dashboard_origins: list[str] = field(default_factory=list)
    twitch_client_id: str = field(default_factory=lambda: os.getenv("TWITCH_CLIENT_ID", "").strip())
    twitch_client_secret: str = field(
        default_factory=lambda: os.getenv("TWITCH_CLIENT_SECRET", "").strip()
    )
    force_command_sync: bool = field(default_factory=lambda: _bool("FORCE_COMMAND_SYNC", False))
    ai_daily_limit: int = field(default_factory=lambda: _int("AI_DAILY_LIMIT", 20))
    ssl_key_path: str = field(default_factory=lambda: os.getenv("SSL_KEY_PATH", "").strip())
    ssl_cert_path: str = field(default_factory=lambda: os.getenv("SSL_CERT_PATH", "").strip())

    def __post_init__(self) -> None:
        raw = os.getenv("DASHBOARD_ORIGINS", "")
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if self.public_base_url and self.public_base_url not in origins:
            origins.append(self.public_base_url)
        origins.extend(["http://localhost:5173", "http://127.0.0.1:5173"])
        self.dashboard_origins = list(dict.fromkeys(origins))
        if not self.discord_redirect_uri:
            self.discord_redirect_uri = f"{self.public_base_url}/auth/discord/callback"
        if not self.session_secret or self.session_secret == "change-me-in-production-please":
            self.session_secret = _load_or_create_secret()
        # Normalise platform aliases
        p = self.platform
        if p in ("gamevox", "gv", "game-vox"):
            self.platform = "gamevox"
        else:
            self.platform = "discord"


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
