"""Advanced anti-nuke: monitor mass channel/role/ban/kick/webhook actions with alert or lockdown."""
from __future__ import annotations

import time
from collections import defaultdict

import discord
from discord import app_commands
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
        window = float((sec.get("antiNuke") or {}).get("windowSec") or (sec.get("antiNuke") or {}).get("windowMs") or 30)
        if window > 1000:
            window = window / 1000.0
        bucket = [t for t in self._actions[key] if now - t < window]
        bucket.append(now)
        self._actions[key] = bucket
        return len(bucket)

    async def _alert(self, guild: discord.Guild, text: str, mode: str):
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
                    emb = discord.Embed(
                        title="🛡️ Security alert",
                        description=text,
                        color=0xEF4444,
                        timestamp=discord.utils.utcnow(),
                    )
                    emb.add_field(name="Mode", value=mode)
                    await ch.send(embed=emb)
                except Exception:
                    pass
        if mode == "lockdown":
            try:
                for ch in guild.text_channels:
                    try:
                        ow = ch.overwrites_for(guild.default_role)
                        ow.send_messages = False
                        await ch.set_permissions(guild.default_role, overwrite=ow, reason="Anti-nuke lockdown")
                    except Exception:
                        continue
            except Exception:
                pass

    async def _check(self, guild: discord.Guild, kind: str, label: str):
        data = storage.load_guild(guild.id)
        sec = data.get("security") or {}
        if not sec.get("enabled"):
            return
        an = sec.get("antiNuke") or {}
        if an.get("enabled") is False:
            return
        thr = int((an.get("thresholds") or {}).get(kind) or 3)
        count = self._track(guild.id, kind)
        if count >= thr:
            mode = sec.get("mode") or "alert"
            await self._alert(guild, f"{label} detected (**{count}** in window).", mode)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self._check(channel.guild, "channelDelete", "Mass channel deletion")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await self._check(channel.guild, "channelCreate", "Mass channel creation")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self._check(role.guild, "roleDelete", "Mass role deletion")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self._check(role.guild, "roleCreate", "Mass role creation")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await self._check(guild, "ban", "Mass ban")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self._check(member.guild, "kick", "Rapid member removals")

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        await self._check(channel.guild, "webhook", "Webhook changes")

    sec = app_commands.Group(name="antinuke", description="Advanced anti-nuke settings")

    @sec.command(name="config", description="Configure anti-nuke mode and thresholds")
    @app_commands.checks.has_permissions(administrator=True)
    async def antinuke_config(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        mode: str | None = None,
        window_seconds: app_commands.Range[int, 5, 120] | None = None,
        channel_delete_threshold: app_commands.Range[int, 1, 20] | None = None,
        ban_threshold: app_commands.Range[int, 1, 20] | None = None,
    ):
        if mode and mode not in ("monitor", "alert", "lockdown"):
            return await interaction.response.send_message(
                "Mode must be monitor, alert, or lockdown.", ephemeral=True
            )

        def mut(d):
            s = d.setdefault("security", {})
            if enabled is not None:
                s["enabled"] = enabled
            if mode is not None:
                s["mode"] = mode
            an = s.setdefault("antiNuke", {})
            an["enabled"] = True
            if window_seconds is not None:
                an["windowSec"] = int(window_seconds)
            thr = an.setdefault("thresholds", {})
            if channel_delete_threshold is not None:
                thr["channelDelete"] = int(channel_delete_threshold)
            if ban_threshold is not None:
                thr["ban"] = int(ban_threshold)

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Anti-nuke settings updated.", ephemeral=True)

    @sec.command(name="status", description="Show anti-nuke status")
    @app_commands.checks.has_permissions(administrator=True)
    async def antinuke_status(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        sec = data.get("security") or {}
        an = sec.get("antiNuke") or {}
        thr = an.get("thresholds") or {}
        emb = discord.Embed(title="🛡️ Anti-nuke status", color=0x5B6CFF)
        emb.add_field(name="Enabled", value=str(sec.get("enabled", False)))
        emb.add_field(name="Mode", value=str(sec.get("mode", "monitor")))
        emb.add_field(name="Window (s)", value=str(an.get("windowSec") or an.get("windowMs") or 30))
        emb.add_field(name="Channel delete thr", value=str(thr.get("channelDelete", 3)))
        emb.add_field(name="Ban thr", value=str(thr.get("ban", 3)))
        emb.add_field(name="Role delete thr", value=str(thr.get("roleDelete", 3)))
        await interaction.response.send_message(embed=emb, ephemeral=True)

    @sec.command(name="unlockdown", description="Lift lockdown (@everyone can send again)")
    @app_commands.checks.has_permissions(administrator=True)
    async def unlockdown(self, interaction: discord.Interaction):
        g = interaction.guild
        if not g:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        n = 0
        for ch in g.text_channels:
            try:
                ow = ch.overwrites_for(g.default_role)
                ow.send_messages = None
                await ch.set_permissions(g.default_role, overwrite=ow, reason="Lift anti-nuke lockdown")
                n += 1
            except Exception:
                continue
        await interaction.followup.send(f"Lockdown lifted on **{n}** channels.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Security(bot))
