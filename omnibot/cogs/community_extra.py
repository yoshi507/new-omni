"""Suggestions, birthdays, announcements, levels, profiles."""
from __future__ import annotations

import time
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


class CommunityExtra(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    suggest = app_commands.Group(name="suggest", description="Suggestion box")

    @suggest.command(name="setup", description="Set suggestions channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def suggest_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        def mut(d):
            d.setdefault("suggestions", {})["channelId"] = str(channel.id)
            d["suggestions"]["enabled"] = True

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Suggestions → {channel.mention}", ephemeral=True)

    @suggest.command(name="submit", description="Submit a suggestion")
    async def suggest_submit(self, interaction: discord.Interaction, text: str):
        data = storage.load_guild(interaction.guild.id)
        ch_id = (data.get("suggestions") or {}).get("channelId")
        if not ch_id:
            return await interaction.response.send_message("Suggestions not set up.", ephemeral=True)
        ch = interaction.guild.get_channel(int(ch_id))
        emb = discord.Embed(title="💡 Suggestion", description=text[:2000], color=0x5B6CFF)
        emb.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        msg = await ch.send(embed=emb)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
        await interaction.response.send_message("Submitted!", ephemeral=True)

    bday = app_commands.Group(name="birthday", description="Birthday tracking")

    @bday.command(name="set", description="Set your birthday (MM-DD)")
    async def bday_set(self, interaction: discord.Interaction, month: app_commands.Range[int, 1, 12], day: app_commands.Range[int, 1, 31]):
        def mut(d):
            d.setdefault("birthdays", {})[str(interaction.user.id)] = f"{month:02d}-{day:02d}"

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Birthday set to **{month:02d}-{day:02d}**.", ephemeral=True)

    @bday.command(name="upcoming", description="List upcoming birthdays")
    async def bday_upcoming(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)
        bdays = data.get("birthdays") or {}
        if not bdays:
            return await interaction.response.send_message("No birthdays stored.")
        lines = [f"<@{uid}> — `{date}`" for uid, date in list(bdays.items())[:20]]
        await interaction.response.send_message("🎂\n" + "\n".join(lines))

    level = app_commands.Group(name="level", description="XP and ranks")

    @level.command(name="rank", description="Your level rank")
    async def rank(self, interaction: discord.Interaction, member: discord.Member | None = None):
        m = member or interaction.user
        data = storage.load_guild(interaction.guild.id)
        lv = (data.get("levels") or {}).get(str(m.id)) or {"xp": 0, "level": 0}
        await interaction.response.send_message(
            f"**{m.display_name}** — Level **{lv.get('level', 0)}** · XP **{lv.get('xp', 0)}**"
        )

    @level.command(name="leaderboard", description="Top XP")
    async def leaderboard(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)
        levels = data.get("levels") or {}
        ranked = sorted(levels.items(), key=lambda kv: (kv[1].get("level", 0), kv[1].get("xp", 0)), reverse=True)[:10]
        lines = [f"**{i}.** <@{uid}> — Lv {v.get('level', 0)} ({v.get('xp', 0)} XP)" for i, (uid, v) in enumerate(ranked, 1)]
        await interaction.response.send_message("\n".join(lines) or "No XP yet.")

    @level.command(name="toggle", description="Enable/disable leveling")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def level_toggle(self, interaction: discord.Interaction, enabled: bool):
        def mut(d):
            d.setdefault("levelSettings", {})["enabled"] = enabled

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Leveling **{'on' if enabled else 'off'}**.")

    announce = app_commands.Group(name="announce", description="Announcements")

    @announce.command(name="send", description="Send an announcement embed")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def announce_send(
        self,
        interaction: discord.Interaction,
        title: str,
        message: str,
        channel: discord.TextChannel | None = None,
    ):
        ch = channel or interaction.channel
        emb = discord.Embed(title=title[:256], description=message[:4000], color=0x5B6CFF)
        emb.set_footer(text=f"From {interaction.user}")
        await ch.send(embed=emb)
        await interaction.response.send_message("Announcement sent.", ephemeral=True)

    profile = app_commands.Group(name="profile", description="User profiles")

    @profile.command(name="setbio", description="Set your profile bio")
    async def setbio(self, interaction: discord.Interaction, bio: str):
        def mut(d):
            d.setdefault("profiles", {}).setdefault(str(interaction.user.id), {})["bio"] = bio[:300]

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message("Bio updated.", ephemeral=True)

    @profile.command(name="view", description="View a profile")
    async def view(self, interaction: discord.Interaction, member: discord.Member | None = None):
        m = member or interaction.user
        data = storage.load_guild(interaction.guild.id)
        p = (data.get("profiles") or {}).get(str(m.id)) or {}
        lv = (data.get("levels") or {}).get(str(m.id)) or {}
        emb = discord.Embed(title=f"{m.display_name}'s profile", color=0x5B6CFF)
        emb.set_thumbnail(url=m.display_avatar.url)
        emb.add_field(name="Bio", value=p.get("bio") or "No bio set.", inline=False)
        emb.add_field(name="Level", value=str(lv.get("level", 0)))
        emb.add_field(name="Rep", value=str(p.get("rep", 0)))
        await interaction.response.send_message(embed=emb)

    @profile.command(name="rep", description="Give reputation to a member")
    async def rep(self, interaction: discord.Interaction, member: discord.Member):
        if member.id == interaction.user.id:
            return await interaction.response.send_message("You can't rep yourself.", ephemeral=True)

        def mut(d):
            p = d.setdefault("profiles", {}).setdefault(str(member.id), {})
            p["rep"] = int(p.get("rep") or 0) + 1

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Gave +1 rep to {member.mention}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(CommunityExtra(bot))
