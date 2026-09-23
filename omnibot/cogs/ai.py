"""AI commands — ask, chat, summary, moderate, security, imagine, memory."""
from __future__ import annotations

import io

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage
from omnibot.services import groq_client, ai_limits, image_gen


class AI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _reply_ai(self, interaction: discord.Interaction, prompt: str):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        await interaction.response.defer()
        ok, text = await groq_client.chat(interaction.guild.id, prompt)
        if not ok:
            return await interaction.followup.send(f"❌ {text}")
        if len(text) > 1900:
            text = text[:1900] + "…"
        await interaction.followup.send(text)

    @app_commands.command(name="ask", description="Ask OmniBot anything (uses AI quota)")
    @app_commands.describe(question="Your question")
    async def ask(self, interaction: discord.Interaction, question: str):
        await self._reply_ai(interaction, question)

    @app_commands.command(name="chat", description="Chat with OmniBot AI")
    @app_commands.describe(message="Message")
    async def chat(self, interaction: discord.Interaction, message: str):
        await self._reply_ai(interaction, message)

    @app_commands.command(name="aisummary", description="Summarise recent channel messages")
    async def aisummary(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Text channel only.", ephemeral=True)
        await interaction.response.defer()
        msgs = [m async for m in interaction.channel.history(limit=40)]
        lines = []
        for m in reversed(msgs):
            if m.author.bot or not m.content:
                continue
            lines.append(f"{m.author.display_name}: {m.content[:200]}")
        blob = "\n".join(lines[-30:]) or "(no messages)"
        ok, text = await groq_client.chat(
            interaction.guild.id,
            f"Summarise this Discord conversation concisely:\n\n{blob}",
        )
        await interaction.followup.send(f"❌ {text}" if not ok else text[:1900])

    @app_commands.command(name="aimoderate", description="AI analysis of a message for staff")
    @app_commands.describe(text="Message text to analyse")
    async def aimoderate(self, interaction: discord.Interaction, text: str):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ok, out = await groq_client.chat(
            interaction.guild.id,
            "Analyse this message for moderation risk. Give confidence and recommended action. "
            "Do not order punishments.\n\n" + text[:1500],
        )
        await interaction.followup.send(f"❌ {out}" if not ok else out[:1900], ephemeral=True)

    @app_commands.command(name="aisecurity", description="AI raid/security insights for staff")
    async def aisecurity(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        if not interaction.user.guild_permissions.administrator:  # type: ignore
            return await interaction.response.send_message("Administrator permission required.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        g = interaction.guild
        ok, out = await groq_client.chat(
            g.id,
            f"Security briefing for Discord server '{g.name}' with ~{g.member_count} members. "
            "Suggest monitoring practices. Do not claim live raid data you don't have.",
        )
        await interaction.followup.send(f"❌ {out}" if not ok else out[:1900], ephemeral=True)

    @app_commands.command(name="imagine", description="Generate an image (uses AI quota)")
    @app_commands.describe(prompt="What to generate")
    async def imagine(self, interaction: discord.Interaction, prompt: str):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        await interaction.response.defer()
        ok, result = await image_gen.generate(interaction.guild.id, prompt)
        if not ok:
            return await interaction.followup.send(f"❌ {result}")
        file = discord.File(io.BytesIO(result), filename="omnibot.png")  # type: ignore
        await interaction.followup.send(f"🎨 **{prompt[:100]}**", file=file)

    @app_commands.command(name="clearmemory", description="Clear your AI conversation memory in this server")
    async def clearmemory(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)

        def mut(data):
            mem = data.setdefault("memory", {})
            mem.pop(str(interaction.user.id), None)

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message("Memory cleared.", ephemeral=True)

    @commands.command(name="ask")
    async def ask_prefix(self, ctx: commands.Context, *, question: str):
        if not ctx.guild:
            return
        async with ctx.typing():
            ok, text = await groq_client.chat(ctx.guild.id, question)
        await ctx.reply(f"❌ {text}" if not ok else text[:1900], mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(AI(bot))
