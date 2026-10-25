"""Fetchers for social feed notifications (YouTube, Reddit, Twitch).

Each fetcher returns a list of items, newest first:
    {"id": str, "title": str, "url": str, "author": str, "thumbnail": str | None}
"""
from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from omnibot.config import settings

log = logging.getLogger("omnibot.social")

SUPPORTED = ("youtube", "reddit", "twitch")
UA = "OmniBot/2.0 (+https://github.com/yoshi507/new-omni)"
_YT_ID = re.compile(r"^UC[\w-]{22}$")
# Most reliable first: canonical link / externalId belong to the page's own channel.
_YT_CHANNEL_PATTERNS = (
    re.compile(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"'),
    re.compile(r'"externalId":"(UC[\w-]{22})"'),
    re.compile(r'<meta itemprop="identifier" content="(UC[\w-]{22})"'),
)
_SUBREDDIT = re.compile(r"^[A-Za-z0-9_]{2,21}$")
_TWITCH_LOGIN = re.compile(r"^[A-Za-z0-9_]{3,25}$")
_ATOM = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
         "media": "http://search.yahoo.com/mrss/"}

_twitch_token: dict[str, Any] = {"token": "", "expires": 0.0}


class FeedError(Exception):
    pass


def normalise(platform: str, handle: str) -> tuple[str, str]:
    """Validate and clean a platform/handle pair. Raises FeedError with a user-facing message."""
    platform = (platform or "").strip().lower()
    handle = (handle or "").strip()
    if platform not in SUPPORTED:
        raise FeedError("Supported platforms: YouTube, Reddit, Twitch.")
    if platform == "youtube":
        handle = re.sub(r"^https?://(www\.)?youtube\.com/", "", handle).strip("/")
        handle = handle.removeprefix("channel/")
        if _YT_ID.match(handle):
            return platform, handle
        handle = handle.lstrip("@")
        if not re.match(r"^[\w.\-]{3,30}$", handle):
            raise FeedError("Enter a YouTube @handle or a channel ID starting with UC.")
        return platform, "@" + handle
    if platform == "reddit":
        handle = re.sub(r"^(https?://(www\.)?reddit\.com)?/?r/", "", handle).strip("/")
        if not _SUBREDDIT.match(handle):
            raise FeedError("Enter a subreddit name, e.g. `gaming`.")
        return platform, handle
    handle = re.sub(r"^https?://(www\.)?twitch\.tv/", "", handle).strip("/").lower()
    if not _TWITCH_LOGIN.match(handle):
        raise FeedError("Enter a Twitch login name, e.g. `shroud`.")
    if not (settings.twitch_client_id and settings.twitch_client_secret):
        raise FeedError("Twitch feeds need TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET set on the bot.")
    return platform, handle


async def resolve_youtube_channel(client: httpx.AsyncClient, handle: str) -> str:
    if _YT_ID.match(handle):
        return handle
    r = await client.get(
        f"https://www.youtube.com/{handle}",
        headers={"Accept-Language": "en"},
        cookies={"CONSENT": "YES+1", "SOCS": "CAI"},  # skip the EU consent wall
    )
    if r.status_code == 404:
        raise FeedError(f"YouTube channel {handle} not found.")
    r.raise_for_status()
    for pat in _YT_CHANNEL_PATTERNS:
        m = pat.search(r.text)
        if m:
            return m.group(1)
    raise FeedError(f"Couldn't find the channel ID for {handle}.")


async def fetch_youtube(client: httpx.AsyncClient, channel_id: str) -> list[dict]:
    r = await client.get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": channel_id})
    r.raise_for_status()
    root = ET.fromstring(r.text)
    author = root.findtext("a:title", default="YouTube", namespaces=_ATOM)
    items = []
    for e in root.findall("a:entry", _ATOM):
        vid = e.findtext("yt:videoId", namespaces=_ATOM)
        if not vid:
            continue
        thumb = e.find("media:group/media:thumbnail", _ATOM)
        items.append({
            "id": vid,
            "title": e.findtext("a:title", default="New video", namespaces=_ATOM),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "author": author,
            "thumbnail": thumb.get("url") if thumb is not None else None,
        })
    return items


async def fetch_reddit(client: httpx.AsyncClient, sub: str) -> list[dict]:
    r = await client.get(f"https://www.reddit.com/r/{sub}/new.json", params={"limit": 5, "raw_json": 1})
    if r.status_code == 200:
        items = []
        for child in (r.json().get("data") or {}).get("children") or []:
            d = child.get("data") or {}
            thumb = d.get("thumbnail")
            items.append({
                "id": d.get("name") or d.get("id"),
                "title": d.get("title") or "New post",
                "url": "https://www.reddit.com" + (d.get("permalink") or f"/r/{sub}"),
                "author": f"r/{sub} · u/{d.get('author', '?')}",
                "thumbnail": thumb if isinstance(thumb, str) and thumb.startswith("http") else None,
            })
        return items
    # JSON API often blocks hosting IPs — fall back to the Atom feed.
    r = await client.get(f"https://www.reddit.com/r/{sub}/new/.rss")
    r.raise_for_status()
    root = ET.fromstring(r.text)
    items = []
    for e in root.findall("a:entry", _ATOM):
        link = e.find("a:link", _ATOM)
        items.append({
            "id": e.findtext("a:id", namespaces=_ATOM),
            "title": e.findtext("a:title", default="New post", namespaces=_ATOM),
            "url": link.get("href") if link is not None else f"https://www.reddit.com/r/{sub}",
            "author": f"r/{sub}",
            "thumbnail": None,
        })
    return items


async def _twitch_app_token(client: httpx.AsyncClient) -> str:
    if _twitch_token["token"] and _twitch_token["expires"] > time.time() + 60:
        return _twitch_token["token"]
    r = await client.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": settings.twitch_client_id,
        "client_secret": settings.twitch_client_secret,
        "grant_type": "client_credentials",
    })
    r.raise_for_status()
    body = r.json()
    _twitch_token.update(token=body["access_token"], expires=time.time() + float(body.get("expires_in", 3600)))
    return _twitch_token["token"]


async def fetch_twitch(client: httpx.AsyncClient, login: str) -> list[dict]:
    """Returns one item while the channel is live (id = stream id), else []."""
    if not (settings.twitch_client_id and settings.twitch_client_secret):
        return []
    token = await _twitch_app_token(client)
    r = await client.get(
        "https://api.twitch.tv/helix/streams",
        params={"user_login": login},
        headers={"Client-Id": settings.twitch_client_id, "Authorization": f"Bearer {token}"},
    )
    if r.status_code == 401:
        _twitch_token["token"] = ""
    r.raise_for_status()
    items = []
    for s in r.json().get("data") or []:
        thumb = (s.get("thumbnail_url") or "").replace("{width}", "640").replace("{height}", "360")
        items.append({
            "id": s.get("id"),
            "title": s.get("title") or f"{login} is live",
            "url": f"https://www.twitch.tv/{login}",
            "author": f"{s.get('user_name', login)} is live · {s.get('game_name') or 'Twitch'}",
            "thumbnail": thumb or None,
        })
    return items


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers={"User-Agent": UA})
