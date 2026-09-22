"""Information commands — user, server, role, channel, avatar, botinfo."""
from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands


class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    info = app_commands.Group(name="info", description="Lookup information")

    @info.command(name="user", description="User information")
    async def user(self, interaction: discord.Interaction, member: discord.Member | None = None):
        m = member or interaction.user
        if not isinstance(m, discord.Member):
            m = interaction.guild.get_member(m.id) if interaction.guild else None
        if not m:
            return await interaction.response.send_message("User not found in this server.", ephemeral=True)
        emb = discord.Embed(title=str(m), color=m.color or 0x5B6CFF)
        emb.set_thumbnail(url=m.display_avatar.url)
        emb.add_field(name="ID", value=str(m.id))
        emb.add_field(name="Joined", value=discord.utils.format_dt(m.joined_at, "R") if m.joined_at else "—")
        emb.add_field(name="Created", value=discord.utils.format_dt(m.created_at, "R"))
        roles = [r.mention for r in m.roles[1:][:15]]
        emb.add_field(name="Roles", value=", ".join(roles) or "None", inline=False)
        await interaction.response.send_message(embed=emb)

    @info.command(name="server", description="Server information")
    async def server(self, interaction: discord.Interaction):
        g = interaction.guild
        if not g:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        emb = discord.Embed(title=g.name, color=0x5B6CFF)
        if g.icon:
            emb.set_thumbnail(url=g.icon.url)
        emb.add_field(name="Members", value=str(g.member_count))
        emb.add_field(name="Channels", value=str(len(g.channels)))
        emb.add_field(name="Roles", value=str(len(g.roles)))
        emb.add_field(name="Boosts", value=str(g.premium_subscription_count or 0))
        emb.add_field(name="Owner", value=str(g.owner))
        emb.add_field(name="Created", value=discord.utils.format_dt(g.created_at, "R"))
        await interaction.response.send_message(embed=emb)

    @info.command(name="role", description="Role information")
    async def role(self, interaction: discord.Interaction, role: discord.Role):
        emb = discord.Embed(title=role.name, color=role.color or 0x5B6CFF)
        emb.add_field(name="ID", value=str(role.id))
        emb.add_field(name="Members", value=str(len(role.members)))
        emb.add_field(name="Position", value=str(role.position))
        emb.add_field(name="Mentionable", value=str(role.mentionable))
        await interaction.response.send_message(embed=emb)

    @info.command(name="channel", description="Channel information")
    async def channel_info(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        ch = channel or interaction.channel
        emb = discord.Embed(title=getattr(ch, "name", "channel"), color=0x5B6CFF)
        emb.add_field(name="ID", value=str(ch.id))
        emb.add_field(name="Type", value=str(ch.type))
        if isinstance(ch, discord.TextChannel):
            emb.add_field(name="Topic", value=(ch.topic or "—")[:200], inline=False)
        await interaction.response.send_message(embed=emb)

    @info.command(name="avatar", description="Show avatar")
    async def avatar(self, interaction: discord.Interaction, member: discord.User | None = None):
        u = member or interaction.user
        emb = discord.Embed(title=f"{u}'s avatar", color=0x5B6CFF)
        emb.set_image(url=u.display_avatar.url)
        await interaction.response.send_message(embed=emb)

    @info.command(name="banner", description="Show user banner if any")
    async def banner(self, interaction: discord.Interaction, member: discord.User | None = None):
        u = member or interaction.user
        user = await self.bot.fetch_user(u.id)
        if not user.banner:
            return await interaction.response.send_message("No banner.", ephemeral=True)
        emb = discord.Embed(title=f"{user}'s banner", color=0x5B6CFF)
        emb.set_image(url=user.banner.url)
        await interaction.response.send_message(embed=emb)

    @info.command(name="bot", description="Bot statistics")
    async def botinfo(self, interaction: discord.Interaction):
        emb = discord.Embed(title="OmniBot", color=0x5B6CFF)
        emb.add_field(name="Guilds", value=str(len(self.bot.guilds)))
        emb.add_field(name="Users", value=str(sum(g.member_count or 0 for g in self.bot.guilds)))
        emb.add_field(name="Latency", value=f"{round(self.bot.latency*1000)}ms")
        emb.add_field(name="Commands", value=str(len(list(self.bot.tree.walk_commands()))))
        await interaction.response.send_message(embed=emb)

    @info.command(name="permissions", description="Check member permissions in this channel")
    async def permissions(self, interaction: discord.Interaction, member: discord.Member | None = None):
        m = member or interaction.user
        if not isinstance(m, discord.Member):
            return await interaction.response.send_message("Member required.", ephemeral=True)
        perms = interaction.channel.permissions_for(m)
        enabled = [name for name, val in perms if val][:25]
        await interaction.response.send_message(", ".join(f"`{p}`" for p in enabled) or "None")


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
