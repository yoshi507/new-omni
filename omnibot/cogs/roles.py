"""Autorole, reaction roles, self-roles, temp roles."""
from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    rolecfg = app_commands.Group(name="roles", description="Role tools")

    @rolecfg.command(name="autorole", description="Set role given on join")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole(self, interaction: discord.Interaction, role: discord.Role, enabled: bool = True):
        def mut(d):
            d["autorole"] = {"enabled": enabled, "roleId": str(role.id)}

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Autorole → {role.mention} ({'on' if enabled else 'off'})")

    @rolecfg.command(name="give", description="Give a role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def give(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await member.add_roles(role, reason=f"By {interaction.user}")
        await interaction.response.send_message(f"Gave {role.mention} to {member.mention}")

    @rolecfg.command(name="remove", description="Remove a role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def remove(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await member.remove_roles(role, reason=f"By {interaction.user}")
        await interaction.response.send_message(f"Removed {role.mention} from {member.mention}")

    @rolecfg.command(name="reaction", description="Bind emoji reaction → role on a message")
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
        try:
            msg = await ch.fetch_message(int(message_id))
            await msg.add_reaction(emoji)
        except Exception as e:
            return await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

        def mut(d):
            rr = d.setdefault("reactionRoles", {})
            key = f"{msg.id}:{emoji}"
            rr[key] = {"messageId": str(msg.id), "emoji": emoji, "roleId": str(role.id), "channelId": str(ch.id)}

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Reaction role set: {emoji} → {role.mention}", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id or payload.user_id == (self.bot.user.id if self.bot.user else 0):
            return
        data = storage.load_guild(payload.guild_id)
        rr = data.get("reactionRoles") or {}
        emoji = str(payload.emoji)
        key = f"{payload.message_id}:{emoji}"
        entry = rr.get(key)
        if not entry:
            # try name-only match
            for k, v in rr.items():
                if k.startswith(f"{payload.message_id}:") and (v.get("emoji") == emoji or emoji in k):
                    entry = v
                    break
        if not entry:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(entry["roleId"]))
        if member and role:
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
        emoji = str(payload.emoji)
        entry = None
        for k, v in rr.items():
            if k.startswith(f"{payload.message_id}:") and (v.get("emoji") == emoji or emoji in k):
                entry = v
                break
        if not entry:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(entry["roleId"]))
        if member and role:
            try:
                await member.remove_roles(role, reason="Reaction role remove")
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
