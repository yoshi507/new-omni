"""Feature hub 2: bump, analytics, social, docs, forms, casino."""
from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from omnibot import storage


def _parse_color(s: str | None, default: int = 0x5B6CFF) -> int:
    if not s:
        return default
    s = str(s).strip().lstrip("#")
    try:
        return int(s, 16) & 0xFFFFFF
    except ValueError:
        return default


class FeaturesHub2(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._bump_last: dict[int, float] = {}
        self.bump_loop.start()

    def cog_unload(self):
        self.bump_loop.cancel()

    bump = app_commands.Group(name="bump", description="Disboard / DISBOARD bump reminders")

    @bump.command(name="setup", description="Channel for bump reminders (2h after DISBOARD bump)")
    @app_commands.checks.has_permissions(administrator=True)
    async def bump_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        enabled: bool = True,
        message: str = "⏰ Time to `/bump` the server!",
    ):
        def mut(d):
            d["bumpReminder"] = {
                "enabled": enabled,
                "channelId": str(channel.id),
                "message": message[:500],
                "lastBumpAt": 0,
            }

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(
            f"Bump reminder {'on' if enabled else 'off'} → {channel.mention}", ephemeral=True
        )

    @commands.Cog.listener(name="on_message")
    async def on_message_bump(self, message: discord.Message):
        if not message.guild or not message.author.bot:
            return
        content = (message.content or "").lower()
        embeds_txt = " ".join((e.description or "") + (e.title or "") for e in message.embeds).lower()
        if "bump" not in content and "bump" not in embeds_txt:
            return
        if "success" not in embeds_txt and "bumped" not in embeds_txt and "next bump" not in embeds_txt:
            if "disboard" not in str(message.author).lower():
                return
        data = storage.load_guild(message.guild.id)
        br = data.get("bumpReminder") or {}
        if not br.get("enabled"):
            return

        def mut(d):
            d.setdefault("bumpReminder", {})["lastBumpAt"] = time.time()

        storage.update_guild(message.guild.id, mut)
        self._bump_last[message.guild.id] = time.time()

    @tasks.loop(minutes=5)
    async def bump_loop(self):
        for guild in list(self.bot.guilds):
            try:
                data = storage.load_guild(guild.id)
                br = data.get("bumpReminder") or {}
                if not br.get("enabled") or not br.get("channelId"):
                    continue
                last = float(br.get("lastBumpAt") or 0)
                if last <= 0:
                    continue
                if time.time() - last < 7200:
                    continue
                ch = guild.get_channel(int(br["channelId"]))
                if not isinstance(ch, discord.TextChannel):
                    continue

                def mut(d):
                    d.setdefault("bumpReminder", {})["lastBumpAt"] = 0

                storage.update_guild(guild.id, mut)
                try:
                    await ch.send(br.get("message") or "⏰ Time to `/bump` the server!")
                except Exception:
                    pass
            except Exception:
                continue

    @bump_loop.before_loop
    async def before_bump(self):
        await self.bot.wait_until_ready()

    stats = app_commands.Group(name="stats", description="Server stats & analytics")

    @stats.command(name="server", description="Server community stats overview")
    async def stats_server(self, interaction: discord.Interaction):
        g = interaction.guild
        if not g:
            return
        data = storage.load_guild(g.id)
        an = data.get("analytics") or {}
        emb = discord.Embed(title=f"📈 {g.name} stats", color=0x5B6CFF)
        emb.add_field(name="Members", value=str(g.member_count or len(g.members)))
        emb.add_field(name="Channels", value=str(len(g.channels)))
        emb.add_field(name="Roles", value=str(len(g.roles)))
        emb.add_field(name="Messages tracked", value=str(an.get("messages", 0)))
        emb.add_field(name="Joins tracked", value=str(an.get("joins", 0)))
        emb.add_field(name="Leaves tracked", value=str(an.get("leaves", 0)))
        emb.set_thumbnail(url=g.icon.url if g.icon else None)
        await interaction.response.send_message(embed=emb)

    @stats.command(name="analytics", description="Activity analytics snapshot")
    @app_commands.checks.has_permissions(administrator=True)
    async def stats_analytics(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        an = data.get("analytics") or {}
        emb = discord.Embed(title="📊 Analytics", color=0x5B6CFF)
        emb.add_field(name="Messages", value=str(an.get("messages", 0)))
        emb.add_field(name="Joins", value=str(an.get("joins", 0)))
        emb.add_field(name="Leaves", value=str(an.get("leaves", 0)))
        emb.add_field(name="Commands", value=str(an.get("commands", 0)))
        await interaction.response.send_message(embed=emb, ephemeral=True)

    @commands.Cog.listener(name="on_message")
    async def on_message_count(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        def mut(d):
            a = d.setdefault("analytics", {"messages": 0, "joins": 0, "leaves": 0, "commands": 0})
            a["messages"] = int(a.get("messages") or 0) + 1

        storage.update_guild(message.guild.id, mut)

    @commands.Cog.listener(name="on_member_join")
    async def on_member_join_stats(self, member: discord.Member):
        def mut(d):
            a = d.setdefault("analytics", {"messages": 0, "joins": 0, "leaves": 0, "commands": 0})
            a["joins"] = int(a.get("joins") or 0) + 1

        storage.update_guild(member.guild.id, mut)

    @commands.Cog.listener(name="on_member_remove")
    async def on_member_remove_stats(self, member: discord.Member):
        def mut(d):
            a = d.setdefault("analytics", {"messages": 0, "joins": 0, "leaves": 0, "commands": 0})
            a["leaves"] = int(a.get("leaves") or 0) + 1

        storage.update_guild(member.guild.id, mut)

    social = app_commands.Group(name="social", description="Social feed notifications")

    @social.command(name="setup", description="Channel for social notifications")
    @app_commands.checks.has_permissions(administrator=True)
    async def social_setup(
        self, interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool = True
    ):
        def mut(d):
            d.setdefault("social", {})["channelId"] = str(channel.id)
            d["social"]["enabled"] = enabled
            d["social"].setdefault("feeds", [])

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(
            f"Social notifications {'on' if enabled else 'off'} → {channel.mention}. Add feeds with `/social add`.",
            ephemeral=True,
        )

    @social.command(name="add", description="Add a feed label (YouTube/Twitch/Twitter handle)")
    @app_commands.checks.has_permissions(administrator=True)
    async def social_add(
        self, interaction: discord.Interaction, platform: str, handle: str
    ):
        platform = platform.strip().lower()
        handle = handle.strip().lstrip("@")

        def mut(d):
            feeds = d.setdefault("social", {}).setdefault("feeds", [])
            feeds.append({"platform": platform[:32], "handle": handle[:64]})
            d["social"]["feeds"] = feeds[-20:]

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(f"Added **{platform}** / **{handle}**.", ephemeral=True)

    @social.command(name="list", description="List configured social feeds")
    async def social_list(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        feeds = (data.get("social") or {}).get("feeds") or []
        if not feeds:
            return await interaction.response.send_message("No feeds. Use `/social add`.", ephemeral=True)
        lines = [f"• **{f.get('platform')}** — `{f.get('handle')}`" for f in feeds]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @social.command(name="notify", description="Post a manual social notification")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def social_notify(
        self, interaction: discord.Interaction, title: str, url: str, platform: str = "update"
    ):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        soc = data.get("social") or {}
        ch_id = soc.get("channelId")
        if not ch_id:
            return await interaction.response.send_message("Set a channel with `/social setup` first.", ephemeral=True)
        ch = interaction.guild.get_channel(int(ch_id))  # type: ignore
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("Channel missing.", ephemeral=True)
        emb = discord.Embed(title=title[:256], url=url[:500], color=0xFF0050)
        emb.set_footer(text=f"{platform} · via OmniBot")
        await ch.send(embed=emb)
        await interaction.response.send_message("Posted.", ephemeral=True)

    docs = app_commands.Group(name="docs", description="Server documentation pages")

    @docs.command(name="set", description="Create or update a doc page")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def docs_set(self, interaction: discord.Interaction, name: str, content: str):
        key = re.sub(r"[^a-z0-9_-]+", "-", name.lower())[:32]

        def mut(d):
            d.setdefault("serverDocs", {})[key] = {"title": name[:64], "content": content[:4000]}

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(f"Doc **{key}** saved.", ephemeral=True)

    @docs.command(name="get", description="Show a doc page")
    async def docs_get(self, interaction: discord.Interaction, name: str):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        docs = data.get("serverDocs") or {}
        key = re.sub(r"[^a-z0-9_-]+", "-", name.lower())[:32]
        doc = docs.get(key) or docs.get(name)
        if not doc:
            return await interaction.response.send_message("Doc not found. `/docs list`", ephemeral=True)
        emb = discord.Embed(title=doc.get("title") or name, description=doc.get("content", "")[:4000], color=0x5B6CFF)
        await interaction.response.send_message(embed=emb)

    @docs.command(name="list", description="List server docs")
    async def docs_list(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        docs = data.get("serverDocs") or {}
        if not docs:
            return await interaction.response.send_message("No docs yet. `/docs set`")
        lines = [f"• `{k}` — {v.get('title', k)}" for k, v in list(docs.items())[:30]]
        await interaction.response.send_message("\n".join(lines))

    form_g = app_commands.Group(name="form", description="Custom staff forms")

    @form_g.command(name="create", description="Create a custom form (modal fields)")
    @app_commands.checks.has_permissions(administrator=True)
    async def form_create(
        self,
        interaction: discord.Interaction,
        name: str,
        field1: str,
        field2: str | None = None,
        field3: str | None = None,
        channel: discord.TextChannel | None = None,
    ):
        key = re.sub(r"[^a-z0-9_-]+", "-", name.lower())[:32]
        fields = [f for f in [field1, field2, field3] if f]

        def mut(d):
            d.setdefault("forms", {})[key] = {
                "name": name[:64],
                "fields": fields[:5],
                "channelId": str(channel.id) if channel else "",
            }

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(
            f"Form **{key}** created. Users: `/form submit {key}`", ephemeral=True
        )

    @form_g.command(name="submit", description="Submit a custom form")
    async def form_submit(self, interaction: discord.Interaction, name: str):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        key = re.sub(r"[^a-z0-9_-]+", "-", name.lower())[:32]
        form = (data.get("forms") or {}).get(key)
        if not form:
            return await interaction.response.send_message("Unknown form.", ephemeral=True)

        class FormModal(discord.ui.Modal, title=str(form.get("name") or "Form")[:45]):
            def __init__(self):
                super().__init__()
                self.inputs = []
                for i, label in enumerate((form.get("fields") or [])[:5]):
                    ti = discord.ui.TextInput(
                        label=str(label)[:45],
                        style=discord.TextStyle.paragraph,
                        required=True,
                        max_length=1000,
                    )
                    self.inputs.append(ti)
                    self.add_item(ti)

            async def on_submit(modal_self, inter: discord.Interaction):
                emb = discord.Embed(title=f"📝 {form.get('name')}", color=0x5B6CFF)
                emb.set_author(name=str(inter.user), icon_url=inter.user.display_avatar.url)
                for ti in modal_self.inputs:
                    emb.add_field(name=ti.label, value=ti.value[:1000], inline=False)
                dest = inter.channel
                cid = form.get("channelId")
                if cid and inter.guild:
                    ch = inter.guild.get_channel(int(cid))
                    if isinstance(ch, discord.TextChannel):
                        dest = ch
                try:
                    await dest.send(embed=emb)  # type: ignore
                except Exception:
                    await inter.response.send_message("Could not deliver form.", ephemeral=True)
                    return
                await inter.response.send_message("Form submitted!", ephemeral=True)

        await interaction.response.send_modal(FormModal())

    casino = app_commands.Group(name="casino", description="Casino games (server coins)")

    @casino.command(name="blackjack", description="Play blackjack (bet coins)")
    @app_commands.describe(bet="Coins to bet (min 10)")
    async def casino_blackjack(
        self, interaction: discord.Interaction, bet: app_commands.Range[int, 10, 10000] = 50
    ):
        gid = interaction.guild.id  # type: ignore
        uid = str(interaction.user.id)
        data = storage.load_guild(gid)
        eco = (data.get("economy") or {}).get(uid) or {}
        coins = int(eco.get("coins") or 0)
        if coins < bet:
            return await interaction.response.send_message(
                f"You need **{bet}** coins (have {coins}).", ephemeral=True
            )

        def card():
            return random.choice([2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11])

        def hand_val(cards):
            s = sum(cards)
            aces = cards.count(11)
            while s > 21 and aces:
                s -= 10
                aces -= 1
            return s

        player = [card(), card()]
        dealer = [card(), card()]
        pv, dv = hand_val(player), hand_val(dealer)
        while pv < 17:
            player.append(card())
            pv = hand_val(player)
        while dv < 17:
            dealer.append(card())
            dv = hand_val(dealer)

        if pv > 21 and dv > 21:
            result, delta = "Both bust — push", 0
        elif pv > 21:
            result, delta = "You bust", -bet
        elif dv > 21:
            result, delta = "Dealer bust — you win!", bet
        elif pv > dv:
            result, delta = "You win!", bet
        elif pv < dv:
            result, delta = "Dealer wins", -bet
        else:
            result, delta = "Push", 0

        def mut(d):
            e = d.setdefault("economy", {}).setdefault(uid, {})
            e["coins"] = int(e.get("coins") or 0) + delta

        storage.update_guild(gid, mut)
        emb = discord.Embed(
            title="🃏 Blackjack",
            description=(
                f"**You:** {player} = **{pv}**\n"
                f"**Dealer:** {dealer} = **{dv}**\n\n"
                f"{result} · **{delta:+d}** coins"
            ),
            color=0x2ECC71 if delta > 0 else (0xE74C3C if delta < 0 else 0x95A5A6),
        )
        await interaction.response.send_message(embed=emb)

    @casino.command(name="roulette", description="Roulette (red/black/green or number)")
    @app_commands.describe(bet="Coins to bet", choice="red, black, green, or 0-36")
    async def casino_roulette(
        self,
        interaction: discord.Interaction,
        bet: app_commands.Range[int, 10, 10000] = 50,
        choice: str = "red",
    ):
        gid = interaction.guild.id  # type: ignore
        uid = str(interaction.user.id)
        data = storage.load_guild(gid)
        coins = int(((data.get("economy") or {}).get(uid) or {}).get("coins") or 0)
        if coins < bet:
            return await interaction.response.send_message(
                f"Need **{bet}** coins (have {coins}).", ephemeral=True
            )

        choice = choice.strip().lower()
        spin = random.randint(0, 36)
        reds = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
        color = "green" if spin == 0 else ("red" if spin in reds else "black")

        payout = 0
        if choice in ("red", "black"):
            if choice == color:
                payout = bet
        elif choice == "green":
            if spin == 0:
                payout = bet * 14
        else:
            try:
                n = int(choice)
                if 0 <= n <= 36 and n == spin:
                    payout = bet * 35
            except ValueError:
                return await interaction.response.send_message(
                    "Choice: red, black, green, or 0-36.", ephemeral=True
                )

        delta = payout if payout else -bet

        def mut(d):
            e = d.setdefault("economy", {}).setdefault(uid, {})
            e["coins"] = int(e.get("coins") or 0) + delta

        storage.update_guild(gid, mut)
        emb = discord.Embed(
            title="🎰 Roulette",
            description=f"Ball landed on **{spin}** ({color}).\nYou picked **{choice}**.\n**{delta:+d}** coins",
            color=0xE74C3C if color == "red" else (0x2C3E50 if color == "black" else 0x27AE60),
        )
        await interaction.response.send_message(embed=emb)


async def setup(bot: commands.Bot):
    await bot.add_cog(FeaturesHub2(bot))
