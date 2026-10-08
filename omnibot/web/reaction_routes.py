"""Reaction role multi-panel API routes."""
from __future__ import annotations

from fastapi import HTTPException, Request
from pydantic import BaseModel

from omnibot import storage


class ReactionPanelBody(BaseModel):
    channel_id: str
    title: str = "Roles"
    description: str = "React to get a role"
    pairs: list[dict[str, str]] = []


def register_reaction_routes(app, assert_guild_access):
    """Register multi-panel reaction-role endpoints on the FastAPI app."""

    @app.post("/guilds/{guild_id}/roles/reaction-panel")
    async def post_reaction_panel(guild_id: str, body: ReactionPanelBody, request: Request):
        await assert_guild_access(request, guild_id)
        import discord as _discord

        b = app.state.bot
        if not b:
            raise HTTPException(503, "Bot offline")
        g = b.get_guild(int(guild_id))
        if not g:
            raise HTTPException(400, "Bot not in guild")
        ch = g.get_channel(int(body.channel_id))
        if not isinstance(ch, _discord.TextChannel):
            raise HTTPException(400, "Channel not found")
        pairs = []
        for p in (body.pairs or [])[:10]:
            em = str(p.get("emoji") or "").strip()
            rid = str(p.get("role_id") or "").strip()
            if em and rid:
                role = g.get_role(int(rid))
                if role:
                    pairs.append((em, role))
        if not pairs:
            raise HTTPException(400, "Add at least one emoji + role pair")
        lines = [f"{em} — {ro.mention}" for em, ro in pairs]
        panel_title = (body.title or "Roles")[:100]
        emb = _discord.Embed(
            title=panel_title[:256],
            description=((body.description or "")[:1200] + "\n\n" + "\n".join(lines))[:4000],
            color=0x5B6CFF,
        )
        emb.set_footer(text="React to get or remove a role · OmniBot")
        msg = await ch.send(embed=emb)
        failed = []
        for em, _ in pairs:
            try:
                await msg.add_reaction(em)
            except Exception:
                failed.append(em)

        def mut(d):
            rr = d.setdefault("reactionRoles", {})
            for em, ro in pairs:
                rr[f"{msg.id}:{em}"] = {
                    "messageId": str(msg.id),
                    "emoji": em,
                    "roleId": str(ro.id),
                    "channelId": str(ch.id),
                    "panelTitle": panel_title,
                }
            meta = d.setdefault("reactionPanels", {})
            meta[str(msg.id)] = {
                "messageId": str(msg.id),
                "channelId": str(ch.id),
                "title": panel_title,
            }

        storage.update_guild(guild_id, mut)
        return {"ok": True, "messageId": str(msg.id), "failedEmojis": failed}

    @app.get("/guilds/{guild_id}/roles/reaction-list")
    async def list_reaction_roles(guild_id: str, request: Request):
        await assert_guild_access(request, guild_id)
        data = storage.load_guild(guild_id)
        rr = data.get("reactionRoles") or {}
        items = []
        panels_map: dict = {}
        for k, v in rr.items():
            item = {"key": k, **v}
            items.append(item)
            mid = str(v.get("messageId") or k.split(":")[0])
            panels_map.setdefault(
                mid,
                {
                    "messageId": mid,
                    "channelId": v.get("channelId"),
                    "title": v.get("panelTitle") or "Panel",
                    "bindings": [],
                },
            )
            panels_map[mid]["bindings"].append(item)
        for mid, meta in (data.get("reactionPanels") or {}).items():
            if mid in panels_map and meta.get("title"):
                panels_map[mid]["title"] = meta["title"]
        return {"items": items, "panels": list(panels_map.values())}

    @app.delete("/guilds/{guild_id}/roles/reaction-panel/{message_id}")
    async def delete_reaction_panel(guild_id: str, message_id: str, request: Request):
        await assert_guild_access(request, guild_id)
        mid = str(message_id).strip()
        removed = 0

        def mut(d):
            nonlocal removed
            rr = d.get("reactionRoles") or {}
            keys = [
                k
                for k, v in rr.items()
                if str(v.get("messageId")) == mid or k.startswith(f"{mid}:")
            ]
            for k in keys:
                del rr[k]
                removed += 1
            d["reactionRoles"] = rr
            meta = d.get("reactionPanels") or {}
            meta.pop(mid, None)
            d["reactionPanels"] = meta

        storage.update_guild(guild_id, mut)
        return {"ok": True, "removed": removed}
