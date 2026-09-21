"""Core utility commands."""
from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

from omnibot.config import settings
from omnibot.services import ai_limits


class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Pong! `{round(self.bot.latency * 1000)}ms`",
            ephemeral=True,
        )

    @commands.command(name="ping")
    async def ping_prefix(self, ctx: commands.Context):
        await ctx.reply(f"Pong! `{round(self.bot.latency * 1000)}ms`", mention_author=False)

    @app_commands.command(name="help", description="Show OmniBot commands and features")
    async def help_cmd(self, interaction: discord.Interaction):
        limit = settings.ai_daily_limit
        embed = discord.Embed(
            title="🤖 OmniBot Help",
            description=(
                "All-in-one Discord bot — moderation, AI, music, economy, appeals, and more.\n"
                f"AI features share **{limit} requests per server per day**.\n"
                "Staff-only commands require the matching Discord permission."
            ),
            color=0x5865F2,
        )
        embed.add_field(
            name="🧠 AI",
            value="`/ask` `/chat` `/aisummary` `/aimoderate` `/aisecurity` `/imagine` `/clearmemory`\nNatural: `omni explain …`",
            inline=False,
        )
        embed.add_field(
            name="🛡️ Moderation",
            value="`/ban` `/kick` `/timeout` `/warn` `/warnings` `/clear` `/lock` `/unlock` `/slowmode` `/automod`",
            inline=False,
        )
        embed.add_field(
            name="🎵 Music",
            value="`/music play|skip|stop|queue|pause|resume|volume`",
            inline=False,
        )
        embed.add_field(
            name="🎉 Fun & economy",
            value="`/coinflip` `/dice` `/rps` `/slots` `/trivia` `/daily` `/balance` `/shop` `/work`",
            inline=False,
        )
        embed.add_field(
            name="⚙️ Server",
            value="`/welcome` `/goodbye` `/autorole` `/deadchat` `/giveaway` `/reactionrole` `/dashboard`",
            inline=False,
        )
        embed.add_field(
            name="🎫 Appeals & more",
            value="`/appeal` `/appealsetup` `/quiz` `/advertise` `/partner` `/captcha` `/userphone`",
            inline=False,
        )
        embed.set_footer(text="Prefix + natural commands · AI limit resets daily")
        await interaction.response.send_message(embeds=[embed])

    @commands.command(name="help")
    async def help_prefix(self, ctx: commands.Context):
        await ctx.invoke(self.help_cmd)  # type: ignore

    @app_commands.command(name="dashboard", description="Open the OmniBot dashboard")
    async def dashboard(self, interaction: discord.Interaction):
        url = settings.public_base_url.rstrip("/") or "https://omnibot.wisp.uno"
        embed = discord.Embed(
            title="OmniBot Dashboard",
            description=f"Manage your server at:\n**{url}**",
            color=0x5865F2,
        )
        await interaction.response.send_message(embeds=[embed])

    @commands.command(name="dashboard")
    async def dashboard_prefix(self, ctx: commands.Context):
        url = settings.public_base_url.rstrip("/") or "https://omnibot.wisp.uno"
        await ctx.reply(f"Dashboard: {url}", mention_author=False)

    @app_commands.command(name="serverinfo", description="Server information")
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        if not g:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        embed = discord.Embed(title=g.name, color=0x5865F2)
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="Members", value=str(g.member_count))
        embed.add_field(name="Channels", value=str(len(g.channels)))
        embed.add_field(name="Roles", value=str(len(g.roles)))
        embed.add_field(name="ID", value=str(g.id))
        await interaction.response.send_message(embeds=[embed])

    @app_commands.command(name="userinfo", description="User information")
    @app_commands.describe(user="User to inspect")
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member | None = None):
        user = user or interaction.user  # type: ignore
        embed = discord.Embed(title=str(user), color=0x5865F2)
        if user.display_avatar:
            embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="ID", value=str(user.id))
        if isinstance(user, discord.Member) and user.joined_at:
            embed.add_field(name="Joined", value=discord.utils.format_dt(user.joined_at))
        await interaction.response.send_message(embeds=[embed])

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
