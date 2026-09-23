"""Keyword triggers, scheduled messages, custom commands."""
from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


class Automation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    auto = app_commands.Group(name="auto", description="Automations & custom commands")

    @auto.command(name="trigger-add", description="Add keyword → response trigger")
    @app_commands.checks.has_permissions(administrator=True)
    async def trigger_add(self, interaction: discord.Interaction, keyword: str, response: str):
        def mut(d):
            triggers = d.setdefault("triggers", {})
            triggers[keyword.lower()] = response[:1500]

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Trigger added for `{keyword}`.", ephemeral=True)

    @auto.command(name="trigger-remove", description="Remove a keyword trigger")
    @app_commands.checks.has_permissions(administrator=True)
    async def trigger_remove(self, interaction: discord.Interaction, keyword: str):
        def mut(d):
            (d.get("triggers") or {}).pop(keyword.lower(), None)

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message("Removed.", ephemeral=True)

    @auto.command(name="trigger-list", description="List keyword triggers")
    @app_commands.checks.has_permissions(administrator=True)
    async def trigger_list(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)
        triggers = data.get("triggers") or {}
        if not triggers:
            return await interaction.response.send_message("No triggers.", ephemeral=True)
        lines = [f"`{k}` → {v[:80]}" for k, v in list(triggers.items())[:30]]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @auto.command(name="custom-add", description="Add a custom prefix command")
    @app_commands.checks.has_permissions(administrator=True)
    async def custom_add(self, interaction: discord.Interaction, name: str, response: str):
        name = name.lower().strip().replace(" ", "")

        def mut(d):
            d.setdefault("customCommands", {})[name] = response[:1500]

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Custom command `!{name}` added.", ephemeral=True)

    @auto.command(name="custom-remove", description="Remove custom command")
    @app_commands.checks.has_permissions(administrator=True)
    async def custom_remove(self, interaction: discord.Interaction, name: str):
        def mut(d):
            (d.get("customCommands") or {}).pop(name.lower(), None)

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message("Removed.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not message.content:
            return
        data = storage.load_guild(message.guild.id)
        # keyword triggers
        triggers = data.get("triggers") or {}
        content_l = message.content.lower()
        for key, resp in triggers.items():
            if key and key in content_l:
                try:
                    await message.channel.send(resp)
                except Exception:
                    pass
                break
        # custom prefix commands
        prefix = (data.get("commandSettings") or {}).get("prefix") or "!"
        if message.content.startswith(prefix):
            name = message.content[len(prefix):].split()[0].lower()
            custom = (data.get("customCommands") or {}).get(name)
            if custom:
                try:
                    await message.channel.send(custom)
                except Exception:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Automation(bot))
