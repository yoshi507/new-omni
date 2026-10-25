"""Background poller that actually posts social feed notifications.

Feeds are configured with /social add or the dashboard and stored in
guild data under social.feeds. Every 5 minutes each feed is checked;
new items are posted to social.channelId. The first check of a feed only
records the latest item, so adding a feed never spams old posts.
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands, tasks

from omnibot import storage
from omnibot.services import social_feeds as sf

log = logging.getLogger("omnibot.social")

MAX_POSTS_PER_FEED = 3
COLORS = {"youtube": 0xFF0000, "reddit": 0xFF4500, "twitch": 0x9146FF}
LABELS = {"youtube": "YouTube", "reddit": "Reddit", "twitch": "Twitch"}


class SocialFeeds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sem = asyncio.Semaphore(4)
        self.poll.start()

    def cog_unload(self) -> None:
        self.poll.cancel()

    @tasks.loop(minutes=5)
    async def poll(self) -> None:
        async with sf.client() as client:
            for guild in list(self.bot.guilds):
                try:
                    await self._poll_guild(client, guild)
                except Exception:
                    log.exception("Social poll failed for guild %s", guild.id)

    @poll.before_loop
    async def _wait_ready(self) -> None:
        await self.bot.wait_until_ready()

    async def _poll_guild(self, client, guild: discord.Guild) -> None:
        data = storage.load_guild(guild.id)
        soc = data.get("social") or {}
        feeds = soc.get("feeds") or []
        if not soc.get("enabled") or not soc.get("channelId") or not feeds:
            return
        channel = guild.get_channel(int(soc["channelId"])) if str(soc["channelId"]).isdigit() else None
        if not isinstance(channel, discord.TextChannel):
            return

        results = await asyncio.gather(
            *(self._check_feed(client, f) for f in feeds if isinstance(f, dict)),
            return_exceptions=True,
        )
        updates: dict[tuple[str, str], dict] = {}
        for res in results:
            if isinstance(res, BaseException) or not res:
                continue
            key, patch, new_items, platform = res
            updates[key] = patch
            for item in reversed(new_items[:MAX_POSTS_PER_FEED]):  # oldest first
                await self._post(channel, platform, item)

        if updates:
            def mut(d):
                for f in (d.get("social") or {}).get("feeds") or []:
                    key = (str(f.get("platform", "")).lower(), str(f.get("handle", "")).lower())
                    if key in updates:
                        f.update(updates[key])

            storage.update_guild(guild.id, mut)

    async def _check_feed(self, client, feed: dict):
        platform = str(feed.get("platform", "")).lower()
        handle = str(feed.get("handle", ""))
        if platform not in sf.SUPPORTED or not handle:
            return None
        key = (platform, handle.lower())
        patch: dict = {}
        async with self._sem:
            try:
                if platform == "youtube":
                    cid = feed.get("channelId") or await sf.resolve_youtube_channel(client, handle)
                    patch["channelId"] = cid
                    items = await sf.fetch_youtube(client, cid)
                elif platform == "reddit":
                    items = await sf.fetch_reddit(client, handle.removeprefix("r/"))
                else:
                    items = await sf.fetch_twitch(client, handle.lower())
            except Exception as e:
                log.info("Feed %s/%s check failed: %s", platform, handle, e)
                return (key, {**patch, "lastError": str(e)[:200]}, [], platform)

        seen = feed.get("seenIds")
        ids = [i["id"] for i in items if i.get("id")]
        if seen is None:  # first check — remember, don't post
            patch.update(seenIds=ids[:20], lastError="")
            return (key, patch, [], platform)
        seen_set = set(seen)
        new_items = [i for i in items if i.get("id") and i["id"] not in seen_set]
        # Twitch: only one "live" item, remembered so we post once per stream.
        patch.update(seenIds=(ids + [s for s in seen if s not in ids])[:20], lastError="")
        return (key, patch, new_items, platform)

    async def _post(self, channel: discord.TextChannel, platform: str, item: dict) -> None:
        emb = discord.Embed(
            title=str(item.get("title") or "New post")[:256],
            url=str(item.get("url") or "")[:500] or None,
            color=COLORS.get(platform, 0x5B6CFF),
        )
        emb.set_author(name=str(item.get("author") or LABELS.get(platform, platform))[:256])
        if item.get("thumbnail"):
            emb.set_image(url=item["thumbnail"])
        emb.set_footer(text=f"{LABELS.get(platform, platform)} · via OmniBot")
        try:
            await channel.send(embed=emb)
        except discord.HTTPException as e:
            log.info("Could not post social item in %s: %s", channel.id, e)


async def setup(bot: commands.Bot):
    await bot.add_cog(SocialFeeds(bot))
