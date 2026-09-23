"""Comprehensive server logging."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


def _log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    data = storage.load_guild(guild.id)
    lid = (data.get("logging") or {}).get("channelId")
    if not lid:
        return None
    ch = guild.get_channel(int(lid))
    return ch if isinstance(ch, discord.TextChannel) else None


async def _send_log(guild: discord.Guild, title: str, description: str, color: int = 0x5B6CFF):
    ch = _log_channel(guild)
    if not ch:
        return
    emb = discord.Embed(title=title, description=description[:4000], color=color)
    try:
        await ch.send(embed=emb)
    except Exception:
        pass


class LoggingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    log = app_commands.Group(name="logging", description="Moderation & server logs")

    @log.command(name="set", description="Set the log channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        def mut(d):
            d.setdefault("logging", {})["channelId"] = str(channel.id)
            d["logging"]["enabled"] = True

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Logs → {channel.mention}", ephemeral=True)

    @log.command(name="disable", description="Disable logging")
    @app_commands.checks.has_permissions(administrator=True)
    async def disable(self, interaction: discord.Interaction):
        def mut(d):
            d.setdefault("logging", {})["enabled"] = False

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message("Logging disabled.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        data = storage.load_guild(message.guild.id)
        if not (data.get("logging") or {}).get("enabled", True):
            return
        await _send_log(
            message.guild,
            "Message deleted",
            f"**Author:** {message.author} (`{message.author.id}`)\n"
            f"**Channel:** {message.channel.mention}\n"
            f"**Content:** {message.content[:1500] or '(empty/embed)'}",
            0xF04438,
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        data = storage.load_guild(before.guild.id)
        if not (data.get("logging") or {}).get("enabled", True):
            return
        await _send_log(
            before.guild,
            "Message edited",
            f"**Author:** {before.author}\n**Channel:** {before.channel.mention}\n"
            f"**Before:** {before.content[:800]}\n**After:** {after.content[:800]}",
            0xF5A524,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        data = storage.load_guild(member.guild.id)
        if not (data.get("logging") or {}).get("enabled", True):
            return
        await _send_log(member.guild, "Member joined", f"{member} (`{member.id}`)", 0x3DD68C)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        data = storage.load_guild(member.guild.id)
        if not (data.get("logging") or {}).get("enabled", True):
            return
        await _send_log(member.guild, "Member left", f"{member} (`{member.id}`)", 0x8B93A7)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await _send_log(guild, "Member banned", f"{user} (`{user.id}`)", 0xF04438)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        await _send_log(guild, "Member unbanned", f"{user} (`{user.id}`)", 0x3DD68C)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await _send_log(channel.guild, "Channel created", f"{channel.name} (`{channel.id}`)", 0x5B6CFF)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await _send_log(channel.guild, "Channel deleted", f"{channel.name} (`{channel.id}`)", 0xF04438)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await _send_log(role.guild, "Role created", f"{role.name} (`{role.id}`)", 0x5B6CFF)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await _send_log(role.guild, "Role deleted", f"{role.name} (`{role.id}`)", 0xF04438)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        data = storage.load_guild(member.guild.id)
        if not (data.get("logging") or {}).get("voice", False):
            return
        if before.channel != after.channel:
            b = before.channel.name if before.channel else "—"
            a = after.channel.name if after.channel else "—"
            await _send_log(member.guild, "Voice update", f"{member} : {b} → {a}", 0x8B93A7)


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))
