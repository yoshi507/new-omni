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

log = logging.getLogger("omnibot.web")

PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent / "public" / "dashboard"
COOKIE = "omnibot_session"


class SettingsPatch(BaseModel):
    patch: dict[str, Any]


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
        if not b or not b.is_ready():
            raise HTTPException(503, "Bot is still starting, try again in a moment")
        g = b.get_guild(int(gid))
        if not g:
            import asyncio as _asyncio

            await _asyncio.sleep(0.4)
            g = b.get_guild(int(gid))
        if not g:
            raise HTTPException(404, "Bot is not in that server")
        try:
            raw = await _user_guilds(sess)
            for ug in raw:
                if str(ug.get("id")) == gid and oauth.can_manage(ug):
                    return
        except Exception as e:
            log.warning("OAuth guild check failed (%s); trying member fallback", e)
        try:
            member = g.get_member(int(user["id"]))
            if member is None:
                member = await g.fetch_member(int(user["id"]))
            if member and (
                member.guild_permissions.administrator or member.guild_permissions.manage_guild
            ):
                return
        except Exception as e:
            log.warning("Member fallback failed: %s", e)
        raise HTTPException(403, "You cannot manage this server")

    def _channels_payload(g) -> list[dict[str, Any]]:
        out = []
        for c in g.channels:
            tname = getattr(c.type, "name", None) or str(c.type)
            out.append({"id": str(c.id), "name": c.name, "type": tname})
        return out

    def _roles_payload(g) -> list[dict[str, Any]]:
        return [{"id": str(r.id), "name": r.name, "color": r.color.value} for r in g.roles]

    def _settings_payload(guild_id: str) -> dict[str, Any]:
        data = storage.load_guild(guild_id)
        flat = {}
        for s in SETTINGS:
            flat[s["id"]] = storage.get_path(data, s["path"], s["default"])
        return flat

    @app.get("/health")
    async def health():
        b = app.state.bot
        return {
            "ok": True,
            "service": "OmniBot API",
            "discordReady": bool(b and b.is_ready()),
            "guilds": len(b.guilds) if b and b.is_ready() else 0,
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
            try:
                sess = sessions.get(sid)
                if sess:
                    raw = await oauth.fetch_user_guilds(access)
                    sessions.set_cached_guilds(sess, raw)
            except Exception as e:
                log.warning("Prefetch guilds failed: %s", e)
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
            raw = await _user_guilds(sess)
        except Exception:
            raise HTTPException(502, "Failed to fetch Discord guilds — wait a few seconds and refresh")
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

    @app.get("/guilds/{guild_id}/bundle")
    async def guild_bundle(guild_id: str, request: Request):
        await _assert_guild_access(request, guild_id)
        b = app.state.bot
        g = b.get_guild(int(guild_id)) if b else None
        u = ai_limits.usage(guild_id)
        channels = _channels_payload(g) if g else []
        roles = _roles_payload(g) if g else []
        log.info("bundle guild=%s channels=%s roles=%s", guild_id, len(channels), len(roles))
        return {
            "settings": _settings_payload(guild_id),
            "defaults": get_defaults_flat(),
            "bot": {
                "online": bool(b and b.is_ready()),
                "guildName": g.name if g else None,
                "memberCount": g.member_count if g else None,
                "aiUsage": u,
            },
            "channels": channels,
            "roles": roles,
        }

    @app.get("/guilds/{guild_id}/settings")
    async def get_settings(guild_id: str, request: Request):
        await _assert_guild_access(request, guild_id)
        return {"settings": _settings_payload(guild_id), "defaults": get_defaults_flat()}

    @app.put("/guilds/{guild_id}/settings")
    async def put_settings(guild_id: str, body: SettingsPatch, request: Request):
        await _assert_guild_access(request, guild_id)
        before = storage.load_guild(guild_id)
        before_hp = dict(before.get("honeypot") or {})

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

        after = storage.load_guild(guild_id)
        after_hp = after.get("honeypot") or {}
        b = app.state.bot
        g = b.get_guild(int(guild_id)) if b else None
        if g:
            try:
                from omnibot.cogs.engagement_extra import (
                    delete_honeypot_warning,
                    post_honeypot_warning,
                )
                import discord as _discord

                was_on = bool(before_hp.get("enabled"))
                now_on = bool(after_hp.get("enabled"))
                ch_id = after_hp.get("channelId") or before_hp.get("channelId")

                if was_on and not now_on:
                    await delete_honeypot_warning(g, {"honeypot": before_hp})

                    def clear_msg(d):
                        (d.get("honeypot") or {}).pop("warningMessageId", None)

                    storage.update_guild(guild_id, clear_msg)

                elif now_on and ch_id:
                    await delete_honeypot_warning(g, {"honeypot": before_hp})
                    ch = g.get_channel(int(ch_id))
                    if isinstance(ch, _discord.TextChannel):
                        try:
                            msg = await post_honeypot_warning(ch)

                            def save_msg(d):
                                d.setdefault("honeypot", {})["warningMessageId"] = str(msg.id)
                                d["honeypot"]["channelId"] = str(ch_id)
                                d["honeypot"]["enabled"] = True

                            storage.update_guild(guild_id, save_msg)
                        except Exception as e:
                            log.warning("Honeypot warning post failed: %s", e)
            except Exception as e:
                log.warning("Honeypot side-effect failed: %s", e)

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
        return {"channels": _channels_payload(g)}

    @app.get("/guilds/{guild_id}/roles")
    async def guild_roles(guild_id: str, request: Request):
        await _assert_guild_access(request, guild_id)
        b = app.state.bot
        g = b.get_guild(int(guild_id)) if b else None
        if not g:
            return {"roles": []}
        return {"roles": _roles_payload(g)}

    class TicketPanelBody(BaseModel):
        channel_id: str
        title: str = "Support Tickets"
        description: str = (
            "Click a button below to open a private ticket with staff.\n"
            "Please only open a ticket if you need help."
        )

    @app.post("/guilds/{guild_id}/tickets/panel")
    async def post_ticket_panel(guild_id: str, body: TicketPanelBody, request: Request):
        await _assert_guild_access(request, guild_id)
        b = app.state.bot
        g = b.get_guild(int(guild_id)) if b else None
        if not g:
            raise HTTPException(404, "Guild not found")

        data = storage.load_guild(guild_id)
        tcfg = data.get("tickets") or {}
        if not tcfg.get("categoryId"):
            raise HTTPException(
                400,
                "Set a ticket category first (Tickets → category ID, or /ticket setup in Discord).",
            )

        ch = g.get_channel(int(body.channel_id))
        import discord as _discord

        if not isinstance(ch, _discord.TextChannel):
            raise HTTPException(400, "channel_id must be a text channel")

        kinds = [
            ("support", "Support"),
            ("report", "Report"),
            ("partnership", "Partnership"),
            ("staff", "Staff application"),
            ("bug", "Bug report"),
            ("other", "Other"),
        ]
        view = _discord.ui.View(timeout=None)
        for i, (value, label) in enumerate(kinds):
            view.add_item(
                _discord.ui.Button(
                    label=label,
                    style=_discord.ButtonStyle.primary
                    if value != "other"
                    else _discord.ButtonStyle.secondary,
                    custom_id=f"omnibot:ticket:{value}",
                    row=0 if i < 5 else 1,
                )
            )

        emb = _discord.Embed(
            title=(body.title or "Support Tickets")[:256],
            description=(body.description or "")[:4000],
            color=0x5B6CFF,
        )
        emb.set_footer(text="OmniBot tickets · one click opens a private channel")
        try:
            msg = await ch.send(embed=emb, view=view)
        except Exception as e:
            raise HTTPException(500, f"Could not post panel: {e}")

        def mut(d):
            t = d.setdefault("tickets", {})
            t["enabled"] = True
            t["panelChannelId"] = str(ch.id)
            t["panelMessageId"] = str(msg.id)

        storage.update_guild(guild_id, mut)
        return {"ok": True, "messageId": str(msg.id), "channelId": str(ch.id)}

    public_dir = PUBLIC_DIR if PUBLIC_DIR.is_dir() else Path.cwd() / "public" / "dashboard"
    if public_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(public_dir)), name="assets")

        @app.get("/")
        async def index():
            index_path = public_dir / "index.html"
            if index_path.exists():
                return FileResponse(
                    index_path,
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
                )
            return HTMLResponse("<h1>OmniBot</h1><p>Dashboard files missing.</p>")

        @app.get("/tos")
        @app.get("/terms")
        async def tos():
            p = public_dir / "tos.html"
            if p.exists():
                return FileResponse(p)
            return HTMLResponse("<h1>Terms of Service</h1>")

        @app.get("/privacy-policy")
        @app.get("/privacy")
        async def privacy():
            p = public_dir / "privacy-policy.html"
            if p.exists():
                return FileResponse(p)
            return HTMLResponse("<h1>Privacy Policy</h1>")

    return app
