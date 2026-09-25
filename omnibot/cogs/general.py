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
                "All-in-one Discord bot. **Slash**, **prefix**, and natural `omni …`.\n"
                f"AI quota: **{limit}/server/day**. Dashboard for deep config."
            ),
            color=0x5B6CFF,
        )
        embed.add_field(
            name="🧠 AI · 🎵 Music · 🔊 Voice",
            value="`/ask` `/chat` `/imagine` · `/music play|skip|stop|queue` · `/voice join|say|talk` · join-to-create",
            inline=False,
        )
        embed.add_field(
            name="🛡️ Moderation · Security · Logging",
            value=(
                "`/kick` `/ban` `/timeout` `/warn` `/purge` `/lock` `/slowmode` · "
                "`/antinuke config|status|unlockdown` · `/logging set` · honeypot"
            ),
            inline=False,
        )
        embed.add_field(
            name="🎫 Tickets · 📋 Forms · 📊 Polls · 💡 Suggest",
            value="`/ticket setup|panel|button` · `/form create|submit` · `/poll create` · `/suggest setup|submit`",
            inline=False,
        )
        embed.add_field(
            name="⭐ Engagement",
            value=(
                "Starboard · invites · verify · counting · word-chain · AFK · "
                "welcome/goodbye · booster msgs · `/boostrole set` · `/autoname setup` · "
                "`/birthday set` · `/bump setup` · `/social setup|add|notify`"
            ),
            inline=False,
        )
        embed.add_field(
            name="🎭 Roles · 🎨 Colour · 🎉 Giveaways",
            value="`/roles autorole|reaction|give` · `/color set|clear` · `/giveaway start`",
            inline=False,
        )
        embed.add_field(
            name="📈 Stats · 📝 Docs · 💬 Quotes · 📢 Announce · 🧩 Embed",
            value=(
                "`/stats server|analytics` · `/docs set|get|list` · `/quote make|save|random` · "
                "`/announce send` · `/embed send`"
            ),
            inline=False,
        )
        embed.add_field(
            name="💰 Economy · 🎰 Casino · 🎮 Games",
            value=(
                "`/balance` `/daily` `/work` `/slots` `/coinflip` · "
                "`/casino blackjack|roulette` · `/game trivia|hangman|tictactoe`"
            ),
            inline=False,
        )
        embed.add_field(
            name="🌐 Translate · 🎭 RP · 💞 Relationships",
            value=(
                "`/translate` `/tr` `/detectlang` · "
                "`/rp do|list|say` · "
                "`/relationship ship|marry|divorce|status|leaderboard`"
            ),
            inline=False,
        )
        embed.add_field(
            name="⚙️ Custom commands · Dashboard",
            value="`/auto custom-add|trigger-add` · `/dashboard` — toggles, channels, AI personality, tickets…",
            inline=False,
        )
        embed.set_footer(text="OmniBot · commands + dashboard")
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
