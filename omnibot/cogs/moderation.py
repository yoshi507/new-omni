"""Moderation commands with hierarchy checks, warnings, and clear errors."""
from __future__ import annotations

import datetime
import time

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


def _bot_member(guild: discord.Guild) -> discord.Member | None:
    return guild.me


def _hierarchy_error(bot_m: discord.Member, target: discord.Member) -> str | None:
    if target.id == (target.guild.owner_id or 0):
        return "You cannot moderate the server owner."
    if target.id == bot_m.id:
        return "I cannot moderate myself."
    if target.top_role >= bot_m.top_role:
        return (
            f"My highest role (**{bot_m.top_role.name}**) must be **above** "
            f"**{target.display_name}**'s highest role (**{target.top_role.name}**). "
            "Move the OmniBot role higher in Server Settings → Roles."
        )
    return None


def _perm_error(bot_m: discord.Member, need: str) -> str | None:
    p = bot_m.guild_permissions
    mapping = {
        "kick": p.kick_members,
        "ban": p.ban_members,
        "timeout": p.moderate_members,
        "manage_messages": p.manage_messages,
        "manage_channels": p.manage_channels,
    }
    if not mapping.get(need, False):
        labels = {
            "kick": "Kick Members",
            "ban": "Ban Members",
            "timeout": "Timeout Members (Moderate Members)",
            "manage_messages": "Manage Messages",
            "manage_channels": "Manage Channels",
        }
        return (
            f"I need the **{labels.get(need, need)}** permission. "
            "Give it to the OmniBot role (or enable it in the invite)."
        )
    return None


async def _modlog(guild: discord.Guild, embed: discord.Embed) -> None:
    data = storage.load_guild(guild.id)
    log_cfg = data.get("logging") or {}
    if not log_cfg.get("enabled"):
        return
    cid = log_cfg.get("channelId") or log_cfg.get("modLogChannelId")
    if not cid:
        return
    ch = guild.get_channel(int(cid))
    if isinstance(ch, discord.TextChannel):
        try:
            await ch.send(embed=embed)
        except Exception:
            pass


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _guard(self, interaction: discord.Interaction, member: discord.Member, need: str) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return False
        bot_m = _bot_member(interaction.guild)
        if not bot_m:
            await interaction.response.send_message("Bot member not found.", ephemeral=True)
            return False
        err = _perm_error(bot_m, need)
        if err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return False
        err = _hierarchy_error(bot_m, member)
        if err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return False
        inv = interaction.user
        if not inv.guild_permissions.administrator:
            if member.top_role >= inv.top_role and member.id != inv.id:
                await interaction.response.send_message(
                    "❌ You cannot moderate someone with an equal or higher role than yours.",
                    ephemeral=True,
                )
                return False
        return True

    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        if not await self._guard(interaction, member, "kick"):
            return
        try:
            await member.kick(reason=f"{interaction.user} | {reason}")
            await interaction.response.send_message(f"✅ Kicked **{member}** — {reason}")
            emb = discord.Embed(title="Member kicked", color=0xF59E0B, timestamp=discord.utils.utcnow())
            emb.add_field(name="User", value=f"{member} (`{member.id}`)")
            emb.add_field(name="Moderator", value=str(interaction.user))
            emb.add_field(name="Reason", value=reason, inline=False)
            await _modlog(interaction.guild, emb)  # type: ignore
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ **403 Missing Permissions** — Move **OmniBot** role above the target and ensure Kick Members is enabled.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @app_commands.command(name="ban", description="Ban a member")
    @app_commands.default_permissions(ban_members=True)
    async def ban(
        self, interaction: discord.Interaction, member: discord.Member,
        reason: str = "No reason", delete_days: app_commands.Range[int, 0, 7] = 0,
    ):
        if not await self._guard(interaction, member, "ban"):
            return
        try:
            await member.ban(reason=f"{interaction.user} | {reason}", delete_message_days=delete_days)
            await interaction.response.send_message(f"✅ Banned **{member}** — {reason}")
            emb = discord.Embed(title="Member banned", color=0xEF4444, timestamp=discord.utils.utcnow())
            emb.add_field(name="User", value=f"{member} (`{member.id}`)")
            emb.add_field(name="Moderator", value=str(interaction.user))
            emb.add_field(name="Reason", value=reason, inline=False)
            await _modlog(interaction.guild, emb)  # type: ignore
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ **403 Missing Permissions** — Move **OmniBot** role above the target and ensure Ban Members is enabled.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @app_commands.command(name="softban", description="Ban then unban (purge recent messages)")
    @app_commands.default_permissions(ban_members=True)
    async def softban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Softban"):
        if not await self._guard(interaction, member, "ban"):
            return
        try:
            await member.ban(reason=f"Softban by {interaction.user} | {reason}", delete_message_days=1)
            await interaction.guild.unban(member, reason="Softban unban")  # type: ignore
            await interaction.response.send_message(f"✅ Softbanned **{member}** — {reason}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Missing ban permissions or role hierarchy.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @app_commands.command(name="unban", description="Unban a user by ID")
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "Unbanned"):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        bot_m = _bot_member(interaction.guild)
        if bot_m and (err := _perm_error(bot_m, "ban")):
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)
        try:
            user = await self.bot.fetch_user(int(user_id.strip()))
            await interaction.guild.unban(user, reason=f"{interaction.user} | {reason}")
            await interaction.response.send_message(f"✅ Unbanned **{user}**")
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.default_permissions(moderate_members=True)
    async def timeout(
        self, interaction: discord.Interaction, member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320] = 10, reason: str = "No reason",
    ):
        if not await self._guard(interaction, member, "timeout"):
            return
        try:
            until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
            await member.timeout(until, reason=f"{interaction.user} | {reason}")
            await interaction.response.send_message(f"✅ Timed out **{member}** for **{minutes}m** — {reason}")
            emb = discord.Embed(title="Member timed out", color=0x8B5CF6, timestamp=discord.utils.utcnow())
            emb.add_field(name="User", value=f"{member} (`{member.id}`)")
            emb.add_field(name="Duration", value=f"{minutes} minutes")
            emb.add_field(name="Moderator", value=str(interaction.user))
            emb.add_field(name="Reason", value=reason, inline=False)
            await _modlog(interaction.guild, emb)  # type: ignore
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ **403 Missing Permissions** — Move OmniBot role above the target; give Timeout Members; Community may need to be enabled.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @app_commands.command(name="untimeout", description="Remove a member's timeout")
    @app_commands.default_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Timeout removed"):
        if not await self._guard(interaction, member, "timeout"):
            return
        try:
            await member.timeout(None, reason=f"{interaction.user} | {reason}")
            await interaction.response.send_message(f"✅ Removed timeout from **{member}**")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Missing permissions or role hierarchy.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        uid = str(member.id)
        count = 0

        def mut(d):
            nonlocal count
            warns = d.setdefault("warnings", {}).setdefault(uid, [])
            warns.append({"reason": reason, "moderatorId": str(interaction.user.id), "at": time.time()})
            count = len(warns)

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"⚠️ Warned **{member}** — {reason}\nThey now have **{count}** warning(s).")
        try:
            await member.send(f"You were warned in **{interaction.guild.name}**: {reason}\nTotal warnings: **{count}**")
        except Exception:
            pass

    @app_commands.command(name="warnings", description="List warnings for a member")
    @app_commands.default_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        data = storage.load_guild(interaction.guild.id)
        warns = (data.get("warnings") or {}).get(str(member.id)) or []
        if not warns:
            return await interaction.response.send_message(f"**{member}** has no warnings.", ephemeral=True)
        lines = [f"**{i}.** {w.get('reason', '?')} · <t:{int(w.get('at', 0))}:R>" for i, w in enumerate(warns[-15:], 1)]
        await interaction.response.send_message(f"Warnings for **{member}** ({len(warns)} total):\n" + "\n".join(lines), ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a member")
    @app_commands.default_permissions(administrator=True)
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)

        def mut(d):
            (d.get("warnings") or {}).pop(str(member.id), None)

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Cleared warnings for **{member}**.", ephemeral=True)

    @app_commands.command(name="purge", description="Delete recent messages")
    @app_commands.default_permissions(manage_messages=True)
    async def purge(
        self, interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100] = 10, user: discord.Member | None = None,
    ):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Text channel only.", ephemeral=True)
        bot_m = _bot_member(interaction.guild)
        if bot_m and (err := _perm_error(bot_m, "manage_messages")):
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            def check(m: discord.Message) -> bool:
                return (not user) or m.author.id == user.id
            deleted = await interaction.channel.purge(limit=amount, check=check)
            await interaction.followup.send(f"✅ Deleted **{len(deleted)}** message(s).", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Missing Manage Messages or messages too old.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

    @app_commands.command(name="slowmode", description="Set channel slowmode (0 to disable)")
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(
        self, interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 21600] = 0, channel: discord.TextChannel | None = None,
    ):
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("Text channel only.", ephemeral=True)
        try:
            await ch.edit(slowmode_delay=seconds)
            msg = "disabled" if seconds == 0 else f"set to **{seconds}s**"
            await interaction.response.send_message(f"✅ Slowmode {msg} in {ch.mention}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Need Manage Channels.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @app_commands.command(name="lock", description="Lock a channel")
    @app_commands.default_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None, reason: str = "Locked"):
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel) or not interaction.guild:
            return await interaction.response.send_message("Text channel only.", ephemeral=True)
        try:
            overwrite = ch.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = False
            await ch.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)
            await interaction.response.send_message(f"🔒 Locked {ch.mention}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Missing Manage Channels.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @app_commands.command(name="unlock", description="Unlock a channel")
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None, reason: str = "Unlocked"):
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel) or not interaction.guild:
            return await interaction.response.send_message("Text channel only.", ephemeral=True)
        try:
            overwrite = ch.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = None
            await ch.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)
            await interaction.response.send_message(f"🔓 Unlocked {ch.mention}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Missing Manage Channels.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @app_commands.command(name="automod", description="Configure word-filter automod")
    @app_commands.default_permissions(administrator=True)
    async def automod(self, interaction: discord.Interaction, enabled: bool | None = None, blocked_words: str | None = None):
        def mut(d):
            am = d.setdefault("automod", {})
            if enabled is not None:
                am["enabled"] = enabled
            if blocked_words is not None:
                am["blockedWords"] = blocked_words
        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Automod updated.", ephemeral=True)

    @app_commands.command(name="antispam", description="Toggle anti-spam")
    @app_commands.default_permissions(administrator=True)
    async def antispam(self, interaction: discord.Interaction, enabled: bool):
        def mut(d):
            d.setdefault("spamConfig", {})["enabled"] = enabled
        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(f"Anti-spam {'on' if enabled else 'off'}.", ephemeral=True)

    @app_commands.command(name="security", description="Set anti-nuke security mode")
    @app_commands.default_permissions(administrator=True)
    async def security(self, interaction: discord.Interaction, enabled: bool | None = None, mode: str | None = None):
        def mut(d):
            s = d.setdefault("security", {})
            if enabled is not None:
                s["enabled"] = enabled
            if mode is not None:
                s["mode"] = mode
        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Security updated.", ephemeral=True)

    @app_commands.command(name="honeypot", description="Configure honeypot channel")
    @app_commands.default_permissions(administrator=True)
    async def honeypot(self, interaction: discord.Interaction, enabled: bool | None = None, channel: discord.TextChannel | None = None):
        def mut(d):
            h = d.setdefault("honeypot", {})
            if enabled is not None:
                h["enabled"] = enabled
            if channel is not None:
                h["channelId"] = str(channel.id)
        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Honeypot updated.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
