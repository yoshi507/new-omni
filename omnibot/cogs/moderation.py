"""Moderation commands + automod."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(f"Kicked {member} — {reason}")
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

    @app_commands.command(name="ban", description="Ban a member")
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(f"Banned {member} — {reason}")
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

    @app_commands.command(name="unban", description="Unban a user by ID")
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "Unbanned"):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=reason)
            await interaction.response.send_message(f"Unbanned {user}")
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.default_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320] = 10,
        reason: str = "No reason",
    ):
        import datetime

        try:
            until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
            await member.timeout(until, reason=reason)
            await interaction.response.send_message(f"Timed out {member} for {minutes}m — {reason}")
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

    @app_commands.command(name="purge", description="Delete recent messages")
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100] = 10):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        def mut(d):
            warns = d.setdefault("warns", {}).setdefault(str(member.id), [])
            warns.append({"reason": reason, "by": str(interaction.user.id)})

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Warned {member.mention}: {reason}")

    @app_commands.command(name="warnings", description="List warnings for a member")
    @app_commands.default_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        data = storage.load_guild(interaction.guild.id)
        warns = (data.get("warns") or {}).get(str(member.id)) or []
        if not warns:
            return await interaction.response.send_message("No warnings.", ephemeral=True)
        lines = [f"• {w.get('reason', '?')}" for w in warns[-15:]]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="automod", description="Configure word-filter automod")
    @app_commands.default_permissions(administrator=True)
    async def automod(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        blocked_words: str | None = None,
    ):
        def mut(d):
            am = d.setdefault("automod", {})
            if enabled is not None:
                am["enabled"] = enabled
            if blocked_words is not None:
                am["blockedWords"] = blocked_words

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message("Automod updated.", ephemeral=True)

    @app_commands.command(name="antispam", description="Toggle anti-spam")
    @app_commands.default_permissions(administrator=True)
    async def antispam(self, interaction: discord.Interaction, enabled: bool):
        def mut(d):
            d.setdefault("spamConfig", {})["enabled"] = enabled

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Anti-spam {'on' if enabled else 'off'}.", ephemeral=True)

    @app_commands.command(name="security", description="Set anti-nuke security mode")
    @app_commands.default_permissions(administrator=True)
    async def security(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        mode: str | None = None,
    ):
        def mut(d):
            s = d.setdefault("security", {})
            if enabled is not None:
                s["enabled"] = enabled
            if mode is not None:
                s["mode"] = mode

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message("Security updated.", ephemeral=True)

    @app_commands.command(name="honeypot", description="Configure honeypot channel")
    @app_commands.default_permissions(administrator=True)
    async def honeypot(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        channel: discord.TextChannel | None = None,
    ):
        def mut(d):
            h = d.setdefault("honeypot", {})
            if enabled is not None:
                h["enabled"] = enabled
            if channel is not None:
                h["channelId"] = str(channel.id)

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message("Honeypot updated.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
