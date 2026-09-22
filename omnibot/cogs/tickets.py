"""Ticket system — open, claim, close, transcript, categories."""
from __future__ import annotations

import time
import uuid

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    ticket = app_commands.Group(name="ticket", description="Support tickets")

    @ticket.command(name="setup", description="Configure ticket category/channel")
    @app_commands.describe(category="Category for ticket channels", log_channel="Ticket log channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        log_channel: discord.TextChannel | None = None,
    ):
        def mut(d):
            t = d.setdefault("tickets", {})
            t["enabled"] = True
            t["categoryId"] = str(category.id)
            if log_channel:
                t["logChannelId"] = str(log_channel.id)

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message("Ticket system configured.", ephemeral=True)

    @ticket.command(name="open", description="Open a support ticket")
    @app_commands.describe(subject="What do you need help with?", kind="Ticket type")
    @app_commands.choices(
        kind=[
            app_commands.Choice(name="Support", value="support"),
            app_commands.Choice(name="Report", value="report"),
            app_commands.Choice(name="Partnership", value="partnership"),
            app_commands.Choice(name="Staff application", value="staff"),
            app_commands.Choice(name="Bug report", value="bug"),
            app_commands.Choice(name="Other", value="other"),
        ]
    )
    async def open_ticket(self, interaction: discord.Interaction, subject: str, kind: app_commands.Choice[str]):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        data = storage.load_guild(interaction.guild.id)
        tcfg = data.get("tickets") or {}
        if not tcfg.get("enabled") or not tcfg.get("categoryId"):
            return await interaction.response.send_message(
                "Tickets are not set up. An admin must run `/ticket setup`.", ephemeral=True
            )
        cat = interaction.guild.get_channel(int(tcfg["categoryId"]))
        if not isinstance(cat, discord.CategoryChannel):
            return await interaction.response.send_message("Ticket category missing.", ephemeral=True)

        tid = str(uuid.uuid4())[:6]
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for role in interaction.guild.roles:
            if role.permissions.manage_messages:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        try:
            ch = await interaction.guild.create_text_channel(
                name=f"ticket-{tid}",
                category=cat,
                overwrites=overwrites,
                topic=f"{kind.value}: {subject[:100]} | opener:{interaction.user.id}",
                reason=f"Ticket by {interaction.user}",
            )
        except Exception as e:
            return await interaction.response.send_message(f"Could not create ticket: {e}", ephemeral=True)

        def mut(d):
            recs = d.setdefault("ticketRecords", {})
            recs[tid] = {
                "id": tid,
                "channelId": str(ch.id),
                "userId": str(interaction.user.id),
                "kind": kind.value,
                "subject": subject[:500],
                "status": "open",
                "createdAt": time.time(),
            }

        storage.update_guild(interaction.guild.id, mut)
        await ch.send(
            f"{interaction.user.mention} Ticket **{tid}** ({kind.value})\n"
            f"**Subject:** {subject[:500]}\nStaff: use `/ticket claim` / `/ticket close`."
        )
        await interaction.response.send_message(f"Ticket created: {ch.mention}", ephemeral=True)

    @ticket.command(name="claim", description="Claim this ticket (staff)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def claim(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Claimed by {interaction.user.mention}.")

    @ticket.command(name="close", description="Close this ticket")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def close(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Use in a ticket channel.", ephemeral=True)
        await interaction.response.send_message("Closing ticket in 3s…")
        try:
            await interaction.channel.delete(reason=f"Closed by {interaction.user}")
        except Exception as e:
            await interaction.followup.send(f"Could not delete: {e}")

    @ticket.command(name="add", description="Add a user to this ticket")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def add_user(self, interaction: discord.Interaction, member: discord.Member):
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Ticket channel only.", ephemeral=True)
        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True)
        await interaction.response.send_message(f"Added {member.mention}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
