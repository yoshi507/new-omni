"""Staff notes, cases, applications."""
from __future__ import annotations

import time
import uuid

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


class Staff(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    staff = app_commands.Group(name="staff", description="Staff tools")

    @staff.command(name="note", description="Add a staff note about a user")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def note(self, interaction: discord.Interaction, member: discord.Member, text: str):
        nid = str(uuid.uuid4())[:8]

        def mut(d):
            notes = d.setdefault("staffNotes", {}).setdefault(str(member.id), [])
            notes.append({
                "id": nid,
                "text": text[:1000],
                "by": str(interaction.user.id),
                "at": time.time(),
            })

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Note `{nid}` added.", ephemeral=True)

    @staff.command(name="notes", description="View staff notes for a user")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def notes(self, interaction: discord.Interaction, member: discord.Member):
        data = storage.load_guild(interaction.guild.id)
        notes = (data.get("staffNotes") or {}).get(str(member.id)) or []
        if not notes:
            return await interaction.response.send_message("No notes.", ephemeral=True)
        lines = [f"`{n['id']}` <@{n['by']}>: {n['text']}" for n in notes[-15:]]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @staff.command(name="case", description="Create a moderation case number")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def case(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        cid = str(uuid.uuid4())[:6].upper()

        def mut(d):
            cases = d.setdefault("modCases", {})
            cases[cid] = {
                "userId": str(member.id),
                "reason": reason[:500],
                "modId": str(interaction.user.id),
                "at": time.time(),
            }

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Case **{cid}** created for {member.mention}: {reason[:200]}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Staff(bot))
