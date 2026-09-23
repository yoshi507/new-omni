"""Ticket system — panel buttons, open, claim, close."""
from __future__ import annotations

import time
import uuid

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage

TICKET_KINDS = [
    ("support", "Support", "Need help with something"),
    ("report", "Report", "Report a user or issue"),
    ("partnership", "Partnership", "Partnership inquiry"),
    ("staff", "Staff application", "Apply for staff"),
    ("bug", "Bug report", "Report a bug"),
    ("other", "Other", "Something else"),
]


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    ticket = app_commands.Group(name="ticket", description="Support tickets")

    @ticket.command(name="setup", description="Configure ticket category (+ optional log channel)")
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
        await interaction.response.send_message(
            f"Tickets configured → category **{category.name}**.\n"
            f"Next: run `/ticket panel` in the channel where members should open tickets.",
            ephemeral=True,
        )

    @ticket.command(name="panel", description="Post a ticket panel with buttons (recommended)")
    @app_commands.describe(
        channel="Where to post the panel (defaults to this channel)",
        title="Panel title",
        description="Panel description",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        title: str = "Support Tickets",
        description: str = (
            "Click a button below to open a private ticket with staff.\n"
            "Please only open a ticket if you need help."
        ),
    ):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        data = storage.load_guild(interaction.guild.id)
        tcfg = data.get("tickets") or {}
        if not tcfg.get("categoryId"):
            return await interaction.response.send_message(
                "Run `/ticket setup` first to set a ticket category.", ephemeral=True
            )

        dest = channel or interaction.channel
        if not isinstance(dest, discord.TextChannel):
            return await interaction.response.send_message("Need a text channel.", ephemeral=True)

        view = discord.ui.View(timeout=None)
        for value, label, _hint in TICKET_KINDS[:5]:  # Discord max 5 buttons per row; one row
            view.add_item(
                discord.ui.Button(
                    label=label,
                    style=discord.ButtonStyle.primary,
                    custom_id=f"omnibot:ticket:{value}",
                )
            )
        # second row for "other"
        view.add_item(
            discord.ui.Button(
                label="Other",
                style=discord.ButtonStyle.secondary,
                custom_id="omnibot:ticket:other",
                row=1,
            )
        )

        emb = discord.Embed(title=title[:256], description=description[:4000], color=0x5B6CFF)
        emb.set_footer(text="OmniBot tickets · one click opens a private channel")
        msg = await dest.send(embed=emb, view=view)

        def mut(d):
            t = d.setdefault("tickets", {})
            t["enabled"] = True
            t["panelChannelId"] = str(dest.id)
            t["panelMessageId"] = str(msg.id)

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Ticket panel posted in {dest.mention}.", ephemeral=True)

    async def _create_ticket(
        self,
        interaction: discord.Interaction,
        kind: str,
        subject: str,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Guild only.", ephemeral=True)

        data = storage.load_guild(interaction.guild.id)
        tcfg = data.get("tickets") or {}
        if not tcfg.get("enabled") or not tcfg.get("categoryId"):
            return await interaction.response.send_message(
                "Tickets are not set up. An admin must run `/ticket setup`.", ephemeral=True
            )

        # One open ticket per user
        records = data.get("ticketRecords") or {}
        for rec in records.values():
            if (
                str(rec.get("userId")) == str(interaction.user.id)
                and rec.get("status") == "open"
            ):
                ch = interaction.guild.get_channel(int(rec.get("channelId") or 0))
                if ch:
                    return await interaction.response.send_message(
                        f"You already have an open ticket: {ch.mention}", ephemeral=True
                    )

        cat = interaction.guild.get_channel(int(tcfg["categoryId"]))
        if not isinstance(cat, discord.CategoryChannel):
            return await interaction.response.send_message("Ticket category missing.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        tid = str(uuid.uuid4())[:6]
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True, read_message_history=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }
        for role in interaction.guild.roles:
            if role.permissions.manage_messages and not role.is_default():
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        try:
            ch = await interaction.guild.create_text_channel(
                name=f"ticket-{kind}-{tid}",
                category=cat,
                overwrites=overwrites,
                topic=f"{kind}: {subject[:100]} | opener:{interaction.user.id}",
                reason=f"Ticket by {interaction.user}",
            )
        except Exception as e:
            return await interaction.followup.send(f"Could not create ticket: {e}", ephemeral=True)

        def mut(d):
            d.setdefault("tickets", {})["enabled"] = True
            recs = d.setdefault("ticketRecords", {})
            recs[tid] = {
                "id": tid,
                "channelId": str(ch.id),
                "userId": str(interaction.user.id),
                "kind": kind,
                "subject": subject[:500],
                "status": "open",
                "createdAt": time.time(),
            }

        storage.update_guild(interaction.guild.id, mut)

        close_view = discord.ui.View(timeout=None)
        close_view.add_item(
            discord.ui.Button(
                label="Close ticket",
                style=discord.ButtonStyle.danger,
                custom_id="omnibot:ticket:close",
            )
        )

        emb = discord.Embed(
            title=f"Ticket {tid}",
            description=f"**Type:** {kind}\n**Subject:** {subject[:500]}",
            color=0x5B6CFF,
        )
        emb.set_footer(text="Staff: claim with /ticket claim · close with the button or /ticket close")
        await ch.send(
            content=f"{interaction.user.mention} — staff will be with you shortly.",
            embed=emb,
            view=close_view,
        )

        log_id = tcfg.get("logChannelId")
        if log_id:
            log_ch = interaction.guild.get_channel(int(log_id))
            if isinstance(log_ch, discord.TextChannel):
                try:
                    await log_ch.send(
                        f"🎫 Ticket **{tid}** ({kind}) opened by {interaction.user.mention} → {ch.mention}"
                    )
                except Exception:
                    pass

        await interaction.followup.send(f"Ticket created: {ch.mention}", ephemeral=True)

    @ticket.command(name="open", description="Open a ticket via command (panel is preferred)")
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
    async def open_ticket(
        self, interaction: discord.Interaction, subject: str, kind: app_commands.Choice[str]
    ):
        await self._create_ticket(interaction, kind.value, subject)

    @ticket.command(name="claim", description="Claim this ticket (staff)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def claim(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Claimed by {interaction.user.mention}.")

    @ticket.command(name="close", description="Close this ticket")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def close(self, interaction: discord.Interaction):
        await self._close_ticket(interaction)

    async def _close_ticket(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel) or not interaction.guild:
            if not interaction.response.is_done():
                return await interaction.response.send_message("Use in a ticket channel.", ephemeral=True)
            return

        data = storage.load_guild(interaction.guild.id)
        recs = data.get("ticketRecords") or {}
        tid = None
        for k, v in recs.items():
            if str(v.get("channelId")) == str(interaction.channel.id):
                tid = k
                break

        if not interaction.response.is_done():
            await interaction.response.send_message("Closing ticket in 3 seconds…")
        else:
            await interaction.followup.send("Closing ticket in 3 seconds…")

        if tid:

            def mut(d):
                r = (d.get("ticketRecords") or {}).get(tid)
                if r:
                    r["status"] = "closed"

            storage.update_guild(interaction.guild.id, mut)

        import asyncio

        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"Closed by {interaction.user}")
        except Exception as e:
            try:
                await interaction.followup.send(f"Could not delete: {e}")
            except Exception:
                pass

    @ticket.command(name="add", description="Add a user to this ticket")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def add_user(self, interaction: discord.Interaction, member: discord.Member):
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Ticket channel only.", ephemeral=True)
        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True)
        await interaction.response.send_message(f"Added {member.mention}.")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        cid = (interaction.data or {}).get("custom_id") or ""
        if not cid.startswith("omnibot:ticket:"):
            return
        action = cid.removeprefix("omnibot:ticket:")

        if action == "close":
            # Allow opener or staff
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                return
            data = storage.load_guild(interaction.guild.id)
            recs = data.get("ticketRecords") or {}
            is_opener = False
            for v in recs.values():
                if str(v.get("channelId")) == str(getattr(interaction.channel, "id", "")):
                    if str(v.get("userId")) == str(interaction.user.id):
                        is_opener = True
                    break
            if not (
                is_opener
                or interaction.user.guild_permissions.manage_messages
                or interaction.user.guild_permissions.administrator
            ):
                return await interaction.response.send_message(
                    "Only the ticket opener or staff can close this.", ephemeral=True
                )
            await self._close_ticket(interaction)
            return

        # Open ticket from panel button
        kind = action
        labels = {v: lab for v, lab, _ in TICKET_KINDS}
        subject = f"Opened via panel · {labels.get(kind, kind)}"
        await self._create_ticket(interaction, kind, subject)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
