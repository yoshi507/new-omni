"""Simple giveaways."""
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

    giveaway = app_commands.Group(name="giveaway", description="Giveaways")

    @giveaway.command(name="start", description="Start a giveaway")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(prize="Prize", minutes="Duration in minutes", winners="Number of winners")
    async def start(
        self,
        interaction: discord.Interaction,
        prize: str,
        minutes: app_commands.Range[int, 1, 10080] = 60,
        winners: app_commands.Range[int, 1, 20] = 1,
    ):
        emb = discord.Embed(
            title="🎉 Giveaway",
            description=f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** <t:{int(time.time()) + minutes * 60}:R>\n\nReact with 🎉 to enter!",
            color=0x5B6CFF,
        )
        await interaction.response.send_message(embed=emb)
        msg = await interaction.original_response()
        await msg.add_reaction("🎉")

        def mut(d):
            d.setdefault("giveaways", {})[str(msg.id)] = {
                "channelId": str(interaction.channel.id),
                "prize": prize,
                "winners": winners,
                "endsAt": time.time() + minutes * 60,
            }

        storage.update_guild(interaction.guild.id, mut)

        async def end_later():
            await asyncio.sleep(minutes * 60)
            try:
                channel = interaction.channel
                if not isinstance(channel, discord.TextChannel):
                    return
                m = await channel.fetch_message(msg.id)
                users = []
                for r in m.reactions:
                    if str(r.emoji) == "🎉":
                        async for u in r.users():
                            if not u.bot:
                                users.append(u)
                if not users:
                    await channel.send("Giveaway ended — no valid entries.")
                    return
                picked = random.sample(users, min(winners, len(users)))
                names = ", ".join(u.mention for u in picked)
                await channel.send(f"🎉 Giveaway ended! Prize: **{prize}**\nWinner(s): {names}")
            except Exception:
                pass
            finally:

                def clear(d):
                    (d.get("giveaways") or {}).pop(str(msg.id), None)

                storage.update_guild(interaction.guild.id, clear)

        asyncio.create_task(end_later())

    @giveaway.command(name="end", description="Force-end a giveaway by message ID")
    @app_commands.checks.has_permissions(administrator=True)
    async def end(self, interaction: discord.Interaction, message_id: str):
        def mut(d):
            (d.get("giveaways") or {}).pop(str(message_id), None)

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message("Giveaway record cleared.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))
