"""Starboard, sticky roles, invites, counting, word-chain, AFK, verification, honeypot, boosters."""
from __future__ import annotations

import re
import time
from collections import defaultdict

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage

HONEYPOT_WARNING = (
    "⚠️ **HONEYPOT CHANNEL** ⚠️\n\n"
    "This channel is monitored.\n"
    "**Anyone who sends a message here will be automatically banned.**\n\n"
    "If you can see this and you are a normal member: **do not type anything.**\n"
    "Leave this channel immediately."
)


class EngagementExtra(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._invite_cache: dict[int, dict[str, int]] = {}
        self._counting_expect: dict[int, int] = {}
        self._wordchain_last: dict[int, str] = {}
        self._afk: dict[int, dict[int, str]] = defaultdict(dict)

    engage = app_commands.Group(name="engage", description="Engagement tools")
    inv = app_commands.Group(name="invite", description="Invite tracking")
    verify_g = app_commands.Group(name="verify", description="Member verification")

    @engage.command(name="starboard-setup", description="Set starboard channel and emoji threshold")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def starboard_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        emoji: str = "⭐",
        threshold: app_commands.Range[int, 1, 50] = 3,
    ):
        def mut(d):
            d["starboard"] = {
                "enabled": True,
                "channelId": str(channel.id),
                "emoji": emoji,
                "threshold": threshold,
            }

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(
            f"Starboard → {channel.mention} · {emoji} × {threshold}", ephemeral=True
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id or payload.user_id == (self.bot.user.id if self.bot.user else 0):
            return
        data = storage.load_guild(payload.guild_id)
        sb = data.get("starboard") or {}
        if not sb.get("enabled") or not sb.get("channelId"):
            return
        emoji = str(payload.emoji)
        if emoji != sb.get("emoji", "⭐") and getattr(payload.emoji, "name", None) != sb.get("emoji", "⭐").strip(":"):
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        ch = guild.get_channel(payload.channel_id)
        if not isinstance(ch, discord.TextChannel):
            return
        try:
            msg = await ch.fetch_message(payload.message_id)
        except Exception:
            return
        count = 0
        for r in msg.reactions:
            if str(r.emoji) == emoji or getattr(r.emoji, "name", None) == sb.get("emoji"):
                count = r.count
                break
        if count < int(sb.get("threshold") or 3):
            return
        posted = (data.get("starboardPosts") or {}).get(str(msg.id))
        if posted:
            return
        dest = guild.get_channel(int(sb["channelId"]))
        if not isinstance(dest, discord.TextChannel):
            return
        emb = discord.Embed(
            description=msg.content[:2000] or "*attachment/embed*",
            color=0xF1C40F,
            timestamp=msg.created_at,
        )
        emb.set_author(name=msg.author.display_name, icon_url=msg.author.display_avatar.url)
        emb.add_field(name="Source", value=f"[Jump]({msg.jump_url})")
        emb.set_footer(text=f"{emoji} {count}")
        if msg.attachments:
            emb.set_image(url=msg.attachments[0].url)
        try:
            sent = await dest.send(embed=emb)

            def mut(d):
                d.setdefault("starboardPosts", {})[str(msg.id)] = str(sent.id)

            storage.update_guild(payload.guild_id, mut)
        except Exception:
            pass

    @engage.command(name="sticky-toggle", description="Restore roles when members rejoin")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def sticky_toggle(self, interaction: discord.Interaction, enabled: bool):
        def mut(d):
            d.setdefault("stickyRoles", {})["enabled"] = enabled

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Sticky roles **{'on' if enabled else 'off'}**.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        data = storage.load_guild(member.guild.id)
        if not (data.get("stickyRoles") or {}).get("enabled"):
            return
        role_ids = [str(r.id) for r in member.roles if not r.is_default() and not r.managed]

        def mut(d):
            d.setdefault("stickyRoles", {}).setdefault("saved", {})[str(member.id)] = role_ids

        storage.update_guild(member.guild.id, mut)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        data = storage.load_guild(member.guild.id)
        sr = data.get("stickyRoles") or {}
        if sr.get("enabled"):
            saved = (sr.get("saved") or {}).get(str(member.id)) or []
            roles = [member.guild.get_role(int(rid)) for rid in saved]
            roles = [r for r in roles if r]
            if roles:
                try:
                    await member.add_roles(*roles, reason="Sticky roles restore")
                except Exception:
                    pass
        guild = member.guild
        try:
            invs = await guild.invites()
        except Exception:
            invs = []
        current = {i.code: i.uses or 0 for i in invs}
        old = self._invite_cache.get(guild.id) or {}
        inviter_id = None
        for code, uses in current.items():
            if uses > old.get(code, 0):
                for i in invs:
                    if i.code == code and i.inviter:
                        inviter_id = str(i.inviter.id)
                break
        self._invite_cache[guild.id] = current
        if inviter_id:

            def mut_inv(d):
                inv = d.setdefault("invites", {}).setdefault(inviter_id, {"joins": 0})
                inv["joins"] = int(inv.get("joins") or 0) + 1
                d.setdefault("inviteJoins", {})[str(member.id)] = inviter_id

            storage.update_guild(guild.id, mut_inv)

    @inv.command(name="leaderboard", description="Top inviters")
    async def invite_lb(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)
        invs = data.get("invites") or {}
        ranked = sorted(invs.items(), key=lambda kv: kv[1].get("joins", 0), reverse=True)[:15]
        if not ranked:
            return await interaction.response.send_message("No invite data yet.")
        lines = [
            f"**{i}.** <@{uid}> — **{v.get('joins', 0)}** joins"
            for i, (uid, v) in enumerate(ranked, 1)
        ]
        await interaction.response.send_message("📨 Invite leaderboard\n" + "\n".join(lines))

    @inv.command(name="stats", description="Your invite stats")
    async def invite_stats(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ):
        m = member or interaction.user
        data = storage.load_guild(interaction.guild.id)
        v = (data.get("invites") or {}).get(str(m.id)) or {"joins": 0}
        await interaction.response.send_message(
            f"**{m.display_name}** invited **{v.get('joins', 0)}** members."
        )

    @commands.Cog.listener()
    async def on_ready(self):
        for g in self.bot.guilds:
            try:
                invs = await g.invites()
                self._invite_cache[g.id] = {i.code: i.uses or 0 for i in invs}
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild:
            cache = self._invite_cache.setdefault(invite.guild.id, {})
            cache[invite.code] = invite.uses or 0

    @engage.command(name="counting-setup", description="Set a counting channel (next number starts at 1)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def counting_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        def mut(d):
            d["counting"] = {
                "enabled": True,
                "channelId": str(channel.id),
                "next": 1,
                "lastUser": None,
            }

        storage.update_guild(interaction.guild.id, mut)
        self._counting_expect[channel.id] = 1
        await interaction.response.send_message(f"Counting channel: {channel.mention} — start at **1**.")

    @engage.command(name="wordchain-setup", description="Set a word-chain channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def wordchain_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        def mut(d):
            d["wordchain"] = {
                "enabled": True,
                "channelId": str(channel.id),
                "lastWord": "",
                "lastUser": None,
            }

        storage.update_guild(interaction.guild.id, mut)
        self._wordchain_last.pop(channel.id, None)
        await interaction.response.send_message(f"Word-chain channel: {channel.mention}")

    @commands.command(name="afk")
    async def afk_prefix(self, ctx: commands.Context, *, reason: str = "AFK"):
        if not ctx.guild:
            return
        self._afk[ctx.guild.id][ctx.author.id] = reason[:200]
        await ctx.reply(f"You're now AFK: {reason[:200]}", mention_author=False)

    @app_commands.command(name="afk", description="Set AFK status")
    async def afk_slash(self, interaction: discord.Interaction, reason: str = "AFK"):
        self._afk[interaction.guild.id][interaction.user.id] = reason[:200]
        await interaction.response.send_message(f"You're now AFK: {reason[:200]}")

    @verify_g.command(name="setup", description="Setup verification button + role")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def verify_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: discord.Role,
        message: str = "Click the button below to verify and gain access.",
    ):
        view = discord.ui.View(timeout=None)
        btn = discord.ui.Button(
            label="Verify", style=discord.ButtonStyle.success, custom_id="omnibot:verify"
        )
        view.add_item(btn)
        emb = discord.Embed(title="Verification", description=message, color=0x3DD68C)
        msg = await channel.send(embed=emb, view=view)

        def mut(d):
            d["verification"] = {
                "enabled": True,
                "roleId": str(role.id),
                "channelId": str(channel.id),
                "messageId": str(msg.id),
            }

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message("Verification panel posted.", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        if not interaction.data or interaction.data.get("custom_id") != "omnibot:verify":
            return
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        data = storage.load_guild(interaction.guild.id)
        v = data.get("verification") or {}
        if not v.get("enabled") or not v.get("roleId"):
            return await interaction.response.send_message(
                "Verification not configured.", ephemeral=True
            )
        role = interaction.guild.get_role(int(v["roleId"]))
        if not role:
            return await interaction.response.send_message("Verify role missing.", ephemeral=True)
        try:
            await interaction.user.add_roles(role, reason="Verified")
            await interaction.response.send_message("✅ Verified!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

    @engage.command(
        name="honeypot-setup",
        description="Mark a channel as honeypot (auto-ban on message) and post a warning",
    )
    @app_commands.checks.has_permissions(ban_members=True)
    async def honeypot_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        enabled: bool = True,
    ):
        def mut(d):
            d["honeypot"] = {"enabled": enabled, "channelId": str(channel.id)}

        storage.update_guild(interaction.guild.id, mut)

        if enabled:
            emb = discord.Embed(
                title="⚠️ HONEYPOT CHANNEL",
                description=(
                    "This channel is a **trap for raiders and spam bots**.\n\n"
                    "**Anyone who sends a message here will be automatically banned.**\n\n"
                    "If you are a normal member and can see this: **do not type anything.** "
                    "Leave this channel."
                ),
                color=0xF04438,
            )
            emb.set_footer(text="OmniBot honeypot · messages here = ban")
            try:
                await channel.send(embed=emb)
            except Exception as e:
                await interaction.response.send_message(
                    f"Honeypot enabled on {channel.mention}, but could not post warning: {e}",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                f"Honeypot **enabled** on {channel.mention}. Warning message posted.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"Honeypot **disabled** on {channel.mention}.",
                ephemeral=True,
            )

    @engage.command(name="booster-setup", description="Celebrate server boosts in a channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def booster_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str = "🚀 {user} just boosted the server! Thank you!",
    ):
        def mut(d):
            d["booster"] = {"enabled": True, "channelId": str(channel.id), "message": message}

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Booster messages → {channel.mention}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.premium_since == after.premium_since:
            return
        if after.premium_since and (
            not before.premium_since or after.premium_since > before.premium_since
        ):
            data = storage.load_guild(after.guild.id)
            b = data.get("booster") or {}
            if not b.get("enabled") or not b.get("channelId"):
                return
            ch = after.guild.get_channel(int(b["channelId"]))
            if isinstance(ch, discord.TextChannel):
                msg = b.get("message") or "🚀 {user} boosted!"
                msg = msg.replace("{user}", after.mention).replace("{username}", after.name)
                try:
                    await ch.send(msg)
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not message.content:
            return
        data = storage.load_guild(message.guild.id)
        gid = message.guild.id
        cid = message.channel.id

        if message.author.id in self._afk.get(gid, {}):
            self._afk[gid].pop(message.author.id, None)
            try:
                await message.channel.send(
                    f"Welcome back {message.author.mention} — AFK removed.", delete_after=8
                )
            except Exception:
                pass
        for m in message.mentions:
            reason = self._afk.get(gid, {}).get(m.id)
            if reason:
                try:
                    await message.channel.send(
                        f"{m.display_name} is AFK: {reason}", delete_after=12
                    )
                except Exception:
                    pass

        hp = data.get("honeypot") or {}
        if hp.get("enabled") and str(cid) == str(hp.get("channelId")):
            # Don't ban staff / people with ban perms (avoid self-ban accidents)
            if isinstance(message.author, discord.Member):
                if (
                    message.author.guild_permissions.ban_members
                    or message.author.guild_permissions.administrator
                ):
                    return
            try:
                await message.author.ban(reason="Honeypot channel", delete_message_days=0)
            except Exception:
                try:
                    await message.author.kick(reason="Honeypot channel")
                except Exception:
                    pass
            try:
                await message.delete()
            except Exception:
                pass
            return

        cnt = data.get("counting") or {}
        if cnt.get("enabled") and str(cid) == str(cnt.get("channelId")):
            expect = int(cnt.get("next") or 1)
            last_user = cnt.get("lastUser")
            try:
                num = int(message.content.strip().split()[0])
            except ValueError:
                try:
                    await message.delete()
                except Exception:
                    pass
                return
            if num != expect or str(message.author.id) == str(last_user):
                try:
                    await message.delete()
                except Exception:
                    pass
                return

            def mut(d):
                c = d.setdefault("counting", {})
                c["next"] = expect + 1
                c["lastUser"] = str(message.author.id)

            storage.update_guild(gid, mut)
            return

        wc = data.get("wordchain") or {}
        if wc.get("enabled") and str(cid) == str(wc.get("channelId")):
            word = message.content.strip().lower().split()[0]
            word = re.sub(r"[^a-z]", "", word)
            if len(word) < 2:
                try:
                    await message.delete()
                except Exception:
                    pass
                return
            last = (wc.get("lastWord") or "").lower()
            last_user = wc.get("lastUser")
            if last and (
                not word.startswith(last[-1]) or str(message.author.id) == str(last_user)
            ):
                try:
                    await message.delete()
                except Exception:
                    pass
                return

            def mut(d):
                w = d.setdefault("wordchain", {})
                w["lastWord"] = word
                w["lastUser"] = str(message.author.id)

            storage.update_guild(gid, mut)


async def setup(bot: commands.Bot):
    await bot.add_cog(EngagementExtra(bot))
