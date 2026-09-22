"""Temporary voice channels (join-to-create)."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


class VoiceExtra(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.temp_channels: set[int] = set()

    voice = app_commands.Group(name="voice", description="Voice utilities")

    @voice.command(name="setup-join-to-create", description="Set a lobby channel that creates temp voice rooms")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def setup_jtc(self, interaction: discord.Interaction, lobby: discord.VoiceChannel):
        def mut(d):
            d.setdefault("tempVoice", {})["lobbyChannelId"] = str(lobby.id)
            d["tempVoice"]["enabled"] = True

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Join-to-create lobby: {lobby.mention}", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        data = storage.load_guild(member.guild.id)
        tv = data.get("tempVoice") or {}
        if not tv.get("enabled") or not tv.get("lobbyChannelId"):
            return
        lobby_id = int(tv["lobbyChannelId"])
        if after.channel and after.channel.id == lobby_id:
            try:
                ch = await member.guild.create_voice_channel(
                    name=f"{member.display_name}'s room",
                    category=after.channel.category,
                    reason="Join-to-create",
                )
                self.temp_channels.add(ch.id)
                await member.move_to(ch)
            except Exception:
                pass
        if before.channel and before.channel.id in self.temp_channels:
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Temp voice empty")
                except Exception:
                    pass
                self.temp_channels.discard(before.channel.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceExtra(bot))
