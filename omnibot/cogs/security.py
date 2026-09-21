"""Anti-nuke monitor (safe: log/alert/lockdown, no auto-ban by default)."""
from __future__ import annotations

import time
from collections import defaultdict

import discord
from discord.ext import commands

from omnibot import storage


class Security(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._actions: dict[str, list[float]] = defaultdict(list)

    def _track(self, guild_id: int, kind: str) -> int:
        key = f"{guild_id}:{kind}"
        now = time.time()
        data = storage.load_guild(guild_id)
        sec = data.get("security") or {}
        window = float((sec.get("antiNuke") or {}).get("windowMs") or 30)
        bucket = [t for t in self._actions[key] if now - t < window]
        bucket.append(now)
        self._actions[key] = bucket
        return len(bucket)

    async def _alert(self, guild: discord.Guild, text: str):
        data = storage.load_guild(guild.id)
        if not (data.get("security") or {}).get("enabled"):
            return
        ch_id = storage.get_path(data, "logging.channelId") or storage.get_path(
            data, "settings.modLogChannel"
        )
        if ch_id:
            ch = guild.get_channel(int(ch_id))
            if isinstance(ch, discord.TextChannel):
                try:
                    await ch.send(f"🛡️ **Security:** {text}")
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        data = storage.load_guild(guild.id)
        sec = data.get("security") or {}
        if not sec.get("enabled"):
            return
        count = self._track(guild.id, "channelDelete")
        thr = int((sec.get("antiNuke") or {}).get("thresholds", {}).get("channelDelete") or 3)
        if count >= thr:
            await self._alert(guild, f"Mass channel deletion detected ({count} in window). Mode={sec.get('mode')}")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        data = storage.load_guild(guild.id)
        sec = data.get("security") or {}
        if not sec.get("enabled"):
            return
        count = self._track(guild.id, "roleDelete")
        thr = int((sec.get("antiNuke") or {}).get("thresholds", {}).get("roleDelete") or 3)
        if count >= thr:
            await self._alert(guild, f"Mass role deletion detected ({count} in window). Mode={sec.get('mode')}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Security(bot))
