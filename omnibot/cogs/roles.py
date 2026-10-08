"""Autorole, reaction roles (multi-panel + bind), give/remove roles."""
from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


def _emoji_key(emoji) -> str:
    if emoji is None:
        return ""
    if isinstance(emoji, str):
        return emoji.strip()
    if getattr(emoji, "id", None):
        return f"{emoji.name}:{emoji.id}"
    return str(getattr(emoji, "name", emoji) or emoji)


def _emoji_matches(a, b: str) -> bool:
    ka, kb = _emoji_key(a), _emoji_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True

    def norm(s: str) -> str:
        s = s.strip()
        m = re.match(r"<a?:(\w+):(\d+)>"
                     , s)
        if m:
            return f"{m.group(1)}:{m.group(2)}"
        return s

    return norm(ka) == norm(kb)


def _find_entry(rr: dict, message_id: int, emoji) -> tuple[str | None, dict | None]:
    mid = str(message_id)
    for key, entry in (rr or {}).items():
        if str(entry.get("messageId") or "") != mid and not key.startswith(f"{message_id}:"):
            continue
        if _emoji_matches(emoji, entry.get("emoji") or key.split(":", 1)[-1]):
            return key, entry
    for key, entry in (rr or {}).items():
        if key.startswith(f"{message_id}:") or str(entry.get("messageId")) == mid:
            if _emoji_matches(emoji, entry.get("emoji") or ""):
                return key, entry
    return None, None


def _group_panels(rr: dict) -> dict[str, list[dict]]:
    panels: dict[str, list[dict]] = {}
    for key, entry in (rr or {}).items():
        mid = str(entry.get("messageId") or key.split(":")[0])
        panels.setdefault(mid, []).append({**entry, "key": key})
    return panels


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    rolecfg = app_commands.Group(name="roles", description="Role tools & reaction roles")

    @rolecfg.command(name="autorole", description="Set role given on join")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole(self, interaction: discord.Interaction, role: discord.Role, enabled: bool = True):
        def mut(d):
            d["autorole"] = {"enabled": enabled, "roleId": str(role.id)}
        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(
            f"Autorole → {role.mention} ({'on' if enabled else 'off'})", ephemeral=True
        )

    @rolecfg.command(name="give", description="Give a role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def give(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        try:
            await member.add_roles(role, reason=f"By {interaction.user}")
        except Exception as e:
            return await interaction.response.send_message(f"Failed: {e}", ephemeral=True)
        await interaction.response.send_message(f"Gave {role.mention} to {member.mention}")

    @rolecfg.command(name="remove", description="Remove a role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def remove(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        try:
            await member.remove_roles(role, reason=f"By {interaction.user}")
        except Exception as e:
            return await interaction.response.send_message(f"Failed: {e}", ephemeral=True)
        await interaction.response.send_message(f"Removed {role.mention} from {member.mention}")

    @rolecfg.command(name="panel", description="Post a NEW reaction-role panel (supports multiple panels)")
    @app_commands.describe(
        title="Panel title",
        description="Panel description",
        emoji1="First emoji",
        role1="Role for emoji1",
        emoji2="Optional second emoji",
        role2="Role for emoji2",
        emoji3="Optional third emoji",
        role3="Role for emoji3",
        emoji4="Optional fourth emoji",
        role4="Role for emoji4",
        emoji5="Optional fifth emoji",
        role5="Role for emoji5",
        channel="Where to post (default: here)",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def panel(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        emoji1: str,
        role1: discord.Role,
        emoji2: str | None = None,
        role2: discord.Role | None = None,
        emoji3: str | None = None,
        role3: discord.Role | None = None,
        emoji4: str | None = None,
        role4: discord.Role | None = None,
        emoji5: str | None = None,
        role5: discord.Role | None = None,
        channel: discord.TextChannel | None = None,
    ):
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("Text channel required.", ephemeral=True)

        pairs: list[tuple[str, discord.Role]] = [(emoji1.strip(), role1)]
        for em, ro in ((emoji2, role2), (emoji3, role3), (emoji4, role4), (emoji5, role5)):
            if em and ro:
                pairs.append((em.strip(), ro))

        lines = [f"{em} — {ro.mention}" for em, ro in pairs]
        emb = discord.Embed(
            title=title[:256],
            description=(description[:1500] + "\n\n" + "\n".join(lines))[:4000],
            color=0x5B6CFF,
        )
        emb.set_footer(text="React to get or remove a role · OmniBot")
        try:
            msg = await ch.send(embed=emb)
        except Exception as e:
            return await interaction.response.send_message(f"Could not post panel: {e}", ephemeral=True)

        failed = []
        for em, _ in pairs:
            try:
                await msg.add_reaction(em)
            except Exception:
                failed.append(em)

        def mut(d):
            rr = d.setdefault("reactionRoles", {})
            for em, ro in pairs:
                key = f"{msg.id}:{_emoji_key(em)}"
                rr[key] = {
                    "messageId": str(msg.id),
                    "emoji": em,
                    "roleId": str(ro.id),
                    "channelId": str(ch.id),
                    "panelTitle": title[:100],
                }
            panels_meta = d.setdefault("reactionPanels", {})
            panels_meta[str(msg.id)] = {
                "messageId": str(msg.id),
                "channelId": str(ch.id),
                "title": title[:100],
                "createdAt": int(msg.created_at.timestamp()) if msg.created_at else 0,
            }

        storage.update_guild(interaction.guild.id, mut)
        note = f" (failed reactions: {', '.join(failed)})" if failed else ""
        await interaction.response.send_message(
            f"Panel posted in {ch.mention} · message `{msg.id}` · {len(pairs)} role(s){note}\n"
            f"You can post more panels anytime — they all work together.",
            ephemeral=True,
        )

    @rolecfg.command(name="reaction", description="Bind emoji → role on an existing message")
    @app_commands.describe(
        message_id="Message ID",
        emoji="Emoji to react with",
        role="Role to give when reacted",
        channel="Channel of the message",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reaction(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
        role: discord.Role,
        channel: discord.TextChannel | None = None,
    ):
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("Text channel required.", ephemeral=True)
        emoji = emoji.strip()
        try:
            msg = await ch.fetch_message(int(message_id.strip()))
            await msg.add_reaction(emoji)
        except Exception as e:
            return await interaction.response.send_message(
                f"Failed to add reaction: {e}", ephemeral=True
            )

        def mut(d):
            rr = d.setdefault("reactionRoles", {})
            key = f"{msg.id}:{_emoji_key(emoji)}"
            rr[key] = {
                "messageId": str(msg.id),
                "emoji": emoji,
                "roleId": str(role.id),
                "channelId": str(ch.id),
            }

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(
            f"Bound {emoji} → {role.mention} on message `{msg.id}`", ephemeral=True
        )

    @rolecfg.command(name="list", description="List all reaction-role panels and bindings")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def list_rr(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)
        rr = data.get("reactionRoles") or {}
        if not rr:
            return await interaction.response.send_message("No reaction role panels yet.", ephemeral=True)
        panels = _group_panels(rr)
        lines = [f"**{len(panels)} panel(s)** · {len(rr)} binding(s)\n"]
        for mid, entries in list(panels.items())[:15]:
            title = entries[0].get("panelTitle") or "Panel"
            ch = entries[0].get("channelId") or "?"
            lines.append(f"**{title}** · msg `{mid}` · channel `{ch}`")
            for e in entries[:8]:
                lines.append(f"  {e.get('emoji')} → role `{e.get('roleId')}`")
            if len(entries) > 8:
                lines.append(f"  … +{len(entries) - 8} more")
        await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)

    @rolecfg.command(name="panel-remove", description="Remove an entire reaction-role panel by message ID")
    @app_commands.describe(message_id="Message ID of the panel to remove")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def panel_remove(self, interaction: discord.Interaction, message_id: str):
        mid = message_id.strip()
        removed = 0

        def mut(d):
            nonlocal removed
            rr = d.get("reactionRoles") or {}
            keys = [k for k, v in rr.items() if str(v.get("messageId")) == mid or k.startswith(f"{mid}:")]
            for k in keys:
                del rr[k]
                removed += 1
            d["reactionRoles"] = rr
            meta = d.get("reactionPanels") or {}
            meta.pop(mid, None)
            d["reactionPanels"] = meta

        storage.update_guild(interaction.guild.id, mut)
        if removed:
            await interaction.response.send_message(
                f"Removed panel `{mid}` ({removed} binding(s)). You can delete the Discord message manually.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("No bindings found for that message ID.", ephemeral=True)

    @rolecfg.command(name="unbind", description="Remove a single emoji binding from a panel")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def unbind(self, interaction: discord.Interaction, message_id: str, emoji: str):
        emoji = emoji.strip()
        removed = False

        def mut(d):
            nonlocal removed
            rr = d.get("reactionRoles") or {}
            key, entry = _find_entry(rr, int(message_id), emoji)
            if key and key in rr:
                del rr[key]
                removed = True
            d["reactionRoles"] = rr

        storage.update_guild(interaction.guild.id, mut)
        if removed:
            await interaction.response.send_message("Binding removed.", ephemeral=True)
        else:
            await interaction.response.send_message("No matching binding found.", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        if self.bot.user and payload.user_id == self.bot.user.id:
            return
        data = storage.load_guild(payload.guild_id)
        rr = data.get("reactionRoles") or {}
        _, entry = _find_entry(rr, payload.message_id, payload.emoji)
        if not entry:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        role = guild.get_role(int(entry["roleId"]))
        if member and role and not member.get_role(role.id):
            try:
                await member.add_roles(role, reason="Reaction role")
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        data = storage.load_guild(payload.guild_id)
        rr = data.get("reactionRoles") or {}
        _, entry = _find_entry(rr, payload.message_id, payload.emoji)
        if not entry:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        try:
            member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        except Exception:
            return
        role = guild.get_role(int(entry["roleId"]))
        if member and role and member.get_role(role.id):
            try:
                await member.remove_roles(role, reason="Reaction role remove")
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        data = storage.load_guild(member.guild.id)
        ar = data.get("autorole") or {}
        if not ar.get("enabled") or not ar.get("roleId"):
            return
        role = member.guild.get_role(int(ar["roleId"]))
        if role:
            try:
                await member.add_roles(role, reason="Autorole")
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
