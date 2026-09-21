"""Appeals, giveaways, reaction roles, advertise, partner, captcha, userphone, quiz, translate."""
from __future__ import annotations

import random
import time
import uuid

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage


class Community(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._userphone: dict[int, int] = {}  # channel -> partner channel

    # —— Appeals ——
    appeal = app_commands.Group(name="appeal", description="Ban/timeout/warn appeals")

    @appeal.command(name="setup", description="Enable appeals and set review channel")
    @app_commands.default_permissions(manage_guild=True)
    async def appeal_setup(
        self, interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool = True
    ):
        def mut(d):
            ap = d.setdefault("appeals", {})
            ap["enabled"] = enabled
            ap["channelId"] = str(channel.id)

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(
            f"Appeals {'enabled' if enabled else 'disabled'}. Channel: {channel.mention}"
        )

    @appeal.command(name="list", description="List pending appeals")
    @app_commands.default_permissions(moderate_members=True)
    async def appeal_list(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        recs = data.get("appealsRecords") or {}
        pending = [v for v in recs.values() if v.get("status") == "pending"]
        if not pending:
            return await interaction.response.send_message("No pending appeals.", ephemeral=True)
        lines = [
            f"`{r['id']}` <@{r['userId']}> {r.get('punishment')} — {r.get('reason', '')[:80]}"
            for r in pending[:20]
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @appeal.command(name="accept", description="Accept an appeal (unban/unmute/clear warn as applicable)")
    @app_commands.default_permissions(ban_members=True)
    async def appeal_accept(self, interaction: discord.Interaction, appeal_id: str):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        rec = (data.get("appealsRecords") or {}).get(appeal_id)
        if not rec:
            return await interaction.response.send_message("Unknown appeal id.", ephemeral=True)
        uid = int(rec["userId"])
        ptype = rec.get("punishment", "ban")
        try:
            if ptype == "ban":
                await interaction.guild.unban(discord.Object(id=uid), reason=f"Appeal {appeal_id}")  # type: ignore
            elif ptype == "timeout":
                member = interaction.guild.get_member(uid)  # type: ignore
                if member:
                    await member.timeout(None, reason=f"Appeal {appeal_id}")
            elif ptype == "warn":

                def mut_w(d):
                    (d.get("warnings") or {}).pop(str(uid), None)

                storage.update_guild(interaction.guild.id, mut_w)  # type: ignore
        except Exception as e:
            await interaction.response.send_message(f"Action failed: {e}", ephemeral=True)
            return

        def mut(d):
            r = (d.get("appealsRecords") or {}).get(appeal_id)
            if r:
                r["status"] = "accepted"

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(f"Appeal `{appeal_id}` accepted.")

    @appeal.command(name="reject", description="Reject an appeal")
    @app_commands.default_permissions(moderate_members=True)
    async def appeal_reject(self, interaction: discord.Interaction, appeal_id: str):
        def mut(d):
            r = (d.get("appealsRecords") or {}).get(appeal_id)
            if r:
                r["status"] = "rejected"
            else:
                raise RuntimeError("missing")

        try:
            storage.update_guild(interaction.guild.id, mut)  # type: ignore
        except RuntimeError:
            return await interaction.response.send_message("Unknown appeal.", ephemeral=True)
        await interaction.response.send_message(f"Appeal `{appeal_id}` rejected.")

    # —— Advertise ——
    @app_commands.command(name="advertise", description="List this server on the public advertise board")
    @app_commands.default_permissions(manage_guild=True)
    async def advertise(
        self,
        interaction: discord.Interaction,
        description: str,
        category: str = "General",
        invite: str | None = None,
    ):
        inv = invite
        if not inv:
            try:
                inv_obj = await interaction.channel.create_invite(max_age=0, max_uses=0)  # type: ignore
                inv = inv_obj.url
            except Exception:
                inv = None

        def mut(d):
            d["advertise"] = {
                "listed": True,
                "description": description[:500],
                "category": category[:40],
                "invite": inv,
            }

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Server listed on the advertise board.")

    # —— Partner / affiliate stubs ——
    @app_commands.command(name="partner", description="Record a partnership with another server")
    @app_commands.default_permissions(manage_guild=True)
    async def partner(self, interaction: discord.Interaction, other_server_id: str, note: str = ""):
        def mut(d):
            p = d.setdefault("partner", {})
            p[other_server_id] = {"note": note[:300], "at": time.time(), "by": str(interaction.user.id)}

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(f"Partnership recorded with `{other_server_id}`.")

    @app_commands.command(name="affiliate", description="Manage affiliate tag for this server")
    @app_commands.default_permissions(manage_guild=True)
    async def affiliate(self, interaction: discord.Interaction, code: str):
        def mut(d):
            d.setdefault("partner", {})["affiliateCode"] = code[:40]

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(f"Affiliate code set to `{code}`.")

    # —— Giveaway ——
    @app_commands.command(name="giveaway", description="Start a simple reaction giveaway")
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway(
        self, interaction: discord.Interaction, prize: str, winners: app_commands.Range[int, 1, 20] = 1
    ):
        embed = discord.Embed(
            title="🎉 Giveaway",
            description=f"**{prize}**\nReact with 🎉 to enter!\nWinners: {winners}",
            color=0xFEE75C,
        )
        await interaction.response.send_message(embeds=[embed])
        msg = await interaction.original_response()
        await msg.add_reaction("🎉")

        def mut(d):
            d.setdefault("giveaways", {})[str(msg.id)] = {
                "prize": prize,
                "winners": winners,
                "channel": str(interaction.channel.id),
            }

        storage.update_guild(interaction.guild.id, mut)  # type: ignore

    # —— Translate (non-AI) ——
    @app_commands.command(name="translate", description="Translate text (non-AI, unlimited)")
    @app_commands.describe(text="Text", target="Target language code e.g. es, fr, de")
    async def translate(self, interaction: discord.Interaction, text: str, target: str = "en"):
        await interaction.response.defer()
        try:
            import httpx

            # LibreTranslate public instances vary; best-effort
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(
                    "https://libretranslate.com/translate",
                    json={"q": text[:1000], "source": "auto", "target": target, "format": "text"},
                )
            if r.status_code == 200:
                out = r.json().get("translatedText") or r.text
                await interaction.followup.send(out[:1900])
            else:
                await interaction.followup.send(
                    f"Translation service unavailable ({r.status_code}). Try again later."
                )
        except Exception as e:
            await interaction.followup.send(f"Translation failed: {e}")

    # —— Quiz ——
    @app_commands.command(name="quiz", description="Start a short quiz")
    async def quiz(self, interaction: discord.Interaction):
        qs = [
            ("What year was Discord launched?", "2015"),
            ("How many bits in a byte?", "8"),
            ("Planet known as the Red Planet?", "mars"),
        ]
        q, a = random.choice(qs)
        await interaction.response.send_message(f"**Quiz:** {q}\n*(Answer in chat — staff can score manually)*")

    # —— Userphone ——
    @app_commands.command(name="userphone", description="Anonymous cross-server chat bridge")
    async def userphone(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Text only.", ephemeral=True)
        # Pair with another waiting channel if any
        waiting = getattr(self.bot, "_up_wait", None)
        if waiting and waiting != interaction.channel.id:
            self._userphone[waiting] = interaction.channel.id
            self._userphone[interaction.channel.id] = waiting
            self.bot._up_wait = None  # type: ignore
            other = self.bot.get_channel(waiting)
            await interaction.response.send_message("📞 Connected!")
            if other:
                try:
                    await other.send("📞 Someone picked up the userphone!")
                except Exception:
                    pass
        else:
            self.bot._up_wait = interaction.channel.id  # type: ignore
            await interaction.response.send_message("📞 Waiting for another server…")

    # —— Captcha ——
    @app_commands.command(name="captcha", description="Toggle simple join captcha mode")
    @app_commands.default_permissions(manage_guild=True)
    async def captcha(self, interaction: discord.Interaction, enabled: bool):
        def mut(d):
            d.setdefault("captcha", {})["enabled"] = enabled

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(f"Captcha {'enabled' if enabled else 'disabled'}.")

    # —— Reaction role ——
    @app_commands.command(name="reactionrole", description="Create a reaction-role message")
    @app_commands.default_permissions(manage_roles=True)
    async def reactionrole(
        self, interaction: discord.Interaction, role: discord.Role, emoji: str, label: str = "React for role"
    ):
        msg = await interaction.channel.send(f"{label}\nReact with {emoji} for {role.mention}")  # type: ignore
        try:
            await msg.add_reaction(emoji)
        except Exception:
            return await interaction.response.send_message("Invalid emoji.", ephemeral=True)

        def mut(d):
            d.setdefault("reactionRoles", {})[str(msg.id)] = {
                "emoji": emoji,
                "roleId": str(role.id),
            }

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Reaction role created.", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id or payload.user_id == self.bot.user.id:
            return
        data = storage.load_guild(payload.guild_id)
        rr = (data.get("reactionRoles") or {}).get(str(payload.message_id))
        if not rr:
            return
        if str(payload.emoji) != rr.get("emoji") and payload.emoji.name != rr.get("emoji"):
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(rr["roleId"]))
        if member and role:
            try:
                await member.add_roles(role, reason="Reaction role")
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Community(bot))
