"""OmniBot entrypoint — Discord and/or GameVox + dashboard.

Platforms are isolated:
  PLATFORM=discord  — Discord only (default if only DISCORD_TOKEN is set)
  PLATFORM=gamevox  — GameVox only
  PLATFORM=both     — Discord in this process + GameVox in a child process
  PLATFORM=auto     — both if both tokens exist, else whichever token is set

GameVox runs in a separate OS process so gateway/intent failures there
cannot take Discord or the dashboard offline.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path


def _bootstrap_path() -> Path:
    """Ensure the project root (folder with omnibot/) is on sys.path and cwd."""
    here = Path(__file__).resolve().parent
    candidates = [
        here,
        Path.cwd(),
        *here.parents[:3],
        *Path.cwd().parents[:3],
    ]
    for base in (here, Path.cwd()):
        try:
            for child in base.iterdir():
                if child.is_dir():
                    candidates.append(child)
        except OSError:
            pass

    seen: set[Path] = set()
    for root in candidates:
        try:
            root = root.resolve()
        except OSError:
            continue
        if root in seen:
            continue
        seen.add(root)
        if (root / "omnibot" / "__init__.py").is_file() or (root / "omnibot" / "config.py").is_file():
            root_s = str(root)
            if root_s not in sys.path:
                sys.path.insert(0, root_s)
            try:
                os.chdir(root)
            except OSError:
                pass
            return root

    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    return Path.cwd()


_PROJECT_ROOT = _bootstrap_path()

import uvicorn

from omnibot import DEPLOY_MARKER
from omnibot.bot import OmniBot
from omnibot.config import settings
from omnibot.platform import PLATFORM_DISCORD, PLATFORM_GAMEVOX, configure_platform, resolve_bot_token
from omnibot.web.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("omnibot")

# Set by parent when spawning the GameVox worker — prevents nested spawn / second web server.
_ROLE = (os.getenv("OMNIBOT_ROLE") or "primary").strip().lower()


def _resolve_targets() -> tuple[bool, bool]:
    """Return (run_discord, run_gamevox) for this process."""
    if _ROLE in ("gamevox", "gamevox-worker", "gv-worker"):
        return False, True

    plat = settings.platform
    has_discord = bool(settings.discord_token)
    has_gamevox = bool(settings.gamevox_bot_token)

    if plat == "discord":
        return has_discord, False
    if plat == "gamevox":
        return False, has_gamevox
    if plat == "both":
        return has_discord, has_gamevox

    # auto
    if has_discord and has_gamevox:
        return True, True
    if has_gamevox and not has_discord:
        return False, True
    return has_discord, False


def _spawn_gamevox_worker() -> subprocess.Popen | None:
    """Start GameVox in a child process. Parent keeps Discord + dashboard."""
    env = os.environ.copy()
    env["OMNIBOT_ROLE"] = "gamevox-worker"
    env["PLATFORM"] = "gamevox"
    # Child must not try to bind the same PORT for the web dashboard.
    env["OMNIBOT_NO_WEB"] = "1"
    py = sys.executable
    script = str(Path(__file__).resolve())
    log.info("[Startup] launching GameVox worker subprocess (isolated from Discord)")
    try:
        proc = subprocess.Popen(
            [py, script],
            env=env,
            cwd=str(_PROJECT_ROOT),
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        return proc
    except Exception:
        log.exception("Failed to start GameVox worker — Discord will still run")
        return None


async def _watch_gamevox_worker(proc: subprocess.Popen) -> None:
    """Restart GameVox worker if it dies; never raises into the Discord task."""
    backoff = 5
    current = proc
    while True:
        try:
            code = await asyncio.to_thread(current.wait)
        except Exception:
            log.exception("GameVox worker wait failed")
            await asyncio.sleep(backoff)
            current = _spawn_gamevox_worker() or current
            continue
        log.warning(
            "GameVox worker exited with code %s — Discord stays up; restarting worker in %ss",
            code,
            backoff,
        )
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)
        nxt = _spawn_gamevox_worker()
        if nxt is not None:
            current = nxt
            backoff = 5


async def run() -> None:
    run_discord, run_gamevox = _resolve_targets()
    is_worker = _ROLE in ("gamevox", "gamevox-worker", "gv-worker")
    no_web = is_worker or os.getenv("OMNIBOT_NO_WEB", "").strip() in {"1", "true", "yes"}

    if not run_discord and not run_gamevox:
        log.error(
            "No bot token for the selected platform. Set DISCORD_TOKEN and/or GAMEVOX_BOT_TOKEN."
        )
        sys.exit(1)

    # Primary process: if both platforms requested, Discord stays here; GameVox is a child.
    gamevox_proc: subprocess.Popen | None = None
    if run_discord and run_gamevox and not is_worker:
        gamevox_proc = _spawn_gamevox_worker()
        run_gamevox = False  # this process only runs Discord (+ web)

    if run_gamevox and not run_discord:
        platform = configure_platform(PLATFORM_GAMEVOX)
    elif run_discord:
        platform = configure_platform(PLATFORM_DISCORD)
    else:
        platform = configure_platform(PLATFORM_GAMEVOX)

    token = resolve_bot_token(platform)
    if not token:
        if platform == PLATFORM_GAMEVOX:
            log.error("GAMEVOX_BOT_TOKEN is missing.")
        else:
            log.error("DISCORD_TOKEN is missing.")
        sys.exit(1)

    log.info(
        "[Startup] projectRoot=%s platform=%s role=%s web=%s",
        _PROJECT_ROOT,
        platform,
        _ROLE,
        "off" if no_web else "on",
    )

    bot = OmniBot()
    bot.platform = platform  # type: ignore[attr-defined]

    tasks: set[asyncio.Task] = set()

    async def start_bot() -> None:
        async with bot:
            await bot.start(token)

    tasks.add(asyncio.create_task(start_bot(), name=f"{platform}-bot"))

    if not no_web:
        app = create_app(bot=bot, deploy_marker=DEPLOY_MARKER)
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=settings.port,
            log_level="info",
            access_log=False,
            ssl_keyfile=settings.ssl_key_path or None,
            ssl_certfile=settings.ssl_cert_path or None,
        )
        server = uvicorn.Server(config)
        tasks.add(asyncio.create_task(server.serve(), name="web-api"))

    if gamevox_proc is not None:
        tasks.add(asyncio.create_task(_watch_gamevox_worker(gamevox_proc), name="gamevox-watch"))

    log.info("[Startup] deployMarker=%s", DEPLOY_MARKER)
    log.info("[Startup] PORT=%s PUBLIC_BASE_URL=%s", settings.port, settings.public_base_url)
    log.info(
        "[Startup] groq=%s model=%s",
        "ready" if settings.groq_api_key else "not-configured",
        settings.groq_model,
    )
    log.info("[Startup] image=%s", "ready" if settings.home_mode_api_url else "not-configured")

    # Wait until the *primary* bot or web dies. GameVox watcher never finishes on its own.
    # Prefer FIRST_COMPLETED on bot+web only so GameVox exit doesn't stop Discord.
    critical = {t for t in tasks if t.get_name() != "gamevox-watch"}
    done, pending = await asyncio.wait(critical, return_when=asyncio.FIRST_EXCEPTION)
    for t in pending:
        t.cancel()
    for t in list(tasks - critical):
        t.cancel()
    if gamevox_proc is not None and gamevox_proc.poll() is None:
        try:
            gamevox_proc.terminate()
        except Exception:
            pass
    for t in done:
        if t.exception():
            log.error("Task failed: %s", t.exception())
            raise t.exception()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Shutting down…")
