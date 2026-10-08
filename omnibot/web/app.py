"""FastAPI application: health, OAuth, settings, static dashboard."""
from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from omnibot.config import settings
from omnibot import storage
from omnibot.settings_registry import SETTINGS, get_setting_by_id, validate_setting, get_defaults_flat
from omnibot.web import sessions, oauth
from omnibot.services import ai_limits
from omnibot.web.social_routes import register_social_routes
from omnibot.web.reaction_routes import register_reaction_routes

log = logging.getLogger("omnibot.web")
PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent / "public" / "dashboard"
COOKIE = "omnibot_session"

class SettingsPatch(BaseModel):
    patch: dict[str, Any]

def create_app(bot, deploy_marker: str) -> FastAPI:
    app = FastAPI(title="OmniBot API", docs_url=None, redoc_url=None)
    app.state.bot = bot
    app.state.deploy_marker = deploy_marker
    app.add_middleware(CORSMiddleware, allow_origins=settings.dashboard_origins + ["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def strip_api_prefix(request: Request, call_next):
        path = request.scope.get("path") or ""
        if path == "/api":
            request.scope["path"] = "/"
        elif path.startswith("/api/"):
            request.scope["path"] = path[4:] or "/"
        return await call_next(request)

    def _cookie_kwargs() -> dict:
        secure = settings.public_base_url.lower().startswith("https")
        return {"httponly": True, "samesite": "lax", "max_age": 60 * 60 * 24 * 7, "path": "/", "secure": secure}

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

    async def _user_guilds(sess: dict[str, Any]) -> list[dict[str, Any]]:
        cached = sessions.get_cached_guilds(sess)
        if cached is not None:
            return cached
        async with sessions.guilds_lock():
            cached = sessions.get_cached_guilds(sess)
            if cached is not None:
                return cached
            try:
                raw = await oauth.fetch_user_guilds(sess["access_token"])
                sessions.set_cached_guilds(sess, raw)
                return raw
            except Exception as e:
                stale = sessions.get_cached_guilds(sess, allow_stale=True)
                if stale is not None:
                    log.warning("Using stale guild cache after error: %s", e)
                    return stale
                raise

    async def _assert_guild_access(request: Request, guild_id: str) -> None:
        user, sess = require_user(request)
        b = app.state.bot
        gid = str(guild_id).strip()
        if not gid.isdigit():
            raise HTTPException(400, f"Invalid guild id: {guild_id!r}")
        try:
            guilds = await _user_guilds(sess)
        except Exception as e:
            log.warning("guild list failed: %s", e)
            guilds = []
        managed = {str(g.get("id")) for g in guilds if oauth.can_manage(g)}
        if gid not in managed:
            raise HTTPException(403, "You need Administrator in that server to manage it.")
        if b and hasattr(b, "get_guild") and b.get_guild(int(gid)) is None:
            raise HTTPException(400, "Bot is not in that server. Invite OmniBot first.")

    def _settings_payload(guild_id: str) -> dict[str, Any]:
        data = storage.load_guild(guild_id)
        out: dict[str, Any] = {}
        for s in SETTINGS:
            parts = s["path"].split(".")
            cur = data
            for p in parts:
                if not isinstance(cur, dict):
                    cur = None
                    break
                cur = cur.get(p)
            out[s["id"]] = s["default"] if cur is None else cur
        return out

    @app.get("/health")
    async def health():
        b = app.state.bot
        return {"ok": True, "discordReady": bool(b and getattr(b, "is_ready", lambda: False)()), "marker": app.state.deploy_marker, "guilds": len(getattr(b, "guilds", []) or [])}

    @app.get("/version")
    async def version():
        b = app.state.bot
        return {"marker": app.state.deploy_marker, "discordReady": bool(b and getattr(b, "is_ready", lambda: False)()), "dashboardUrl": settings.public_base_url}

    @app.get("/auth/login")
    async def auth_login():
        if not settings.discord_client_id or not settings.discord_client_secret:
            raise HTTPException(503, "OAuth not configured (DISCORD_CLIENT_ID/SECRET)")
        state = secrets.token_urlsafe(16)
        url = f"https://discord.com/api/oauth2/authorize?client_id={settings.discord_client_id}&redirect_uri={settings.discord_redirect_uri}&response_type=code&scope=identify%20guilds&state={state}"
        return RedirectResponse(url)

    @app.get("/auth/discord/callback")
    async def auth_callback(request: Request, code: str | None = None, error: str | None = None):
        if error or not code:
            return RedirectResponse("/?error=oauth")
        try:
            token = await oauth.exchange_code(code)
            access = token["access_token"]
            user = await oauth.fetch_user(access)
            sid = sessions.create(user, access)
            try:
                sess = sessions.get(sid)
                if sess:
                    sessions.set_cached_guilds(sess, await oauth.fetch_user_guilds(access))
            except Exception as e:
                log.warning("Prefetch guilds failed: %s", e)
            resp = RedirectResponse("/?logged_in=1")
            resp.set_cookie(COOKIE, sid, **_cookie_kwargs())
            return resp
        except Exception as e:
            log.error("OAuth callback failed: %s", e)
            return RedirectResponse("/?error=callback")

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
        resp.delete_cookie(COOKIE, path="/")
        return resp

    @app.get("/guilds")
    async def list_guilds(request: Request):
        user, sess = require_user(request)
        try:
            raw = await _user_guilds(sess)
        except Exception as e:
            raise HTTPException(502, f"Could not load Discord guilds: {e}")
        b = app.state.bot
        bot_ids = {str(g.id) for g in getattr(b, "guilds", []) or []} if b else set()
        out = []
        for g in raw:
            if not oauth.can_manage(g):
                continue
            gid = str(g.get("id"))
            out.append({"id": gid, "name": g.get("name"), "icon": g.get("icon"), "botIn": gid in bot_ids})
        return {"guilds": out, "user": {"id": user.get("id"), "username": user.get("username"), "global_name": user.get("global_name")}}

    @app.get("/guilds/{guild_id}/bundle")
    async def guild_bundle(guild_id: str, request: Request):
        await _assert_guild_access(request, guild_id)
        b = app.state.bot
        g = b.get_guild(int(guild_id)) if b else None
        channels, roles = [], []
        if g:
            for c in g.channels:
                channels.append({"id": str(c.id), "name": getattr(c, "name", str(c.id)), "type": str(getattr(getattr(c, "type", None), "name", ""))})
            for r in g.roles:
                if not r.is_default():
                    roles.append({"id": str(r.id), "name": r.name, "position": r.position})
            roles.sort(key=lambda x: -x["position"])
        return {"settings": _settings_payload(guild_id), "defaults": get_defaults_flat(), "channels": channels, "roles": roles}

    @app.get("/guilds/{guild_id}/settings")
    async def get_settings(guild_id: str, request: Request):
        await _assert_guild_access(request, guild_id)
        return {"settings": _settings_payload(guild_id), "defaults": get_defaults_flat()}

    @app.put("/guilds/{guild_id}/settings")
    async def put_settings(guild_id: str, body: SettingsPatch, request: Request):
        await _assert_guild_access(request, guild_id)
        patch = body.patch or {}
        def mut(d):
            for key, val in patch.items():
                defn = get_setting_by_id(key)
                if not defn:
                    continue
                ok, cleaned, err = validate_setting(defn, val)
                if not ok:
                    continue
                parts = defn["path"].split(".")
                cur = d
                for p in parts[:-1]:
                    cur = cur.setdefault(p, {})
                cur[parts[-1]] = cleaned
        storage.update_guild(guild_id, mut)
        return {"ok": True, "settings": _settings_payload(guild_id)}

    @app.get("/guilds/{guild_id}/bot")
    async def guild_bot(guild_id: str, request: Request):
        await _assert_guild_access(request, guild_id)
        b = app.state.bot
        g = b.get_guild(int(guild_id)) if b else None
        return {"inGuild": g is not None, "name": g.name if g else None}

    @app.get("/guilds/{guild_id}/channels")
    async def guild_channels(guild_id: str, request: Request):
        await _assert_guild_access(request, guild_id)
        b = app.state.bot
        g = b.get_guild(int(guild_id)) if b else None
        if not g:
            return {"channels": []}
        return {"channels": [{"id": str(c.id), "name": getattr(c, "name", "")} for c in g.channels]}

    @app.get("/guilds/{guild_id}/roles")
    async def guild_roles(guild_id: str, request: Request):
        await _assert_guild_access(request, guild_id)
        b = app.state.bot
        g = b.get_guild(int(guild_id)) if b else None
        if not g:
            return {"roles": []}
        return {"roles": [{"id": str(r.id), "name": r.name} for r in g.roles if not r.is_default()]}

    class TicketPanelBody(BaseModel):
        channel_id: str
        title: str | None = None
        description: str | None = None

    @app.post("/guilds/{guild_id}/tickets/panel")
    async def post_ticket_panel(guild_id: str, body: TicketPanelBody, request: Request):
        await _assert_guild_access(request, guild_id)
        import discord as _discord
        b = app.state.bot
        if not b:
            raise HTTPException(503, "Bot offline")
        g = b.get_guild(int(guild_id))
        if not g:
            raise HTTPException(400, "Bot not in guild")
        ch = g.get_channel(int(body.channel_id))
        if ch is None:
            raise HTTPException(400, "Channel not found")
        view = _discord.ui.View(timeout=None)
        view.add_item(_discord.ui.Button(label="Open Ticket", style=_discord.ButtonStyle.primary, custom_id="omnibot:ticket:open"))
        emb = _discord.Embed(title=(body.title or "Support Tickets")[:256], description=(body.description or "Click to open a ticket.")[:4000], color=0x5B6CFF)
        msg = await ch.send(embed=emb, view=view)
        def mut(d):
            t = d.setdefault("tickets", {})
            t["enabled"] = True
            t["panelChannelId"] = str(ch.id)
            t["panelMessageId"] = str(msg.id)
        storage.update_guild(guild_id, mut)
        return {"ok": True, "messageId": str(msg.id)}

    # Reaction role multi-panel API
    register_reaction_routes(app, _assert_guild_access)

    # Social feeds (platform + handle multi)
    register_social_routes(app, _assert_guild_access)

    public_dir = PUBLIC_DIR if PUBLIC_DIR.is_dir() else Path.cwd() / "public" / "dashboard"
    if public_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(public_dir)), name="assets")

        @app.get("/")
        async def index():
            index_path = public_dir / "index.html"
            if index_path.exists():
                return FileResponse(index_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
            return HTMLResponse("<h1>OmniBot</h1>")

        @app.get("/tos")
        @app.get("/terms")
        async def tos():
            p = public_dir / "tos.html"
            return FileResponse(p) if p.exists() else HTMLResponse("<h1>Terms</h1>")

        @app.get("/privacy-policy")
        @app.get("/privacy")
        async def privacy():
            p = public_dir / "privacy-policy.html"
            return FileResponse(p) if p.exists() else HTMLResponse("<h1>Privacy</h1>")

    return app
