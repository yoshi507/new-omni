"""Moderation commands + automod."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _log(self, guild: discord.Guild, text: str):
        data = storage.load_guild(guild.id)
        ch_id = storage.get_path(data, "settings.modLogChannel") or storage.get_path(
            data, "logging.channelId"
        )
        if not ch_id:
            return
        ch = guild.get_channel(int(ch_id))
        if ch and isinstance(ch, discord.TextChannel):
            try:
                await ch.send(text)
            except Exception:
                pass

    @app_commands.command(name="ban", description="Ban a member")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(member="Member", reason="Reason")
    async def ban(
        self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"
    ):
        await member.ban(reason=reason)
        await interaction.response.send_message(f"Banned **{member}** — {reason}")
        await self._log(interaction.guild, f"🔨 Ban {member} by {interaction.user}: {reason}")  # type: ignore

    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.default_permissions(kick_members=True)
    async def kick(
        self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"
    ):
        await member.kick(reason=reason)
        await interaction.response.send_message(f"Kicked **{member}** — {reason}")
        await self._log(interaction.guild, f"👢 Kick {member} by {interaction.user}: {reason}")  # type: ignore

    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(minutes="Duration in minutes")
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320] = 10,
        reason: str = "No reason",
    ):
        from datetime import timedelta

        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await interaction.response.send_message(f"Timed out **{member}** for {minutes}m")
        await self._log(interaction.guild, f"⏱️ Timeout {member} {minutes}m by {interaction.user}")  # type: ignore

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.default_permissions(moderate_members=True)
    async def warn(
        self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"
    ):
        gid = interaction.guild.id  # type: ignore

        def mut(data):
            w = data.setdefault("warnings", {}).setdefault(str(member.id), [])
            w.append({"reason": reason, "mod": str(interaction.user.id)})

        storage.update_guild(gid, mut)
        await interaction.response.send_message(f"Warned **{member}** — {reason}")
        await self._log(interaction.guild, f"⚠️ Warn {member} by {interaction.user}: {reason}")  # type: ignore

    @app_commands.command(name="warnings", description="List warnings for a member")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        w = (data.get("warnings") or {}).get(str(member.id), [])
        if not w:
            return await interaction.response.send_message("No warnings.", ephemeral=True)
        lines = [f"{i+1}. {x.get('reason', '?')}" for i, x in enumerate(w[-15:])]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Clear warnings for a member")
    @app_commands.default_permissions(moderate_members=True)
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        def mut(data):
            (data.get("warnings") or {}).pop(str(member.id), None)

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(f"Cleared warnings for **{member}**.")

    @app_commands.command(name="clear", description="Delete recent messages")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(amount="Number of messages (1-100)")
    async def clear(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100] = 10):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)  # type: ignore
        await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)

    @app_commands.command(name="lock", description="Lock the channel")
    @app_commands.default_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction):
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("Text only.", ephemeral=True)
        overwrite = ch.overwrites_for(interaction.guild.default_role)  # type: ignore
        overwrite.send_messages = False
        await ch.set_permissions(interaction.guild.default_role, overwrite=overwrite)  # type: ignore
        await interaction.response.send_message("🔒 Channel locked.")

    @app_commands.command(name="unlock", description="Unlock the channel")
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction):
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("Text only.", ephemeral=True)
        overwrite = ch.overwrites_for(interaction.guild.default_role)  # type: ignore
        overwrite.send_messages = None
        await ch.set_permissions(interaction.guild.default_role, overwrite=overwrite)  # type: ignore
        await interaction.response.send_message("🔓 Channel unlocked.")

    @app_commands.command(name="slowmode", description="Set channel slowmode seconds")
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(
        self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600] = 0
    ):
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("Text only.", ephemeral=True)
        await ch.edit(slowmode_delay=seconds)
        await interaction.response.send_message(f"Slowmode set to {seconds}s.")

    # Automod group
    automod = app_commands.Group(name="automod", description="OmniBot automod controls")

    @automod.command(name="enable", description="Enable word filter automod")
    @app_commands.default_permissions(manage_guild=True)
    async def automod_enable(self, interaction: discord.Interaction):
        def mut(d):
            d.setdefault("automod", {})["enabled"] = True

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Automod enabled.")

    @automod.command(name="disable", description="Disable word filter automod")
    @app_commands.default_permissions(manage_guild=True)
    async def automod_disable(self, interaction: discord.Interaction):
        def mut(d):
            d.setdefault("automod", {})["enabled"] = False

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Automod disabled.")

    @automod.command(name="addword", description="Add a blocked word")
    @app_commands.default_permissions(manage_guild=True)
    async def automod_addword(self, interaction: discord.Interaction, word: str):
        def mut(d):
            am = d.setdefault("automod", {})
            words = [w.strip() for w in str(am.get("blockedWords") or "").split(",") if w.strip()]
            if word.lower() not in [w.lower() for w in words]:
                words.append(word)
            am["blockedWords"] = ", ".join(words)

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(f"Added `{word}`.", ephemeral=True)

    @automod.command(name="list", description="List blocked words")
    @app_commands.default_permissions(manage_guild=True)
    async def automod_list(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        words = (data.get("automod") or {}).get("blockedWords") or "(none)"
        await interaction.response.send_message(f"Blocked: {words}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
