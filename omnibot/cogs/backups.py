"""Lightweight config backup/export."""
from __future__ import annotations

import json

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


class Backups(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    backup = app_commands.Group(name="backup", description="Server config backup")

    @backup.command(name="export", description="Export OmniBot settings JSON")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def export(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)
        # strip large runtime records optionally keep structure
        payload = json.dumps(data, indent=2, default=str)[:1900]
        await interaction.response.send_message(f"```json\n{payload}\n```", ephemeral=True)

    @backup.command(name="snapshot", description="Save a named settings snapshot")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def snapshot(self, interaction: discord.Interaction, name: str):
        data = storage.load_guild(interaction.guild.id)

        def mut(d):
            snaps = d.setdefault("snapshots", {})
            snaps[name[:40]] = {
                k: data.get(k)
                for k in (
                    "dashboard", "persona", "automod", "welcomeSettings", "goodbyeSettings",
                    "deadChat", "appeals", "levelSettings", "autorole", "logging",
                )
            }

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Snapshot `{name}` saved.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Backups(bot))
