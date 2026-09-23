"""Ticket system — custom staff buttons, optional modal form, staff roles."""
from __future__ import annotations

import re
import time
import uuid

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage

# custom_id formats:
#   omnibot:ticket:btn:{button_id}   — open (instant or modal)
#   omnibot:ticket:close


def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", s.strip().lower())[:24]
    return s.strip("-") or "ticket"


def _ticket_cfg(guild_id: int) -> dict:
    return (storage.load_guild(guild_id).get("tickets") or {}).copy()


def _staff_overwrites(guild: discord.Guild, tcfg: dict) -> dict:
    """Permission overwrites for staff roles (or manage_messages fallback)."""
    overwrites: dict = {}
    role_ids = tcfg.get("staffRoleIds") or []
    if isinstance(role_ids, str):
        role_ids = [r.strip() for r in role_ids.split(",") if r.strip()]
    added = False
    for rid in role_ids:
        try:
            role = guild.get_role(int(rid))
        except (TypeError, ValueError):
            continue
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, attach_files=True
            )
            added = True
    if not added:
        for role in guild.roles:
            if role.permissions.manage_messages and not role.is_default():
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )
    return overwrites


def _is_staff(member: discord.Member, tcfg: dict) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    if member.guild_permissions.manage_messages:
        return True
    role_ids = {str(r) for r in (tcfg.get("staffRoleIds") or [])}
    if isinstance(tcfg.get("staffRoleIds"), str):
        role_ids = {r.strip() for r in tcfg["staffRoleIds"].split(",") if r.strip()}
    return any(str(r.id) in role_ids for r in member.roles)


class TicketFormModal(discord.ui.Modal):
    def __init__(self, cog: "Tickets", button_id: str, purpose: str, label: str):
        super().__init__(title=(label or "Open a ticket")[:45])
        self.cog = cog
        self.button_id = button_id
        self.purpose = purpose
        self.details = discord.ui.TextInput(
            label="What do you need?",
            style=discord.TextStyle.paragraph,
            placeholder="Describe your request…",
            required=True,
            max_length=1000,
        )
        self.add_item(self.details)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog._create_ticket(
            interaction,
            kind=self.purpose or self.button_id,
            subject=str(self.details.value),
        )


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    ticket = app_commands.Group(name="ticket", description="Support tickets")

    @ticket.command(name="setup", description="Configure ticket category, log channel, and staff role")
    @app_commands.describe(
        category="Category for ticket channels",
        log_channel="Optional ticket log channel",
        staff_role="Role that can see and manage tickets",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        log_channel: discord.TextChannel | None = None,
        staff_role: discord.Role | None = None,
    ):
        def mut(d):
            t = d.setdefault("tickets", {})
            t["enabled"] = True
            t["categoryId"] = str(category.id)
            if log_channel:
                t["logChannelId"] = str(log_channel.id)
            if staff_role:
                t["staffRoleIds"] = [str(staff_role.id)]

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        staff_txt = staff_role.mention if staff_role else "(any role with Manage Messages)"
        await interaction.response.send_message(
            f"Tickets configured.\n"
            f"• Category: **{category.name}**\n"
            f"• Staff role: {staff_txt}\n"
            f"• Next: `/ticket button add` then `/ticket panel`",
            ephemeral=True,
        )

    @ticket.command(name="staffrole", description="Add or clear a staff role for tickets")
    @app_commands.describe(role="Staff role (omit to clear all staff roles)", clear="Clear all staff roles")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def staffrole(
        self,
        interaction: discord.Interaction,
        role: discord.Role | None = None,
        clear: bool = False,
    ):
        def mut(d):
            t = d.setdefault("tickets", {})
            if clear or role is None:
                t["staffRoleIds"] = []
            else:
                ids = list(t.get("staffRoleIds") or [])
                if isinstance(ids, str):
                    ids = [x.strip() for x in ids.split(",") if x.strip()]
                sid = str(role.id)
                if sid not in ids:
                    ids.append(sid)
                t["staffRoleIds"] = ids

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        if clear or role is None:
            await interaction.response.send_message("Staff roles cleared.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Added staff role {role.mention}.",
                ephemeral=True,
            )

    # —— Custom buttons ——
    button = app_commands.Group(name="button", parent=ticket, description="Manage panel buttons")

    @button.command(name="add", description="Add a custom ticket panel button (staff only)")
    @app_commands.describe(
        label="Button text shown on the panel",
        purpose="Internal type / purpose (e.g. support, report, billing)",
        use_form="If true, clicking opens a form to describe the request",
        style="Button colour style",
    )
    @app_commands.choices(
        style=[
            app_commands.Choice(name="Blurple (primary)", value="primary"),
            app_commands.Choice(name="Grey (secondary)", value="secondary"),
            app_commands.Choice(name="Green (success)", value="success"),
            app_commands.Choice(name="Red (danger)", value="danger"),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def button_add(
        self,
        interaction: discord.Interaction,
        label: str,
        purpose: str = "support",
        use_form: bool = True,
        style: app_commands.Choice[str] | None = None,
    ):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        buttons = list((data.get("tickets") or {}).get("buttons") or [])
        if len(buttons) >= 10:
            return await interaction.response.send_message(
                "Max 10 buttons per panel (Discord limit).",
                ephemeral=True,
            )
        bid = _slug(purpose) + "-" + uuid.uuid4().hex[:4]
        style_val = (style.value if style else "primary")
        buttons.append(
            {
                "id": bid,
                "label": label[:80],
                "purpose": purpose[:40],
                "useForm": bool(use_form),
                "style": style_val,
            }
        )

        def mut(d):
            t = d.setdefault("tickets", {})
            t["buttons"] = buttons
            t["enabled"] = True

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        form_txt = "opens a form" if use_form else "opens ticket immediately"
        await interaction.response.send_message(
            f"Button **{label}** added (`{bid}`) — {form_txt}.\n"
            f"Run `/ticket panel` to post (or re-post) the panel.",
            ephemeral=True,
        )

    @button.command(name="remove", description="Remove a panel button by id or label")
    @app_commands.describe(button="Button id or exact label")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def button_remove(self, interaction: discord.Interaction, button: str):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        buttons = list((data.get("tickets") or {}).get("buttons") or [])
        target = button.strip().lower()
        new = [b for b in buttons if str(b.get("id", "")).lower() != target and str(b.get("label", "")).lower() != target]
        if len(new) == len(buttons):
            return await interaction.response.send_message("No matching button.", ephemeral=True)

        def mut(d):
            d.setdefault("tickets", {})["buttons"] = new

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Button removed. Re-run `/ticket panel` to update.", ephemeral=True)

    @button.command(name="list", description="List configured ticket buttons")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def button_list(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        buttons = (data.get("tickets") or {}).get("buttons") or []
        if not buttons:
            return await interaction.response.send_message(
                "No buttons yet. Add some with `/ticket button add`.",
                ephemeral=True,
            )
        lines = []
        for b in buttons:
            form = "form" if b.get("useForm") else "instant"
            lines.append(f"• **{b.get('label')}** (`{b.get('id')}`) · {b.get('purpose')} · {form}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @ticket.command(name="panel", description="Post the ticket panel using your custom buttons")
    @app_commands.describe(
        channel="Where to post (defaults to this channel)",
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
                "Run `/ticket setup` first.", ephemeral=True
            )
        buttons = tcfg.get("buttons") or []
        if not buttons:
            return await interaction.response.send_message(
                "No buttons configured. Add some with `/ticket button add` first.",
                ephemeral=True,
            )

        dest = channel or interaction.channel
        if not isinstance(dest, discord.TextChannel):
            return await interaction.response.send_message("Need a text channel.", ephemeral=True)

        style_map = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger,
        }
        view = discord.ui.View(timeout=None)
        for i, b in enumerate(buttons[:10]):
            view.add_item(
                discord.ui.Button(
                    label=str(b.get("label") or "Ticket")[:80],
                    style=style_map.get(str(b.get("style") or "primary"), discord.ButtonStyle.primary),
                    custom_id=f"omnibot:ticket:btn:{b.get('id')}",
                    row=i // 5,
                )
            )

        emb = discord.Embed(title=title[:256], description=description[:4000], color=0x5B6CFF)
        emb.set_footer(text="OmniBot tickets · configured by staff")
        msg = await dest.send(embed=emb, view=view)

        def mut(d):
            t = d.setdefault("tickets", {})
            t["enabled"] = True
            t["panelChannelId"] = str(dest.id)
            t["panelMessageId"] = str(msg.id)

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(
            f"Ticket panel posted in {dest.mention} with **{len(buttons)}** button(s).",
            ephemeral=True,
        )

    async def _create_ticket(
        self,
        interaction: discord.Interaction,
        kind: str,
        subject: str,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            if not interaction.response.is_done():
                return await interaction.response.send_message("Guild only.", ephemeral=True)
            return

        data = storage.load_guild(interaction.guild.id)
        tcfg = data.get("tickets") or {}
        if not tcfg.get("enabled") or not tcfg.get("categoryId"):
            msg = "Tickets are not set up. An admin must run `/ticket setup`."
            if interaction.response.is_done():
                return await interaction.followup.send(msg, ephemeral=True)
            return await interaction.response.send_message(msg, ephemeral=True)

        records = data.get("ticketRecords") or {}
        for rec in records.values():
            if str(rec.get("userId")) == str(interaction.user.id) and rec.get("status") == "open":
                ch = interaction.guild.get_channel(int(rec.get("channelId") or 0))
                if ch:
                    msg = f"You already have an open ticket: {ch.mention}"
                    if interaction.response.is_done():
                        return await interaction.followup.send(msg, ephemeral=True)
                    return await interaction.response.send_message(msg, ephemeral=True)

        cat = interaction.guild.get_channel(int(tcfg["categoryId"]))
        if not isinstance(cat, discord.CategoryChannel):
            msg = "Ticket category missing — re-run `/ticket setup`."
            if interaction.response.is_done():
                return await interaction.followup.send(msg, ephemeral=True)
            return await interaction.response.send_message(msg, ephemeral=True)

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        tid = str(uuid.uuid4())[:6]
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                attach_files=True,
                read_message_history=True,
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }
        overwrites.update(_staff_overwrites(interaction.guild, tcfg))

        try:
            ch = await interaction.guild.create_text_channel(
                name=f"ticket-{_slug(kind)}-{tid}",
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
        emb.set_footer(text="Staff: /ticket claim · close with the button or /ticket close")
        staff_ping = ""
        role_ids = tcfg.get("staffRoleIds") or []
        if role_ids:
            mentions = []
            for rid in role_ids:
                try:
                    mentions.append(f"<@&{int(rid)}>")
                except (TypeError, ValueError):
                    pass
            staff_ping = " ".join(mentions)
        await ch.send(
            content=f"{interaction.user.mention} {staff_ping}\nStaff will be with you shortly.".strip(),
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

    @ticket.command(name="open", description="Open a ticket (prefer the panel)")
    @app_commands.describe(subject="What do you need help with?", kind="Ticket type / purpose")
    async def open_ticket(self, interaction: discord.Interaction, subject: str, kind: str = "support"):
        await self._create_ticket(interaction, kind[:40], subject)

    @ticket.command(name="claim", description="Claim this ticket (staff)")
    async def claim(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        tcfg = _ticket_cfg(interaction.guild.id)
        if not _is_staff(interaction.user, tcfg):
            return await interaction.response.send_message("Staff only.", ephemeral=True)
        await interaction.response.send_message(f"Claimed by {interaction.user.mention}.")

    @ticket.command(name="close", description="Close this ticket")
    async def close(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        tcfg = _ticket_cfg(interaction.guild.id)
        data = storage.load_guild(interaction.guild.id)
        is_opener = False
        for v in (data.get("ticketRecords") or {}).values():
            if str(v.get("channelId")) == str(getattr(interaction.channel, "id", "")):
                if str(v.get("userId")) == str(interaction.user.id):
                    is_opener = True
                break
        if not (is_opener or _is_staff(interaction.user, tcfg)):
            return await interaction.response.send_message(
                "Only the ticket opener or staff can close this.", ephemeral=True
            )
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
    async def add_user(self, interaction: discord.Interaction, member: discord.Member):
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        tcfg = _ticket_cfg(interaction.guild.id)
        if not _is_staff(interaction.user, tcfg):
            return await interaction.response.send_message("Staff only.", ephemeral=True)
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
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                return
            data = storage.load_guild(interaction.guild.id)
            tcfg = data.get("tickets") or {}
            is_opener = False
            for v in (data.get("ticketRecords") or {}).values():
                if str(v.get("channelId")) == str(getattr(interaction.channel, "id", "")):
                    if str(v.get("userId")) == str(interaction.user.id):
                        is_opener = True
                    break
            if not (is_opener or _is_staff(interaction.user, tcfg)):
                return await interaction.response.send_message(
                    "Only the ticket opener or staff can close this.", ephemeral=True
                )
            await self._close_ticket(interaction)
            return

        if action.startswith("btn:"):
            button_id = action.removeprefix("btn:")
            data = storage.load_guild(interaction.guild.id)  # type: ignore
            buttons = (data.get("tickets") or {}).get("buttons") or []
            btn = next((b for b in buttons if str(b.get("id")) == button_id), None)
            if not btn:
                return await interaction.response.send_message(
                    "This button is no longer configured. Ask staff to re-post the panel.",
                    ephemeral=True,
                )
            purpose = str(btn.get("purpose") or button_id)
            label = str(btn.get("label") or "Ticket")
            if btn.get("useForm", True):
                modal = TicketFormModal(self, button_id, purpose, label)
                return await interaction.response.send_modal(modal)
            # Instant open
            await self._create_ticket(
                interaction,
                kind=purpose,
                subject=f"Opened via panel · {label}",
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
