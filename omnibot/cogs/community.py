"""Community tools: giveaways, reaction roles, partner, captcha, userphone, quiz, translate."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


class Community(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="reactionrole", description="Post a simple reaction-role message")
    @app_commands.default_permissions(administrator=True)
    async def reactionrole(
        self,
        interaction: discord.Interaction,
        emoji: str,
        role: discord.Role,
        channel: discord.TextChannel | None = None,
        text: str = "React to get a role",
    ):
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("Text channel only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        msg = await ch.send(text)
        try:
            await msg.add_reaction(emoji)
        except Exception as e:
            return await interaction.followup.send(f"Could not add reaction: {e}", ephemeral=True)

        def mut(d):
            rr = d.setdefault("reactionRoles", {})
            rr[str(msg.id)] = {"emoji": emoji, "roleId": str(role.id)}

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.followup.send(f"Reaction role set in {ch.mention}.", ephemeral=True)

    @app_commands.command(name="captcha-setup", description="Enable join captcha (verify button)")
    @app_commands.default_permissions(administrator=True)
    async def captcha_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: discord.Role,
        enabled: bool = True,
    ):
        def mut(d):
            v = d.setdefault("verification", {})
            v["enabled"] = enabled
            v["channelId"] = str(channel.id)
            v["roleId"] = str(role.id)

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(
            f"Verification {'on' if enabled else 'off'} in {channel.mention} → {role.mention}",
            ephemeral=True,
        )

    @app_commands.command(name="partner", description="Set partner advertise channel")
    @app_commands.default_permissions(administrator=True)
    async def partner(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        enabled: bool | None = None,
    ):
        def mut(d):
            p = d.setdefault("partner", {})
            if enabled is not None:
                p["enabled"] = enabled
            if channel is not None:
                p["channelId"] = str(channel.id)

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Partner settings updated.", ephemeral=True)

    @app_commands.command(name="verify-panel", description="Post a verify button panel")
    @app_commands.default_permissions(administrator=True)
    async def verify_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        role: discord.Role | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        v = data.get("verification") or {}
        role_id = str(role.id) if role else (v.get("roleId") or "")
        if not role_id:
            return await interaction.followup.send(
                "Set a verify role: pass `role:` here, or run `/verify setup` / `/captcha-setup` first.",
                ephemeral=True,
            )
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.followup.send("Text channel only.", ephemeral=True)
        if v.get("channelId") and v.get("messageId"):
            try:
                old_ch = interaction.guild.get_channel(int(v["channelId"]))  # type: ignore
                if isinstance(old_ch, discord.TextChannel):
                    await (await old_ch.fetch_message(int(v["messageId"]))).delete()
            except Exception:
                pass
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                label="Verify", style=discord.ButtonStyle.success, custom_id="omnibot:verify", emoji="✅"
            )
        )
        desc = v.get("message") or "Click **Verify** to unlock the server."
        emb = discord.Embed(title="✅ Verification", description=desc, color=0x5B6CFF)
        try:
            msg = await ch.send(embed=emb, view=view)
        except discord.Forbidden:
            return await interaction.followup.send(
                f"I can't post in {ch.mention}. Need **Send Messages** + **Embed Links**.",
                ephemeral=True,
            )
        except Exception as e:
            return await interaction.followup.send(f"Failed: {e}", ephemeral=True)

        def mut(d):
            vv = d.setdefault("verification", {})
            vv["enabled"] = True
            vv["roleId"] = role_id
            vv["channelId"] = str(ch.id)
            vv["messageId"] = str(msg.id)

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.followup.send(f"Panel posted in {ch.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Community(bot))
