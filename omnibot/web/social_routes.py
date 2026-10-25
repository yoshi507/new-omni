"""Social feeds dashboard API helpers."""
from __future__ import annotations

from fastapi import HTTPException, Request
from pydantic import BaseModel

from omnibot import storage
from omnibot.services import social_feeds


class SocialFeedBody(BaseModel):
    platform: str
    handle: str


def register_social_routes(app, assert_guild_access):
    @app.get("/guilds/{guild_id}/social/feeds")
    async def list_social_feeds(guild_id: str, request: Request):
        await assert_guild_access(request, guild_id)
        data = storage.load_guild(guild_id)
        s = data.get("social") or {}
        return {
            "enabled": bool(s.get("enabled")),
            "channelId": s.get("channelId") or "",
            "feeds": list(s.get("feeds") or []),
        }

    @app.post("/guilds/{guild_id}/social/feeds")
    async def add_social_feed(guild_id: str, body: SocialFeedBody, request: Request):
        await assert_guild_access(request, guild_id)
        try:
            platform, handle = social_feeds.normalise(body.platform, body.handle)
        except social_feeds.FeedError as e:
            raise HTTPException(400, str(e))

        def mut(d):
            s = d.setdefault("social", {})
            feeds = list(s.get("feeds") or [])
            for f in feeds:
                if str(f.get("platform", "")).lower() == platform and str(f.get("handle", "")).lower() == handle.lower():
                    return
            feeds.append({"platform": platform, "handle": handle})
            s["feeds"] = feeds[-20:]

        storage.update_guild(guild_id, mut)
        data = storage.load_guild(guild_id)
        return {"ok": True, "feeds": list((data.get("social") or {}).get("feeds") or [])}

    @app.delete("/guilds/{guild_id}/social/feeds/{index}")
    async def remove_social_feed(guild_id: str, index: int, request: Request):
        await assert_guild_access(request, guild_id)
        if index < 0:
            raise HTTPException(400, "Invalid index")

        def mut(d):
            s = d.setdefault("social", {})
            feeds = list(s.get("feeds") or [])
            if index >= len(feeds):
                return
            feeds.pop(index)
            s["feeds"] = feeds

        storage.update_guild(guild_id, mut)
        data = storage.load_guild(guild_id)
        return {"ok": True, "feeds": list((data.get("social") or {}).get("feeds") or [])}
