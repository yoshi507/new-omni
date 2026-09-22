"""Giveaways — create, end, reroll."""
from __future__ import annotations

import asyncio
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


class Giveaways(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    giveaway = app_commands.Group(name="giveaway", description="Server giveaways")

    @giveaway.command(name="start", description="Start a giveaway")
    @app_commands.describe(prize="Prize", minutes="Duration in minutes", winners="Number of winners")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def start(
        self,
        interaction: discord.Interaction,
        prize: str,
        minutes: app_commands.Range[int, 1, 10080] = 60,
        winners: app_commands.Range[int, 1, 20] = 1,
    ):
        ends = time.time() + minutes * 60
        emb = discord.Embed(
            title="🎉 Giveaway",
            description=f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** <t:{int(ends)}:R>\nReact with 🎉 to enter!",
            color=0x5B6CFF,
        )
        await interaction.response.send_message(embed=emb)
        msg = await interaction.original_response()
        await msg.add_reaction("🎉")

        def mut(d):
            d.setdefault("giveaways", {})[str(msg.id)] = {
                "prize": prize,
                "winners": winners,
                "ends": ends,
                "channelId": str(interaction.channel_id),
                "messageId": str(msg.id),
                "hostId": str(interaction.user.id),
            }

        storage.update_guild(interaction.guild.id, mut)
        await asyncio.sleep(minutes * 60)
        await self._end(interaction.guild.id, str(msg.id))

    async def _end(self, guild_id: int, message_id: str):
        data = storage.load_guild(guild_id)
        g = (data.get("giveaways") or {}).get(message_id)
        if not g or g.get("ended"):
            return
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        ch = guild.get_channel(int(g["channelId"]))
        if not isinstance(ch, discord.TextChannel):
            return
        try:
            msg = await ch.fetch_message(int(message_id))
        except Exception:
            return
        users = []
        for reaction in msg.reactions:
            if str(reaction.emoji) == "🎉":
                async for u in reaction.users():
                    if not u.bot:
                        users.append(u)
        winners_n = min(int(g.get("winners") or 1), len(users)) if users else 0
        picked = random.sample(users, winners_n) if winners_n else []
        text = (
            f"🎉 Giveaway ended for **{g['prize']}**!\nWinners: {', '.join(m.mention for m in picked)}"
            if picked
            else f"🎉 Giveaway ended for **{g['prize']}** — no valid entries."
        )
        await ch.send(text)

        def mut(d):
            if message_id in (d.get("giveaways") or {}):
                d["giveaways"][message_id]["ended"] = True
                d["giveaways"][message_id]["winnerIds"] = [str(m.id) for m in picked]

        storage.update_guild(guild_id, mut)

    @giveaway.command(name="reroll", description="Reroll winners for a giveaway message")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reroll(self, interaction: discord.Interaction, message_id: str):
        data = storage.load_guild(interaction.guild.id)
        g = (data.get("giveaways") or {}).get(message_id)
        if not g:
            return await interaction.response.send_message("Giveaway not found.", ephemeral=True)
        ch = interaction.guild.get_channel(int(g["channelId"]))
        msg = await ch.fetch_message(int(message_id))
        users = []
        for reaction in msg.reactions:
            if str(reaction.emoji) == "🎉":
                async for u in reaction.users():
                    if not u.bot:
                        users.append(u)
        if not users:
            return await interaction.response.send_message("No entries.", ephemeral=True)
        winner = random.choice(users)
        await interaction.response.send_message(f"New winner: {winner.mention} for **{g['prize']}**")


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))
