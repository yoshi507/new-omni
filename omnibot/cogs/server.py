"""Welcome, goodbye, autorole, leveling, deadchat, logging setup commands."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


class Server(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="welcome", description="Configure welcome messages")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(enabled="Enable", channel="Channel", message="Message with {user} {server}")
    async def welcome(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        channel: discord.TextChannel | None = None,
        message: str | None = None,
    ):
        def mut(d):
            w = d.setdefault("welcomeSettings", {})
            if enabled is not None:
                w["enabled"] = enabled
            if channel is not None:
                w["channelId"] = str(channel.id)
            if message is not None:
                w["message"] = message[:1500]

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Welcome settings updated.", ephemeral=True)

    @app_commands.command(name="goodbye", description="Configure goodbye messages")
    @app_commands.default_permissions(administrator=True)
    async def goodbye(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        channel: discord.TextChannel | None = None,
        message: str | None = None,
    ):
        def mut(d):
            w = d.setdefault("goodbyeSettings", {})
            if enabled is not None:
                w["enabled"] = enabled
            if channel is not None:
                w["channelId"] = str(channel.id)
            if message is not None:
                w["message"] = message[:1500]

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Goodbye settings updated.", ephemeral=True)

    @app_commands.command(name="autorole", description="Set autorole for new members")
    @app_commands.default_permissions(administrator=True)
    async def autorole(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        role: discord.Role | None = None,
    ):
        def mut(d):
            a = d.setdefault("autorole", {})
            if enabled is not None:
                a["enabled"] = enabled
            if role is not None:
                a["roleId"] = str(role.id)

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Autorole updated.", ephemeral=True)

    @app_commands.command(name="deadchat", description="Configure Dead Chat Reviver")
    @app_commands.default_permissions(administrator=True)
    async def deadchat(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        minutes: app_commands.Range[int, 5, 1440] | None = None,
        channel: discord.TextChannel | None = None,
    ):
        def mut(d):
            dc = d.setdefault("deadChat", {})
            if enabled is not None:
                dc["enabled"] = enabled
            if minutes is not None:
                dc["minutes"] = minutes
            if channel is not None:
                dc["channelId"] = str(channel.id)

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Dead Chat settings updated.", ephemeral=True)

    @app_commands.command(name="logging", description="Set mod/log channel")
    @app_commands.default_permissions(administrator=True)
    async def logging_cmd(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        channel: discord.TextChannel | None = None,
    ):
        def mut(d):
            lg = d.setdefault("logging", {})
            if enabled is not None:
                lg["enabled"] = enabled
            if channel is not None:
                lg["channelId"] = str(channel.id)
                d.setdefault("settings", {})["modLogChannel"] = str(channel.id)

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Logging updated.", ephemeral=True)

    @app_commands.command(name="rank", description="Show your level")
    async def rank(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user  # type: ignore
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        lv = (data.get("levels") or {}).get(str(member.id), {"xp": 0, "level": 0})
        await interaction.response.send_message(
            f"**{member.display_name}** — Level **{lv.get('level', 0)}** · XP **{lv.get('xp', 0)}**"
        )

    @app_commands.command(name="leaderboard", description="XP leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        levels = data.get("levels") or {}
        ranked = sorted(
            levels.items(),
            key=lambda x: (int(x[1].get("level") or 0), int(x[1].get("xp") or 0)),
            reverse=True,
        )[:10]
        if not ranked:
            return await interaction.response.send_message("No rankings yet.")
        lines = []
        for i, (uid, v) in enumerate(ranked, 1):
            lines.append(f"{i}. <@{uid}> — Lv {v.get('level', 0)} ({v.get('xp', 0)} XP)")
        await interaction.response.send_message("**Leaderboard**\n" + "\n".join(lines))

    @app_commands.command(name="levelsettings", description="Toggle leveling")
    @app_commands.default_permissions(administrator=True)
    async def levelsettings(self, interaction: discord.Interaction, enabled: bool):
        def mut(d):
            d.setdefault("levelSettings", {})["enabled"] = enabled

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(f"Leveling {'on' if enabled else 'off'}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Server(bot))
