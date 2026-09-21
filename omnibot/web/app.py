"""FastAPI application: health, OAuth, settings, static dashboard."""
from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from omnibot.config import settings, DATA_DIR
from omnibot import storage
from omnibot.settings_registry import SETTINGS, get_setting_by_id, validate_setting, get_defaults_flat
from omnibot.web import sessions, oauth
from omnibot.services import ai_limits

log = logging.getLogger("omnibot.web")

PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent / "public" / "dashboard"
COOKIE = "omnibot_session"


class SettingsPatch(BaseModel):
    patch: dict[str, Any]


class AppealSubmit(BaseModel):
    guild_id: str
    punishment_type: str = "ban"  # ban | timeout | warn
    reason: str
    extra: str = ""


def create_app(bot, deploy_marker: str) -> FastAPI:
    app = FastAPI(title="OmniBot API", docs_url=None, redoc_url=None)
    app.state.bot = bot
    app.state.deploy_marker = deploy_marker

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.dashboard_origins + ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def session_user(request: Request) -> dict | None:
        sid = request.cookies.get(COOKIE)
        s = sessions.get(sid)
        return s["user"] if s else None

    def require_user(request: Request) -> tuple[dict, dict]:
        sid = request.cookies.get(COOKIE)
        s = sessions.get(sid)
        if not s:
            raise HTTPException(401, "Not authenticated")
        return s["user"], s

    @app.get("/health")
    async def health():
        b = app.state.bot
        return {
            "ok": True,
            "service": "OmniBot API",
            "discordReady": bool(b and b.is_ready()),
            "guilds": len(b.guilds) if b and b.is_ready() else 0,
            "uptime": None,
        }

    @app.get("/version")
    async def version():
        b = app.state.bot
        return {
            "ok": True,
            "deployMarker": deploy_marker,
            "service": "OmniBot Python",
            "discordReady": bool(b and b.is_ready()),
            "guilds": len(b.guilds) if b and b.is_ready() else 0,
            "groqConfigured": bool(settings.groq_api_key),
            "imageConfigured": bool(settings.home_mode_api_url),
            "dashboardUrl": settings.public_base_url,
        }

    @app.get("/auth/login")
    async def auth_login():
        if not settings.discord_client_id or not settings.discord_client_secret:
            raise HTTPException(503, "OAuth not configured (DISCORD_CLIENT_ID/SECRET)")
        state = secrets.token_urlsafe(16)
        url = (
            f"https://discord.com/api/oauth2/authorize"
            f"?client_id={settings.discord_client_id}"
            f"&redirect_uri={settings.discord_redirect_uri}"
            f"&response_type=code&scope=identify%20guilds&state={state}"
        )
        return RedirectResponse(url)

    @app.get("/auth/discord/callback")
    async def auth_callback(request: Request, code: str | None = None, error: str | None = None):
        if error or not code:
            return RedirectResponse("/#/login?error=oauth")
        try:
            token = await oauth.exchange_code(code)
            access = token["access_token"]
            user = await oauth.fetch_user(access)
            sid = sessions.create(user, access)
            resp = RedirectResponse("/#/servers")
            resp.set_cookie(COOKIE, sid, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7)
            return resp
        except Exception as e:
            log.error("OAuth callback failed: %s", e)
            return RedirectResponse("/#/login?error=callback")

    @app.get("/auth/me")
    async def auth_me(request: Request):
        user = session_user(request)
        if not user:
            raise HTTPException(401, "Not authenticated")
        return {"user": user}

    @app.post("/auth/logout")
    async def auth_logout(request: Request):
        sessions.destroy(request.cookies.get(COOKIE))
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE)
        return resp

    @app.get("/guilds")
    async def list_guilds(request: Request):
        user, sess = require_user(request)
        try:
            raw = await oauth.fetch_user_guilds(sess["access_token"])
        except Exception:
            raise HTTPException(502, "Failed to fetch Discord guilds")
        bot = app.state.bot
        bot_ids = {str(g.id) for g in bot.guilds} if bot and bot.is_ready() else set()
        out = []
        for g in raw:
            if not oauth.can_manage(g):
                continue
            gid = str(g["id"])
            if gid not in bot_ids:
                continue
            icon = g.get("icon")
            icon_url = (
                f"https://cdn.discordapp.com/icons/{gid}/{icon}.png" if icon else None
            )
            out.append({"id": gid, "name": g.get("name"), "icon": icon_url})
        return {"guilds": out}

    @app.get("/guilds/{guild_id}/settings")
    async def get_settings(guild_id: str, request: Request):
        await _assert_guild_access(request, guild_id)
        data = storage.load_guild(guild_id)
        flat = {}
        for s in SETTINGS:
            flat[s["id"]] = storage.get_path(data, s["path"], s["default"])
        return {"settings": flat, "defaults": get_defaults_flat()}

    @app.put("/guilds/{guild_id}/settings")
    async def put_settings(guild_id: str, body: SettingsPatch, request: Request):
        await _assert_guild_access(request, guild_id)

        def mut(data):
            for sid, val in (body.patch or {}).items():
                defn = get_setting_by_id(sid)
                if not defn:
                    continue
                ok, cleaned, err = validate_setting(defn, val)
                if not ok:
                    raise HTTPException(400, f"{sid}: {err}")
                storage.set_path(data, defn["path"], cleaned)

        try:
            storage.update_guild(guild_id, mut)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))
        return {"ok": True}

    @app.get("/guilds/{guild_id}/bot")
    async def guild_bot(guild_id: str, request: Request):
        await _assert_guild_access(request, guild_id)
        b = app.state.bot
        g = b.get_guild(int(guild_id)) if b else None
        u = ai_limits.usage(guild_id)
        return {
            "online": bool(b and b.is_ready()),
            "guildName": g.name if g else None,
            "memberCount": g.member_count if g else None,
            "aiUsage": u,
        }

    @app.get("/guilds/{guild_id}/channels")
    async def guild_channels(guild_id: str, request: Request):
        await _assert_guild_access(request, guild_id)
        b = app.state.bot
        g = b.get_guild(int(guild_id)) if b else None
        if not g:
            return {"channels": []}
        return {
            "channels": [
                {"id": str(c.id), "name": c.name, "type": str(c.type)}
                for c in g.channels
            ]
        }

    @app.get("/guilds/{guild_id}/roles")
    async def guild_roles(guild_id: str, request: Request):
        await _assert_guild_access(request, guild_id)
        b = app.state.bot
        g = b.get_guild(int(guild_id)) if b else None
        if not g:
            return {"roles": []}
        return {
            "roles": [{"id": str(r.id), "name": r.name, "color": r.color.value} for r in g.roles]
        }

    @app.get("/appeals/servers")
    async def appeals_servers():
        """Public list of guilds with appeals enabled (for Appeal a punishment)."""
        b = app.state.bot
        out = []
        if b and b.is_ready():
            for g in b.guilds:
                data = storage.load_guild(g.id)
                if (data.get("appeals") or {}).get("enabled"):
                    icon = g.icon.url if g.icon else None
                    out.append({"id": str(g.id), "name": g.name, "icon": icon})
        return {"servers": out}

    @app.post("/appeals/submit")
    async def appeals_submit(body: AppealSubmit, request: Request):
        user = session_user(request)
        if not user:
            raise HTTPException(401, "Login required to submit an appeal")
        data = storage.load_guild(body.guild_id)
        ap = data.get("appeals") or {}
        if not ap.get("enabled"):
            raise HTTPException(400, "Appeals are not enabled on that server")
        import time, uuid

        aid = str(uuid.uuid4())[:8]
        record = {
            "id": aid,
            "userId": str(user["id"]),
            "username": user.get("username"),
            "punishment": body.punishment_type,
            "reason": body.reason[:2000],
            "extra": (body.extra or "")[:2000],
            "status": "pending",
            "createdAt": time.time(),
        }

        def mut(d):
            recs = d.setdefault("appealsRecords", {})
            recs[aid] = record

        storage.update_guild(body.guild_id, mut)

        # Post to channel if possible
        b = app.state.bot
        ch_id = ap.get("channelId")
        if b and ch_id:
            ch = b.get_channel(int(ch_id))
            if ch:
                try:
                    await ch.send(
                        f"**Appeal `{aid}`** from <@{user['id']}> ({user.get('username')})\n"
                        f"Type: **{body.punishment_type}**\n"
                        f"Reason: {body.reason[:1500]}"
                    )
                except Exception as e:
                    log.warning("Could not post appeal: %s", e)
        return {"ok": True, "appealId": aid}

    @app.get("/advertise/list")
    async def advertise_list():
        b = app.state.bot
        out = []
        if b and b.is_ready():
            for g in b.guilds:
                data = storage.load_guild(g.id)
                ad = data.get("advertise") or {}
                if ad.get("listed"):
                    out.append(
                        {
                            "id": str(g.id),
                            "name": g.name,
                            "icon": g.icon.url if g.icon else None,
                            "description": ad.get("description", ""),
                            "category": ad.get("category", "General"),
                            "invite": ad.get("invite"),
                        }
                    )
        return {"servers": out}

    async def _assert_guild_access(request: Request, guild_id: str):
        user, sess = require_user(request)
        b = app.state.bot
        if not b or not b.is_ready() or not b.get_guild(int(guild_id)):
            raise HTTPException(404, "Bot is not in that server")
        try:
            raw = await oauth.fetch_user_guilds(sess["access_token"])
        except Exception:
            raise HTTPException(502, "Could not verify guild access")
        for g in raw:
            if str(g["id"]) == str(guild_id) and oauth.can_manage(g):
                return
        raise HTTPException(403, "You cannot manage this server")

    # Static dashboard
    if PUBLIC_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=str(PUBLIC_DIR)), name="assets")

        @app.get("/")
        async def index():
            index_path = PUBLIC_DIR / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            return HTMLResponse("<h1>OmniBot</h1><p>Dashboard files missing.</p>")

        @app.get("/tos")
        @app.get("/terms")
        async def tos():
            p = PUBLIC_DIR / "tos.html"
            if p.exists():
                return FileResponse(p)
            return HTMLResponse("<h1>Terms of Service</h1>")

        @app.get("/privacy-policy")
        @app.get("/privacy")
        async def privacy():
            p = PUBLIC_DIR / "privacy-policy.html"
            if p.exists():
                return FileResponse(p)
            return HTMLResponse("<h1>Privacy Policy</h1>")

    return app
