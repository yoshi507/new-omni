"""Core utility commands + comprehensive help."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from omnibot.config import settings


class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _help_embed(self) -> discord.Embed:
        limit = settings.ai_daily_limit
        embed = discord.Embed(
            title="🤖 OmniBot Help",
            description=(
                "All-in-one Discord bot. Slash, prefix (`!`), and natural `omni …` invocation.\n"
                f"AI features share **{limit}/server/day**.\n"
                "Dashboard: configure everything visually."
            ),
            color=0x5B6CFF,
        )
        embed.add_field(
            name="🧠 AI",
            value="`/ask` `/chat` `/aisummary` `/aimoderate` `/aisecurity` `/imagine` `/clearmemory`",
            inline=False,
        )
        embed.add_field(
            name="🛡️ Moderation & security",
            value="`/ban` `/kick` `/timeout` `/warn` `/clear` `/lock` `/unlock` `/slowmode` `/automod` + anti-nuke/spam",
            inline=False,
        )
        embed.add_field(
            name="📋 Logging · 🎫 Tickets · 👮 Staff",
            value="`/logging set` · `/ticket open|claim|close` · `/staff note|notes|case`",
            inline=False,
        )
        embed.add_field(
            name="🎭 Roles · 🎉 Giveaways · 📢 Announce",
            value="`/roles …` · `/giveaway start|reroll` · `/announce send`",
            inline=False,
        )
        embed.add_field(
            name="🎵 Music · 🔊 Voice",
            value="`/music play|skip|stop|queue|pause|resume` · `/voice setup-join-to-create`",
            inline=False,
        )
        embed.add_field(
            name="💰 Economy · ⭐ Levels · 👤 Profile",
            value="`/daily` `/balance` `/shop` `/work` · `/level rank|leaderboard` · `/profile view|setbio|rep`",
            inline=False,
        )
        embed.add_field(
            name="🎮 Games · 🐾 Fun",
            value="`/game trivia|guess|hangman` · `/fun eightball|ship|joke|meme|cat|dog|rps|…`",
            inline=False,
        )
        embed.add_field(
            name="🧰 Utilities · 🔎 Search · 🌍 Translate",
            value="`/util weather|calc|remind|poll|…` · `/search wiki|urban|github|define` · `/translate`",
            inline=False,
        )
        embed.add_field(
            name="📊 Info · 🔬 Science · 💹 Finance",
            value="`/info user|server|role|bot` · `/science apod|iss` · `/finance crypto|fx`",
            inline=False,
        )
        embed.add_field(
            name="💡 Suggest · 🎂 Birthday · ⚙️ Auto · 💾 Backup",
            value="`/suggest submit` · `/birthday set` · `/auto trigger-add|custom-add` · `/backup export`",
            inline=False,
        )
        embed.add_field(
            name="🌐 Dashboard",
            value="`/dashboard` — full server control panel",
            inline=False,
        )
        embed.set_footer(text="OmniBot · Feature universe edition")
        return embed

    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Pong! `{round(self.bot.latency * 1000)}ms`", ephemeral=True
        )

    @commands.command(name="ping")
    async def ping_prefix(self, ctx: commands.Context):
        await ctx.reply(f"Pong! `{round(self.bot.latency * 1000)}ms`", mention_author=False)

    @app_commands.command(name="help", description="Show OmniBot commands")
    async def help_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._help_embed())

    @commands.command(name="help")
    async def help_prefix(self, ctx: commands.Context):
        await ctx.reply(embed=self._help_embed(), mention_author=False)

    @app_commands.command(name="dashboard", description="Open the OmniBot dashboard")
    async def dashboard(self, interaction: discord.Interaction):
        url = settings.public_base_url.rstrip("/") or "https://omnibot.wisp.uno"
        embed = discord.Embed(
            title="OmniBot Dashboard",
            description=f"Manage your server at:\n**{url}**",
            color=0x5B6CFF,
        )
        await interaction.response.send_message(embeds=[embed])

    @commands.command(name="dashboard")
    async def dashboard_prefix(self, ctx: commands.Context):
        url = settings.public_base_url.rstrip("/") or "https://omnibot.wisp.uno"
        await ctx.reply(f"Dashboard: {url}", mention_author=False)

    @app_commands.command(name="terms", description="OmniBot Terms of Service link")
    async def terms(self, interaction: discord.Interaction):
        url = settings.public_base_url.rstrip("/") + "/tos"
        await interaction.response.send_message(f"Terms of Service: {url}", ephemeral=True)

    @app_commands.command(name="privacy", description="OmniBot Privacy Policy link")
    async def privacy(self, interaction: discord.Interaction):
        url = settings.public_base_url.rstrip("/") + "/privacy-policy"
        await interaction.response.send_message(f"Privacy Policy: {url}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
